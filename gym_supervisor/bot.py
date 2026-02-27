from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from urllib import error, request
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from gym_supervisor.db import GymDB


@dataclass(frozen=True)
class BotConfig:
    allowed_user_id: int
    openai_api_key: str
    reminder_hour: int
    reminder_minute: int
    snooze_minutes: int
    startup_greeting_enabled: bool = True


@dataclass(frozen=True)
class WeeklyMilestone:
    milestone: int
    required_workouts: int
    weekday: int
    hour: int
    minute: int
    label: str


ACTIONS = {
    "did_workout": "did_workout",
    "snooze": "snooze",
    "finish_workout": "finish_workout",
    "undo_entry": "undo_entry",
    "cancel_workout": "cancel_workout",
    "summary_week": "summary_week",
    "summary_month": "summary_month",
}

WEEKLY_MILESTONES = [
    WeeklyMilestone(1, 1, 1, 20, 0, "Tuesday 8:00 PM"),
    WeeklyMilestone(2, 2, 3, 20, 0, "Thursday 8:00 PM"),
    WeeklyMilestone(3, 3, 6, 16, 0, "Sunday 4:00 PM"),
]

AWAITING_WORKOUT_LOG_KEY = "awaiting_workout_log"
WORKOUT_DRAFT_KEY = "workout_draft"
MENU_TRIGGERS = {"hi", "hello", "hey", "menu", "start"}
TRACKED_BODY_AREAS = ("chest", "shoulders", "back", "legs", "core")
NUDGE_PRIORITY = ("chest", "back", "shoulders", "legs", "core")


