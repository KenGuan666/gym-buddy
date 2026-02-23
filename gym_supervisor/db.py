from __future__ import annotations

import psycopg
from dataclasses import dataclass
from datetime import date, datetime
import re
from zoneinfo import ZoneInfo
from psycopg.rows import dict_row

MOVE_BODY_AREA_SEED: list[tuple[str, str]] = [
    # Chest
    ("bench press", "chest"),
    ("barbell bench press", "chest"),
    ("dumbbell bench press", "chest"),
    ("incline bench press", "chest"),
    ("decline bench press", "chest"),
    ("incline dumbbell press", "chest"),
    ("decline dumbbell press", "chest"),
    ("machine chest press", "chest"),
    ("chest press", "chest"),
    ("smith machine bench press", "chest"),
    ("push up", "chest"),
    ("pushup", "chest"),
    ("weighted push up", "chest"),
    ("chest dip", "chest"),
    ("dips", "chest"),
    ("cable fly", "chest"),
    ("cable crossover", "chest"),
    ("pec deck", "chest"),
    ("pec fly", "chest"),
    ("dumbbell fly", "chest"),
    ("svend press", "chest"),
    # Back
    ("pull up", "back"),
    ("pullup", "back"),
    ("chin up", "back"),
    ("lat pulldown", "back"),
    ("wide grip lat pulldown", "back"),
    ("close grip lat pulldown", "back"),
    ("seated cable row", "back"),
    ("seated row", "back"),
    ("barbell row", "back"),
    ("bent over row", "back"),
    ("dumbbell row", "back"),
    ("single arm dumbbell row", "back"),
    ("pendlay row", "back"),
    ("t bar row", "back"),
    ("inverted row", "back"),
    ("chest supported row", "back"),
    ("face pull", "shoulders"),
    ("facepull", "shoulders"),
    ("straight arm pulldown", "back"),
    ("back extension", "back"),
    ("hyperextension", "back"),
    ("reverse hyper", "back"),
    ("good morning", "back"),
    ("rack pull", "back"),
    ("deadlift", "legs"),
    ("sumo deadlift", "back"),
    ("romanian deadlift", "back"),
    ("rdl", "back"),
    # Shoulders
    ("overhead press", "shoulders"),
    ("shoulder press", "shoulders"),
    ("barbell overhead press", "shoulders"),
    ("dumbbell shoulder press", "shoulders"),
    ("seated dumbbell press", "shoulders"),
    ("military press", "shoulders"),
    ("arnold press", "shoulders"),
    ("push press", "shoulders"),
    ("landmine press", "shoulders"),
    ("lateral raise", "shoulders"),
    ("side lateral raise", "shoulders"),
    ("front raise", "shoulders"),
    ("rear delt fly", "shoulders"),
    ("reverse fly", "shoulders"),
    ("upright row", "shoulders"),
    ("cable lateral raise", "shoulders"),
    ("shrug", "shoulders"),
    ("dumbbell shrug", "shoulders"),
    ("barbell shrug", "shoulders"),
    # Legs
    ("squat", "legs"),
    ("back squat", "legs"),
    ("front squat", "legs"),
    ("high bar squat", "legs"),
    ("low bar squat", "legs"),
    ("box squat", "legs"),
    ("pause squat", "legs"),
    ("goblet squat", "legs"),
    ("hack squat", "legs"),
    ("smith machine squat", "legs"),
    ("leg press", "legs"),
    ("leg extension", "legs"),
    ("leg curl", "legs"),
    ("seated leg curl", "legs"),
    ("lying leg curl", "legs"),
    ("nordic curl", "legs"),
    ("walking lunge", "legs"),
    ("lunge", "legs"),
    ("reverse lunge", "legs"),
    ("split squat", "legs"),
    ("bulgarian split squat", "legs"),
    ("step up", "legs"),
    ("pistol squat", "legs"),
    ("sissy squat", "legs"),
    ("calf raise", "legs"),
    ("standing calf raise", "legs"),
    ("seated calf raise", "legs"),
    ("donkey calf raise", "legs"),
    ("adductor machine", "legs"),
    ("abductor machine", "legs"),
    ("hip adduction", "legs"),
    ("hip abduction", "legs"),
    ("glute bridge", "legs"),
    ("hip thrust", "legs"),
    # Arms
    ("barbell curl", "arms"),
    ("dumbbell curl", "arms"),
    ("dumbell curl", "arms"),
    ("curl", "arms"),
    ("alternating dumbbell curl", "arms"),
    ("hammer curl", "arms"),
    ("preacher curl", "arms"),
    ("incline dumbbell curl", "arms"),
    ("concentration curl", "arms"),
    ("cable curl", "arms"),
    ("ez bar curl", "arms"),
    ("reverse curl", "arms"),
    ("tricep pushdown", "arms"),
    ("triceps pushdown", "arms"),
    ("pushdown", "arms"),
    ("rope pushdown", "arms"),
    ("overhead tricep extension", "arms"),
    ("overhead triceps extension", "arms"),
    ("skull crusher", "arms"),
    ("lying tricep extension", "arms"),
    ("close grip bench press", "arms"),
    ("close grip push up", "arms"),
    ("bench dip", "arms"),
    ("cable tricep extension", "arms"),
    ("tricep kickback", "arms"),
    ("triceps kickback", "arms"),
    ("wrist curl", "arms"),
    ("reverse wrist curl", "arms"),
    ("farmer carry", "arms"),
    # Core
    ("plank", "core"),
    ("side plank", "core"),
    ("crunch", "core"),
    ("sit up", "core"),
    ("v up", "core"),
    ("dead bug", "core"),
    ("hollow hold", "core"),
    ("mountain climber", "core"),
    ("russian twist", "core"),
    ("hanging leg raise", "core"),
    ("leg raise", "core"),
    ("ab wheel", "core"),
    ("ab rollout", "core"),
    ("cable crunch", "core"),
    ("pallof press", "core"),
    ("wood chop", "core"),
    ("back plank", "core"),
    ("bird dog", "core"),
    ("toes to bar", "core"),
    # Full body / athletic
    ("clean", "full_body"),
    ("power clean", "full_body"),
    ("hang clean", "full_body"),
    ("snatch", "full_body"),
    ("power snatch", "full_body"),
    ("clean and jerk", "full_body"),
    ("thruster", "full_body"),
    ("burpee", "full_body"),
    ("man maker", "full_body"),
    ("kettlebell swing", "full_body"),
    ("turkish get up", "full_body"),
    ("wall ball", "full_body"),
    ("sled push", "full_body"),
    ("sled pull", "full_body"),
    ("bear crawl", "full_body"),
    ("battle rope", "full_body"),
    # Cardio conditioning
    ("run", "cardio"),
    ("treadmill run", "cardio"),
    ("jog", "cardio"),
    ("sprint", "cardio"),
    ("bike", "cardio"),
    ("cycling", "cardio"),
    ("stationary bike", "cardio"),
    ("spin bike", "cardio"),
    ("row", "cardio"),
    ("rowing", "cardio"),
    ("erg row", "cardio"),
    ("jump rope", "cardio"),
    ("stairmaster", "cardio"),
    ("elliptical", "cardio"),
    ("ski erg", "cardio"),
]


