import argparse

from gym_supervisor.bot import BotConfig, GymSupervisorBot
from gym_supervisor.config import load_settings
from gym_supervisor.db import GymDB
from gym_supervisor.visualize import generate_charts


def run_bot() -> None:
    settings = load_settings()
    db = GymDB(settings.database_url)
    bot = GymSupervisorBot(
        token=settings.telegram_bot_token,
        db=db,
        config=BotConfig(
            allowed_user_id=settings.telegram_user_id,
            openai_api_key=settings.openai_api_key,
            reminder_hour=settings.reminder_hour,
            reminder_minute=settings.reminder_minute,
            snooze_minutes=settings.snooze_minutes,
        ),
    )
    bot.run()


def run_charts() -> None:
    settings = load_settings()
    files = generate_charts(settings.database_url)
    if not files:
        print("No data yet. Log some workouts/snoozes first.")
        return
    print("Generated charts:")
    for file in files:
        print(f"- {file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gym supervisor bot and analytics")
    parser.add_argument(
        "command",
        nargs="?",
        default="bot",
        choices=["bot", "charts"],
        help="Run mode: bot (default) or charts",
    )
    args = parser.parse_args()

    if args.command == "charts":
        run_charts()
    else:
        run_bot()
