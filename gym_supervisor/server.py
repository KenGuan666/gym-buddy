from __future__ import annotations

from telegram import Update

from gym_supervisor.bot import BotConfig, GymSupervisorBot
from gym_supervisor.config import load_settings
from gym_supervisor.db import GymDB

_bot_instance: GymSupervisorBot | None = None
_initialized = False


def get_bot_instance() -> GymSupervisorBot:
    global _bot_instance
    if _bot_instance is None:
        settings = load_settings()
        db = GymDB(settings.db_path)
        _bot_instance = GymSupervisorBot(
            token=settings.telegram_bot_token,
            db=db,
            config=BotConfig(
                allowed_user_id=settings.telegram_user_id,
                openai_api_key=settings.openai_api_key,
                reminder_hour=settings.reminder_hour,
                reminder_minute=settings.reminder_minute,
                snooze_minutes=settings.snooze_minutes,
                startup_greeting_enabled=False,
            ),
        )
    return _bot_instance


async def ensure_initialized() -> GymSupervisorBot:
    global _initialized
    bot = get_bot_instance()
    if not _initialized:
        await bot.app.initialize()
        _initialized = True
    return bot


async def process_telegram_update(payload: dict) -> None:
    bot = await ensure_initialized()
    update = Update.de_json(payload, bot.app.bot)
    await bot.app.process_update(update)


async def send_morning_greeting_once() -> None:
    bot = await ensure_initialized()
    await bot.send_morning_greeting_now(bot.app.bot)