@dataclass(frozen=True)
class WorkoutLog:
    logged_at: str
    sets: int
    note: str


class GymDB:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._init_db()

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _now_pacific_naive() -> datetime:
        return datetime.now(ZoneInfo("America/Los_Angeles")).replace(tzinfo=None)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workouts (
                    id BIGSERIAL PRIMARY KEY,
                    logged_at TEXT NOT NULL,
                    sets INTEGER NOT NULL,
                    note TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS workout_entries (
                    id BIGSERIAL PRIMARY KEY,
                    workout_id BIGINT NOT NULL REFERENCES workouts(id),
                    workout_type TEXT NOT NULL DEFAULT '',
                    workout_display_name TEXT NOT NULL DEFAULT '',
                    reps INTEGER NOT NULL,
                    weight DOUBLE PRECISION NOT NULL,
                    logged_at TEXT NOT NULL,
                    source_text TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS snoozes (
                    id BIGSERIAL PRIMARY KEY,
                    logged_at TEXT NOT NULL,
                    reason TEXT DEFAULT ''
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS weekly_nudges (
                    id BIGSERIAL PRIMARY KEY,
                    week_start TEXT NOT NULL,
                    milestone INTEGER NOT NULL,
                    sent_at TEXT NOT NULL,
                    UNIQUE(week_start, milestone)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS move_body_areas (
                    move_key TEXT PRIMARY KEY,
                    display_label TEXT NOT NULL,
                    body_area TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "ALTER TABLE workout_entries ADD COLUMN IF NOT EXISTS workout_type TEXT NOT NULL DEFAULT ''"
            )
            conn.execute(
                "ALTER TABLE workout_entries ADD COLUMN IF NOT EXISTS workout_display_name TEXT NOT NULL DEFAULT ''"
            )
            self._seed_move_body_areas(conn)
            self._canonicalize_workout_entry_types(conn)

    @staticmethod
    def _normalize_workout_label(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip().lower())

    @staticmethod
    def _normalize_workout_type_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.strip().lower())

    def _seed_move_body_areas(self, conn: psycopg.Connection) -> None:
        rows = [
            (
                self._normalize_workout_type_key(move_name),
                self._normalize_workout_label(move_name),
                self._normalize_workout_label(body_area),
            )
            for move_name, body_area in MOVE_BODY_AREA_SEED
        ]
        conn.executemany(
            """
            INSERT INTO move_body_areas (move_key, display_label, body_area)
            VALUES (%s, %s, %s)
            ON CONFLICT(move_key) DO UPDATE SET
                display_label = excluded.display_label,
                body_area = excluded.body_area
            """,
            [row for row in rows if row[0]],
        )

    def _display_label_for_key(self, conn: psycopg.Connection, workout_key: str) -> str:
        row = conn.execute(
            "SELECT display_label FROM move_body_areas WHERE move_key = %s LIMIT 1",
            (workout_key,),
        ).fetchone()
        if row:
            return str(row["display_label"])
        return workout_key

    def _canonicalize_workout_entry_types(self, conn: psycopg.Connection) -> None:
        rows = conn.execute(
            "SELECT id, workout_type, workout_display_name FROM workout_entries"
        ).fetchall()
        updates: list[tuple[str, str, int]] = []
        for row in rows:
            row_id = int(row["id"])
            current_type = str(row["workout_type"])
            current_label = str(row["workout_display_name"])
            source_label = current_label or current_type
            canonical_key = self._normalize_workout_type_key(current_type or source_label)
            if not canonical_key:
                continue
            canonical_label = self._display_label_for_key(conn, canonical_key)
            if canonical_key != current_type or canonical_label != current_label:
                updates.append((canonical_key, canonical_label, row_id))
        if updates:
            conn.executemany(
                """
                UPDATE workout_entries
                SET workout_type = %s, workout_display_name = %s
                WHERE id = %s
                """,
                updates,
            )

    def _lookup_body_area(self, conn: psycopg.Connection, workout_type: str) -> str:
        key = self._normalize_workout_type_key(workout_type)
        if not key:
            return "unmapped"

        exact = conn.execute(
            "SELECT body_area FROM move_body_areas WHERE move_key = %s LIMIT 1",
            (key,),
        ).fetchone()
        if exact:
            return str(exact["body_area"])

        return "unmapped"

    def log_workout_with_entries(
        self,
        entries: list[tuple[str, int, float]],
        note: str = "",
    ) -> int:
        if not entries:
            raise ValueError("entries must not be empty")

        now = self._now_pacific_naive().isoformat(timespec="seconds")
        with self._connect() as conn:
            normalized_entries: list[tuple[str, str, int, float]] = []
            for workout_type, reps, weight in entries:
                workout_key = self._normalize_workout_type_key(workout_type)
                if not workout_key:
                    continue
                display_name = self._display_label_for_key(conn, workout_key) or self._normalize_workout_label(
                    workout_type
                )
                normalized_entries.append((workout_key, display_name, reps, weight))

            if not normalized_entries:
                raise ValueError("entries must include at least one valid workout type")

            cur = conn.execute(
                "INSERT INTO workouts (logged_at, sets, note) VALUES (%s, %s, %s) RETURNING id",
                (now, len(normalized_entries), note.strip()),
            )
            workout_id = int(cur.fetchone()["id"])

            conn.executemany(
                """
                INSERT INTO workout_entries (
                    workout_id, workout_type, workout_display_name, reps, weight, logged_at, source_text
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (
                        workout_id,
                        workout_key,
                        display_name,
                        reps,
                        weight,
                        now,
                        note.strip(),
                    )
                    for workout_key, display_name, reps, weight in normalized_entries
                ],
            )
            return workout_id

    def log_snooze(self, reason: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO snoozes (logged_at, reason) VALUES (%s, %s)",
                (self._now_pacific_naive().isoformat(timespec="seconds"), reason.strip()),
            )

    def recent_workouts(self, limit: int = 10) -> list[WorkoutLog]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT logged_at, sets, note
                FROM workouts
                ORDER BY logged_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()

        return [WorkoutLog(r["logged_at"], int(r["sets"]), r["note"]) for r in rows]

    def count_workouts_between(self, start: datetime, end: datetime) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS c
                FROM workouts
                WHERE logged_at >= %s AND logged_at < %s
                """,
                (
                    start.isoformat(timespec="seconds"),
                    end.isoformat(timespec="seconds"),
                ),
            ).fetchone()
        return int(row["c"])

    def count_workouts_this_week(self, week_start: datetime, week_end: datetime) -> int:
        return self.count_workouts_between(week_start, week_end)

    def summarize_sets_by_workout_type_between(
        self, start: datetime, end: datetime
    ) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT workout_type, MAX(workout_display_name) AS workout_display_name, COUNT(*) AS set_count
                FROM workout_entries
                WHERE logged_at >= %s AND logged_at < %s
                GROUP BY workout_type
                """,
                (
                    start.isoformat(timespec="seconds"),
                    end.isoformat(timespec="seconds"),
                ),
            ).fetchall()
        summary = {
            (
                str(row["workout_display_name"]).strip()
                or str(row["workout_type"]).strip()
            ): int(row["set_count"])
            for row in rows
            if str(row["workout_type"]).strip()
        }
        return dict(sorted(summary.items(), key=lambda item: (-item[1], item[0])))

    def summarize_sets_by_body_area_between(self, start: datetime, end: datetime) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT workout_type, COUNT(*) AS set_count
                FROM workout_entries
                WHERE logged_at >= %s AND logged_at < %s
                GROUP BY workout_type
                """,
                (
                    start.isoformat(timespec="seconds"),
                    end.isoformat(timespec="seconds"),
                ),
            ).fetchall()

            totals: dict[str, int] = {}
            for row in rows:
                body_area = self._lookup_body_area(conn, str(row["workout_type"]))
                totals[body_area] = totals.get(body_area, 0) + int(row["set_count"])
        return dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))

    def period_workout_summary(self, start: datetime, end: datetime) -> dict[str, object]:
        by_workout_type = self.summarize_sets_by_workout_type_between(start, end)
        by_body_area = self.summarize_sets_by_body_area_between(start, end)
        return {
            "workouts": self.count_workouts_between(start, end),
            "total_sets": sum(by_workout_type.values()),
            "by_workout_type": by_workout_type,
            "by_body_area": by_body_area,
        }

    def weekly_nudge_sent(self, week_start: date, milestone: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM weekly_nudges
                WHERE week_start = %s AND milestone = %s
                LIMIT 1
                """,
                (week_start.isoformat(), milestone),
            ).fetchone()
        return row is not None

    def mark_weekly_nudge_sent(self, week_start: date, milestone: int) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO weekly_nudges (week_start, milestone, sent_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (week_start, milestone) DO NOTHING
                """,
                (
                    week_start.isoformat(),
                    milestone,
                    self._now_pacific_naive().isoformat(timespec="seconds"),
                ),
            )

    def stats_summary(self) -> dict[str, int | float]:
        with self._connect() as conn:
            workout_count = conn.execute("SELECT COUNT(*) AS c FROM workouts").fetchone()["c"]
            snooze_count = conn.execute("SELECT COUNT(*) AS c FROM snoozes").fetchone()["c"]
            total_sets = conn.execute("SELECT COALESCE(SUM(sets), 0) AS s FROM workouts").fetchone()["s"]
            total_volume = conn.execute(
                "SELECT COALESCE(SUM(reps * weight), 0) AS v FROM workout_entries"
            ).fetchone()["v"]

        avg_sets = (total_sets / workout_count) if workout_count else 0.0
        avg_volume = (total_volume / workout_count) if workout_count else 0.0
        return {
            "workout_count": int(workout_count),
            "snooze_count": int(snooze_count),
            "total_sets": int(total_sets),
            "avg_sets": float(avg_sets),
            "total_volume": float(total_volume),
            "avg_volume": float(avg_volume),
        }

    def summarize_sets_by_body_area_for_workout(self, workout_id: int) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT workout_type, COUNT(*) AS set_count
                FROM workout_entries
                WHERE workout_id = %s
                GROUP BY workout_type
                """,
                (workout_id,),
            ).fetchall()

            totals: dict[str, int] = {}
            for row in rows:
                body_area = self._lookup_body_area(conn, str(row["workout_type"]))
                totals[body_area] = totals.get(body_area, 0) + int(row["set_count"])

        return dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))
