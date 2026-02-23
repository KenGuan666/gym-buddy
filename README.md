# Gym Supervisor (Telegram)

A local Telegram bot that:
- Tracks your goal of **3 workouts per week**
- Nudges you only if you're behind deadlines:
  - Workout 1 by Tuesday 8:00 PM
  - Workout 2 by Thursday 8:00 PM
  - Workout 3 by Sunday 4:00 PM
- Logs workouts from button-guided flows (single or multi-message)
- Stores each set entry with **workout type + reps + weight (lb)**
- Maps workout moves to body areas (chest, back, legs, etc.) in SQLite
- Logs snoozes/skips
- Generates charts for workouts and snoozes

## 1) Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env`:
- `TELEGRAM_BOT_TOKEN`: from `@BotFather`
- `TELEGRAM_USER_ID`: your numeric Telegram user id
- `OPENAI_API_KEY`: used for daily morning quote generation
- `TELEGRAM_WEBHOOK_SECRET`: shared secret for Telegram webhook verification
- `CRON_SECRET`: secret used by Vercel cron endpoint authorization
- `SNOOZE_MINUTES`: delay after pressing snooze

## 2) Run bot

```bash
python main.py bot
```

Telegram commands:
- `/start`
- `/log <workout type> <weight>x<reps> ...` for quick one-message log
- `/log` to start guided multi-message log
- `/remindme` to trigger a check-in now
- `/status` to view weekly and all-time stats
- `/summary <week|month|quarter>` to view set breakdowns by workout type and body area
- `/summary_week`, `/summary_month`, `/summary_quarter` as quick aliases
- On bot startup, it pushes a clickable menu with `I trained`, `summary_week`, `summary_month`
- Every day at **8:00 AM Pacific Time**, it sends a morning greeting with a generated motivating quote and the same menu buttons

## 3) Workout logging behavior

- Tap `I trained`.
- Send entries in one message (`bench press 20x8, 30x8`) or multiple messages.
- `lb` is optional in each set (`bench press 20lb x8, 30lbx8`).
- Tap `Undo Last Entry` to remove your latest update.
- Tap `Finish Workout` when done.
- All messages in that draft are saved as **one workout**.
- After saving, the bot shows set totals by body area for that workout.

## 4) Generate charts

```bash
python main.py charts
```

Outputs are written to `charts/`:
- `daily_sets.png`
- `daily_snoozes.png`
- `workout_vs_snooze.png`

## 5) Notes

- Data is stored in SQLite at `DB_PATH` (default: `data/gym_supervisor.db`).
- Bot only accepts logs from `TELEGRAM_USER_ID`.
- Keep the bot process running.
- Weekly nudges are evaluated every 5 minutes and sent once per milestone if you are behind.

## 6) Deploy on Vercel (Webhook mode)

Important:
- `python main.py bot` is for local polling only.
- On Vercel, use webhook + serverless functions in `api/`.
- SQLite is not durable on Vercel. Use a persistent hosted DB for production.

### A. Import project
1. Push this repo to GitHub.
2. In Vercel, create a new project from the repo.
3. Keep root directory as repository root.

### B. Set Vercel environment variables
Set these in Vercel Project Settings -> Environment Variables:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_USER_ID`
- `OPENAI_API_KEY`
- `TELEGRAM_WEBHOOK_SECRET`
- `CRON_SECRET`
- `DB_PATH` (for local/dev only with SQLite; use persistent DB config in production)

### C. Deploy
1. Trigger first deployment in Vercel.
2. Note your domain, e.g. `https://your-bot.vercel.app`.

### D. Register Telegram webhook
Run:

```bash
curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook" \
  -d "url=https://<your-bot-domain>/api/telegram_webhook" \
  -d "secret_token=<TELEGRAM_WEBHOOK_SECRET>"
```

Optional verification:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

### E. Morning greeting schedule
- `vercel.json` config runs `/api/morning_greeting` every hour.
- Endpoint only sends when current Pacific hour is 8, so DST remains correct.
- It requires either `CRON_SECRET` bearer auth (recommended) or Vercel cron header.
