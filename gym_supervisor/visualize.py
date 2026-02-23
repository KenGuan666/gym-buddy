from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


def _read_table(db_path: str, table: str) -> pd.DataFrame:
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    if not df.empty and "logged_at" in df.columns:
        df["logged_at"] = pd.to_datetime(df["logged_at"])
    return df


def generate_charts(db_path: str, out_dir: str = "charts") -> list[str]:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    sns.set_theme(style="whitegrid")

    workouts = _read_table(db_path, "workouts")
    snoozes = _read_table(db_path, "snoozes")

    output_files: list[str] = []

    if not workouts.empty:
        daily_sets = (
            workouts.assign(day=workouts["logged_at"].dt.date)
            .groupby("day", as_index=False)["sets"]
            .sum()
        )

        plt.figure(figsize=(10, 5))
        sns.lineplot(data=daily_sets, x="day", y="sets", marker="o")
        plt.title("Daily Total Sets")
        plt.xlabel("Date")
        plt.ylabel("Total Sets")
        plt.xticks(rotation=30)
        plt.tight_layout()
        sets_file = str(Path(out_dir) / "daily_sets.png")
        plt.savefig(sets_file, dpi=150)
        plt.close()
        output_files.append(sets_file)

    if not snoozes.empty:
        daily_snoozes = (
            snoozes.assign(day=snoozes["logged_at"].dt.date)
            .groupby("day", as_index=False)["id"]
            .count()
            .rename(columns={"id": "snoozes"})
        )

        plt.figure(figsize=(10, 5))
        sns.barplot(data=daily_snoozes, x="day", y="snoozes", color="#d16b5c")
        plt.title("Daily Snoozes / Skips")
        plt.xlabel("Date")
        plt.ylabel("Snoozes")
        plt.xticks(rotation=30)
        plt.tight_layout()
        snooze_file = str(Path(out_dir) / "daily_snoozes.png")
        plt.savefig(snooze_file, dpi=150)
        plt.close()
        output_files.append(snooze_file)

    if not workouts.empty or not snoozes.empty:
        workout_days = (
            workouts.assign(day=workouts["logged_at"].dt.date)
            .groupby("day", as_index=False)["id"]
            .count()
            .rename(columns={"id": "workouts"})
            if not workouts.empty
            else pd.DataFrame(columns=["day", "workouts"])
        )

        snooze_days = (
            snoozes.assign(day=snoozes["logged_at"].dt.date)
            .groupby("day", as_index=False)["id"]
            .count()
            .rename(columns={"id": "snoozes"})
            if not snoozes.empty
            else pd.DataFrame(columns=["day", "snoozes"])
        )

        merged = pd.merge(workout_days, snooze_days, on="day", how="outer").fillna(0)
        if not merged.empty:
            merged = merged.sort_values("day")
            plt.figure(figsize=(10, 5))
            plt.plot(merged["day"], merged["workouts"], marker="o", label="Workout Logs")
            plt.plot(merged["day"], merged["snoozes"], marker="o", label="Snoozes")
            plt.title("Workout vs Snooze Trend")
            plt.xlabel("Date")
            plt.ylabel("Count")
            plt.legend()
            plt.xticks(rotation=30)
            plt.tight_layout()
            trend_file = str(Path(out_dir) / "workout_vs_snooze.png")
            plt.savefig(trend_file, dpi=150)
            plt.close()
            output_files.append(trend_file)

    return output_files
