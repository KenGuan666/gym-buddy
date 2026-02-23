from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    telegram_user_id: int
    openai_api_key: str
    reminder_hour: int
    reminder_minute: int
    snooze_minutes: int
    db_path: str


def load_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    user_id = os.getenv("TELEGRAM_USER_ID", "").strip()

    if not token:
        raise ValueError("Missing TELEGRAM_BOT_TOKEN in .env")
    if not user_id.isdigit():
        raise ValueError("TELEGRAM_USER_ID must be a numeric Telegram user ID")

    return Settings(
        telegram_bot_token=token,
        telegram_user_id=int(user_id),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        reminder_hour=int(os.getenv("REMINDER_HOUR", "18")),
        reminder_minute=int(os.getenv("REMINDER_MINUTE", "0")),
        snooze_minutes=int(os.getenv("SNOOZE_MINUTES", "60")),
        db_path=os.getenv("DB_PATH", "data/gym_supervisor.db"),
    )