class GymSupervisorBot:
    def __init__(self, token: str, db: GymDB, config: BotConfig) -> None:
        self._db = db
        self._config = config
        builder = Application.builder().token(token)
        if config.startup_greeting_enabled:
            builder = builder.post_init(self._post_init)
        self.app = builder.build()
        self._register_handlers()

    def _is_allowed(self, update: Update) -> bool:
        user = update.effective_user
        return bool(user and user.id == self._config.allowed_user_id)

    async def _reject_if_unauthorized(self, update: Update) -> bool:
        if self._is_allowed(update):
            return False

        if update.message:
            await update.message.reply_text("Unauthorized user.")
        elif update.callback_query:
            await update.callback_query.answer("Unauthorized", show_alert=True)
        return True

    @staticmethod
    def _now_pacific_naive() -> datetime:
        return datetime.now(ZoneInfo("America/Los_Angeles")).replace(tzinfo=None)

    @staticmethod
    def _week_start(now: datetime) -> datetime:
        return datetime.combine(now.date() - timedelta(days=now.weekday()), time.min)

    @staticmethod
    def _week_start_date(now: datetime) -> date:
        return now.date() - timedelta(days=now.weekday())

    def _register_handlers(self) -> None:
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help))
        self.app.add_handler(CommandHandler("log", self.log_command))
        self.app.add_handler(CommandHandler("remindme", self.send_manual_reminder))
        self.app.add_handler(CommandHandler("status", self.status))
        self.app.add_handler(CommandHandler("summary", self.summary))
        self.app.add_handler(CommandHandler("summary_week", self.summary_week))
        self.app.add_handler(CommandHandler("summary_month", self.summary_month))
        self.app.add_handler(CommandHandler("summary_quarter", self.summary_quarter))
        self.app.add_handler(CallbackQueryHandler(self.on_button))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.capture_sets_message)
        )

    def _reminder_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("I trained", callback_data=ACTIONS["did_workout"])],
                [InlineKeyboardButton("Snooze / Skip", callback_data=ACTIONS["snooze"])],
            ]
        )

    def _workout_draft_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Finish Workout", callback_data=ACTIONS["finish_workout"])],
                [InlineKeyboardButton("Undo Last Entry", callback_data=ACTIONS["undo_entry"])],
                [InlineKeyboardButton("Cancel", callback_data=ACTIONS["cancel_workout"])],
            ]
        )

    def _main_menu_keyboard(self) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("I trained", callback_data=ACTIONS["did_workout"])],
                [InlineKeyboardButton("summary_week", callback_data=ACTIONS["summary_week"])],
                [InlineKeyboardButton("summary_month", callback_data=ACTIONS["summary_month"])],
            ]
        )

    @staticmethod
    def _fallback_quote(today: date) -> str:
        quotes = [
            "Small steps, repeated daily, build unstoppable momentum.",
            "Discipline today is strength tomorrow.",
            "Show up for the work, and confidence will follow.",
            "Consistency beats intensity when intensity is inconsistent.",
            "Every set is a vote for the person you are becoming.",
            "Progress is quiet: one rep, one set, one day at a time.",
            "You do not need perfect conditions, only a clear next set.",
        ]
        return quotes[today.toordinal() % len(quotes)]

    @staticmethod
    def _extract_quote_text(payload: dict) -> str:
        text = str(payload.get("output_text", "")).strip()
        if text:
            return text

        parts: list[str] = []
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") in {"output_text", "text"}:
                    piece = str(content.get("text", "")).strip()
                    if piece:
                        parts.append(piece)
        return " ".join(parts).strip()

    def _generate_morning_quote_sync(self, today: date) -> str:
        api_key = self._config.openai_api_key.strip()
        if not api_key:
            return self._fallback_quote(today)

        prompt = (
            f"Today is {today.isoformat()}. Write one short motivating fitness quote for a morning "
            "check-in. 1 sentence, under 20 words, no hashtags, no emojis, no quotation marks."
        )
        payload = {
            "model": "gpt-4o-mini",
            "input": prompt,
            "max_output_tokens": 60,
        }
        req = request.Request(
            "https://api.openai.com/v1/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            quote = self._extract_quote_text(body)
            return quote or self._fallback_quote(today)
        except (error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return self._fallback_quote(today)

    async def send_morning_greeting(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_morning_greeting_now(context.bot)

    async def send_morning_greeting_now(self, bot) -> None:
        pacific_now = datetime.now(ZoneInfo("America/Los_Angeles")).replace(tzinfo=None)
        pacific_today = pacific_now.date()
        quote = await asyncio.to_thread(self._generate_morning_quote_sync, pacific_today)
        await bot.send_message(
            chat_id=self._config.allowed_user_id,
            text=f"Good morning.\n{quote}\n\nChoose an action:",
            reply_markup=self._main_menu_keyboard(),
        )
        await self._send_monthly_summary_if_due(bot, pacific_now)

    async def _post_init(self, app: Application) -> None:
        await app.bot.send_message(
            chat_id=self._config.allowed_user_id,
            text="Gym supervisor is online. Choose an action:",
            reply_markup=self._main_menu_keyboard(),
        )

    def _reset_workout_draft(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        context.user_data[AWAITING_WORKOUT_LOG_KEY] = False
        context.user_data[WORKOUT_DRAFT_KEY] = {"batches": []}

    def _set_awaiting_workout_draft(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        self._reset_workout_draft(context)
        context.user_data[AWAITING_WORKOUT_LOG_KEY] = True

    @staticmethod
    def _is_menu_trigger(text: str) -> bool:
        return text.strip().lower() in MENU_TRIGGERS

    @staticmethod
    def _parse_workout_entry(text: str) -> tuple[str, list[tuple[int, float]]]:
        clean_text = text.strip()
        if not clean_text:
            return "", []

        first_number = re.search(r"\d", clean_text)
        if not first_number:
            return "", []

        workout_type = re.sub(
            r"\s+",
            " ",
            clean_text[: first_number.start()].strip(" :-,").lower(),
        )
        if not workout_type:
            return "", []

        sets_text = clean_text[first_number.start() :]
        pairs: list[tuple[int, float]] = []

        # Supports patterns like 20x8, 20lbx8, 20 lb x 8
        explicit = re.findall(
            r"\b(\d{1,4}(?:\.\d+)?)\s*(?:lb)?\s*[xX@]\s*(\d{1,3})\b",
            sets_text,
            flags=re.IGNORECASE,
        )
        if explicit:
            for weight_raw, reps_raw in explicit:
                reps = int(reps_raw)
                weight = float(weight_raw)
                if 1 <= reps <= 100 and 0 < weight <= 2000:
                    pairs.append((reps, weight))
            return workout_type, pairs

        # Fallback: pair numbers as weight/reps, e.g. "20 8, 30 8"
        numbers = [float(n) for n in re.findall(r"\d+(?:\.\d+)?", sets_text)]
        if len(numbers) < 2:
            return workout_type, []

        if len(numbers) % 2 != 0:
            numbers = numbers[:-1]

        for idx in range(0, len(numbers), 2):
            weight = float(numbers[idx])
            reps = int(numbers[idx + 1])
            if 1 <= reps <= 100 and 0 < weight <= 2000:
                pairs.append((reps, weight))

        return workout_type, pairs

    @staticmethod
    def _draft_set_count(draft: dict) -> int:
        set_count = 0

        for batch in draft.get("batches", []):
            for pair in batch.get("pairs", []):
                if int(pair.get("reps", 0)) > 0:
                    set_count += 1

        return set_count

    @staticmethod
    def _format_body_area_summary(area_sets: dict[str, int]) -> str:
        if not area_sets:
            return "Sets by body area: unmapped 0."
        formatted = ", ".join(f"{area} {count}" for area, count in area_sets.items())
        return f"Sets by body area: {formatted}."

    @staticmethod
    def _format_breakdown_lines(title: str, values: dict[str, int]) -> list[str]:
        lines = [title]
        if not values:
            lines.append("- none")
            return lines
        for name, count in values.items():
            lines.append(f"- {name}: {count}")
        return lines

    @staticmethod
    def _summary_window(period: str) -> tuple[str, datetime, datetime]:
        now = GymSupervisorBot._now_pacific_naive()
        normalized = period.strip().lower()
        if normalized == "week":
            return "past week", now - timedelta(days=7), now
        if normalized == "month":
            return "past month", now - timedelta(days=30), now
        if normalized == "quarter":
            return "past quarter", now - timedelta(days=90), now
        raise ValueError("invalid period")

    def _build_period_summary_lines(self, period: str) -> list[str]:
        try:
            period_label, start, end = self._summary_window(period)
        except ValueError:
            raise

        summary = self._db.period_workout_summary(start, end)
        workouts = int(summary["workouts"])
        skips = int(summary["skips"])
        total_sets = int(summary["total_sets"])
        total_volume = float(summary["total_volume"])
        by_workout_type = dict(summary["by_workout_type"])
        by_body_area = dict(summary["by_body_area"])

        lines: list[str] = [
            f"Workout summary ({period_label})",
            f"Window: {start.date().isoformat()} to {end.date().isoformat()}",
            f"Workouts: {workouts}",
            f"Skips (snoozes): {skips}",
            f"Total sets: {total_sets}",
            f"Total volume: {total_volume:.1f}",
            "",
        ]
        lines.extend(self._format_breakdown_lines("By workout type:", by_workout_type))
        lines.append("")
        lines.extend(self._format_breakdown_lines("By body area:", by_body_area))
        return lines

    def _nudge_focus_text(self, now: datetime) -> str:
        week_ago = now - timedelta(days=7)
        by_body_area = self._db.summarize_sets_by_body_area_between(week_ago, now)
        trained = {
            area
            for area, count in by_body_area.items()
            if area in TRACKED_BODY_AREAS and count > 0
        }
        missing = [area for area in NUDGE_PRIORITY if area not in trained]
        if not missing:
            return "You've trained chest, back, shoulders, legs, and core in the past 7 days."
        if len(missing) == 1:
            return f"Suggested focus: {missing[0]} (not trained in the past 7 days)."
        return (
            "Suggested focus order (not trained in the past 7 days): "
            + " > ".join(missing)
            + "."
        )

    @staticmethod
    def _previous_month_window(now: datetime) -> tuple[date, datetime, datetime, str]:
        current_month_start = date(now.year, now.month, 1)
        period_end = datetime.combine(current_month_start, time.min)
        if now.month == 1:
            prev_month_start_date = date(now.year - 1, 12, 1)
        else:
            prev_month_start_date = date(now.year, now.month - 1, 1)
        period_start = datetime.combine(prev_month_start_date, time.min)
        label = prev_month_start_date.strftime("%B %Y")
        return prev_month_start_date, period_start, period_end, label

    def _build_monthly_report_text(self, now: datetime) -> str:
        _, period_start, period_end, label = self._previous_month_window(now)
        summary = self._db.period_workout_summary(period_start, period_end)
        workouts_done = int(summary["workouts"])
        total_sets = int(summary["total_sets"])
        by_workout_type = dict(summary["by_workout_type"])
        by_body_area = dict(summary["by_body_area"])
        skipped = self._db.count_snoozes_between(period_start, period_end)
        workout_logs = self._db.workouts_between(period_start, period_end)

        lines = [
            f"Monthly summary ({label})",
            f"Workouts done: {workouts_done}",
            f"Workouts skipped (snoozes): {skipped}",
            f"Total sets: {total_sets}",
            "",
            "Workouts completed:",
        ]
        if not workout_logs:
            lines.append("- none")
        else:
            for workout in workout_logs:
                ts = str(workout.logged_at).replace("T", " ")
                note = workout.note.strip()
                if note:
                    lines.append(f"- {ts}: {note} ({workout.sets} set(s))")
                else:
                    lines.append(f"- {ts}: {workout.sets} set(s)")

        lines.append("")
        lines.extend(self._format_breakdown_lines("By workout type:", by_workout_type))
        lines.append("")
        lines.extend(self._format_breakdown_lines("By body area:", by_body_area))
        return "\n".join(lines)

    async def _send_monthly_summary_if_due(self, bot, now: datetime) -> None:
        if now.day != 1:
            return

        period_start_date, _, _, _ = self._previous_month_window(now)
        if self._db.monthly_report_sent(period_start_date):
            return

        text = self._build_monthly_report_text(now)
        await bot.send_message(
            chat_id=self._config.allowed_user_id,
            text=text,
            reply_markup=self._main_menu_keyboard(),
        )
        self._db.mark_monthly_report_sent(period_start_date)

    async def _send_period_summary(
        self, update: Update, period: str, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        if await self._reject_if_unauthorized(update):
            return

        try:
            lines = self._build_period_summary_lines(period)
        except ValueError:
            await update.message.reply_text(
                "Unknown period. Use: /summary week, /summary month, or /summary quarter."
            )
            return

        await update.message.reply_text("\n".join(lines))

    def _append_workout_entry(self, context: ContextTypes.DEFAULT_TYPE, text: str) -> tuple[bool, str]:
        workout_type, pairs = self._parse_workout_entry(text)
        if not workout_type or not pairs:
            return False, (
                "I couldn't parse that. Include workout type plus sets, for example "
                "'bench press 20x8, 30x8' or 'bench press 20lb x8, 30lbx8'."
            )

        draft = context.user_data.get(WORKOUT_DRAFT_KEY)
        if not isinstance(draft, dict):
            self._reset_workout_draft(context)
            draft = context.user_data[WORKOUT_DRAFT_KEY]

        batches = draft.get("batches", [])
        batches.append(
            {
                "text": text.strip(),
                "workout_type": workout_type,
                "pairs": [{"reps": reps, "weight": weight} for reps, weight in pairs],
            }
        )
        draft["batches"] = batches
        context.user_data[WORKOUT_DRAFT_KEY] = draft

        total_sets = self._draft_set_count(draft)
        return True, f"Added {workout_type}: {len(pairs)} set(s). Current draft: {total_sets} set(s)."

    def _undo_last_workout_entry(self, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, str]:
        draft = context.user_data.get(WORKOUT_DRAFT_KEY)
        if not isinstance(draft, dict):
            return False, "No workout in progress. Tap 'I trained' to start."

        batches = draft.get("batches", [])
        if not batches:
            return False, "No entries to undo yet."

        removed = batches.pop()
        removed_count = len(removed.get("pairs", []))
        draft["batches"] = batches
        context.user_data[WORKOUT_DRAFT_KEY] = draft

        total_sets = self._draft_set_count(draft)
        return True, f"Removed last entry ({removed_count} set(s)). Current draft: {total_sets} set(s)."

    def _finalize_workout_draft(self, context: ContextTypes.DEFAULT_TYPE) -> tuple[bool, str]:
        draft = context.user_data.get(WORKOUT_DRAFT_KEY)
        if not isinstance(draft, dict):
            return False, "No workout in progress. Tap 'I trained' or use /log to start."

        batches = draft.get("batches", [])
        entries: list[tuple[str, int, float]] = []
        note_parts: list[str] = []

        for batch in batches:
            workout_type = str(batch.get("workout_type", "")).strip()
            note_parts.append(str(batch.get("text", "")).strip())
            for pair in batch.get("pairs", []):
                reps = int(pair.get("reps", 0))
                weight = float(pair.get("weight", 0.0))
                if workout_type and reps > 0 and weight > 0:
                    entries.append((workout_type, reps, weight))

        if not entries:
            return False, "No reps/weight entries collected yet. Send entries first."

        note = " | ".join(part for part in note_parts if part)
        workout_id = self._db.log_workout_with_entries(entries=entries, note=note)
        area_sets = self._db.summarize_sets_by_body_area_for_workout(workout_id)
        self._reset_workout_draft(context)
        total_sets = int(self._db.stats_summary()["total_sets"])
        area_summary = self._format_body_area_summary(area_sets)
        return True, (
            f"Workout saved: {len(entries)} set(s). Total sets logged: {total_sets}.\n"
            f"{area_summary}"
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_if_unauthorized(update):
            return

        await update.message.reply_text(
            "Gym supervisor active. Goal: 3 workouts per week.\n\n"
            "Deadlines:\n"
            "- Workout 1 by Tuesday 8:00 PM\n"
            "- Workout 2 by Thursday 8:00 PM\n"
            "- Workout 3 by Sunday 4:00 PM\n\n"
            "Commands:\n"
            "/log <workout type> <weight>x<reps> ... - quick one-message log\n"
            "/remindme - send check-in now\n"
            "/status - show weekly + total stats\n"
            "/summary <week|month|quarter> - workout breakdown",
            reply_markup=self._main_menu_keyboard(),
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_if_unauthorized(update):
            return
        await self.start(update, context)

    async def log_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_if_unauthorized(update):
            return

        text = " ".join(context.args).strip()
        if not text:
            self._set_awaiting_workout_draft(context)
            await update.message.reply_text(
                "Send one or more entries with workout type + sets.\n"
                "Examples: 'bench press 20x8, 30x8' or 'squat 135lb x5, 155x5'.\n"
                "When done, tap Finish Workout.",
                reply_markup=self._workout_draft_keyboard(),
            )
            return

        workout_type, pairs = self._parse_workout_entry(text)
        if not workout_type or not pairs:
            await update.message.reply_text(
                "Couldn't parse entry. Example: /log bench press 20x8, 30x8"
            )
            return

        workout_id = self._db.log_workout_with_entries(
            entries=[(workout_type, reps, weight) for reps, weight in pairs],
            note=text,
        )
        area_sets = self._db.summarize_sets_by_body_area_for_workout(workout_id)
        total_sets = int(self._db.stats_summary()["total_sets"])
        area_summary = self._format_body_area_summary(area_sets)
        await update.message.reply_text(
            f"Workout logged: {len(pairs)} set(s). Total sets logged: {total_sets}.\n"
            f"{area_summary}",
            reply_markup=self._main_menu_keyboard(),
        )

    async def send_manual_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_if_unauthorized(update):
            return
        await update.message.reply_text(
            "Gym check-in: did you train?",
            reply_markup=self._reminder_keyboard(),
        )

    async def summary(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        period = context.args[0] if context.args else "week"
        await self._send_period_summary(update, period, context)

    async def summary_week(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_period_summary(update, "week", context)

    async def summary_month(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_period_summary(update, "month", context)

    async def summary_quarter(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._send_period_summary(update, "quarter", context)

    async def send_scheduled_reminder(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        await context.bot.send_message(
            chat_id=self._config.allowed_user_id,
            text="Gym check-in. Tap I trained to log your workout or snooze.",
            reply_markup=self._reminder_keyboard(),
        )

    async def on_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_if_unauthorized(update):
            return

        query = update.callback_query
        await query.answer()

        if query.data == ACTIONS["did_workout"]:
            self._set_awaiting_workout_draft(context)
            await query.message.reply_text(
                "Great. Send workout type + sets as one or more messages.\n"
                "Examples: 'bench press 20x8, 30x8' or 'squat 135lb x5, 155x5'.\n"
                "When done, tap Finish Workout.",
                reply_markup=self._workout_draft_keyboard(),
            )
            return

        if query.data == ACTIONS["summary_week"]:
            lines = self._build_period_summary_lines("week")
            await query.message.reply_text(
                "\n".join(lines),
                reply_markup=self._main_menu_keyboard(),
            )
            return

        if query.data == ACTIONS["summary_month"]:
            lines = self._build_period_summary_lines("month")
            await query.message.reply_text(
                "\n".join(lines),
                reply_markup=self._main_menu_keyboard(),
            )
            return

        if query.data == ACTIONS["finish_workout"]:
            ok, message = self._finalize_workout_draft(context)
            await query.message.reply_text(
                message,
                reply_markup=self._main_menu_keyboard(),
            )
            return

        if query.data == ACTIONS["undo_entry"]:
            ok, message = self._undo_last_workout_entry(context)
            await query.message.reply_text(message, reply_markup=self._workout_draft_keyboard())
            return

        if query.data == ACTIONS["cancel_workout"]:
            self._reset_workout_draft(context)
            await query.message.reply_text("Workout draft canceled.")
            return

        if query.data == ACTIONS["snooze"]:
            self._db.log_snooze("button_snooze")
            await query.message.reply_text(
                f"Snooze logged. I will remind you again in {self._config.snooze_minutes} minutes."
            )
            context.job_queue.run_once(
                self.send_scheduled_reminder,
                when=self._config.snooze_minutes * 60,
                name="snooze_reminder",
            )

    async def capture_sets_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_if_unauthorized(update):
            return

        text = (update.message.text or "").strip()
        if not text:
            return

        awaiting = bool(context.user_data.get(AWAITING_WORKOUT_LOG_KEY, False))
        if not awaiting:
            if self._is_menu_trigger(text):
                await update.message.reply_text(
                    "What do you want to do?",
                    reply_markup=self._main_menu_keyboard(),
                )
            return

        ok, message = self._append_workout_entry(context, text)
        await update.message.reply_text(message, reply_markup=self._workout_draft_keyboard())

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if await self._reject_if_unauthorized(update):
            return

        now = self._now_pacific_naive()
        week_start = self._week_start(now)
        week_end = week_start + timedelta(days=7)
        weekly_count = self._db.count_workouts_this_week(week_start, week_end)
        s = self._db.stats_summary()

        lines = [
            f"This week: {weekly_count}/3 workouts",
            f"Workouts (all-time): {s['workout_count']}",
            f"Snoozes (all-time): {s['snooze_count']}",
            f"Total sets: {s['total_sets']}",
            f"Avg sets/workout: {s['avg_sets']:.1f}",
            f"Total volume: {s['total_volume']:.1f}",
            f"Avg volume/workout: {s['avg_volume']:.1f}",
        ]
        await update.message.reply_text("\n".join(lines))

    async def check_weekly_deadline_nudges(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self.send_weekly_deadline_nudges_now(context.bot)

    async def send_weekly_deadline_nudges_now(self, bot) -> None:
        now = self._now_pacific_naive()
        week_start = self._week_start(now)
        week_start_date = self._week_start_date(now)

        for milestone in WEEKLY_MILESTONES:
            if self._db.weekly_nudge_sent(week_start_date, milestone.milestone):
                continue

            deadline = week_start + timedelta(days=milestone.weekday)
            deadline = deadline.replace(hour=milestone.hour, minute=milestone.minute)

            if now < deadline:
                continue

            completed_before_deadline = self._db.count_workouts_between(week_start, deadline)
            if completed_before_deadline >= milestone.required_workouts:
                continue

            await bot.send_message(
                chat_id=self._config.allowed_user_id,
                text=(
                    f"Nudge: You haven't completed workout #{milestone.milestone} by "
                    f"{milestone.label}.\n"
                    f"{self._nudge_focus_text(now)}\n"
                    "Tap I trained and log now."
                ),
                reply_markup=self._reminder_keyboard(),
            )
            self._db.mark_weekly_nudge_sent(week_start_date, milestone.milestone)

    def schedule_weekly_nudges(self) -> None:
        # Runs every 5 minutes so missed/restarted runs still catch deadline nudges.
        self.app.job_queue.run_repeating(
            self.check_weekly_deadline_nudges,
            interval=300,
            first=10,
            name="weekly_deadline_nudges",
        )

    def schedule_morning_greeting(self) -> None:
        self.app.job_queue.run_daily(
            self.send_morning_greeting,
            time=time(hour=8, minute=0, tzinfo=ZoneInfo("America/Los_Angeles")),
            name="morning_greeting_pacific",
        )

    def run(self) -> None:
        self.schedule_weekly_nudges()
        self.schedule_morning_greeting()
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)
