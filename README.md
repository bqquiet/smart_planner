# 🗂 Smart Planner — Telegram Task Manager Bot

> A production-ready Telegram bot for managing tasks, deadlines, and productivity.
> Built as a junior+ portfolio pet project with clean architecture and real-world features.

**Author:** [@bqquiet](https://github.com/bqquiet)

---

## ✨ Features

| Feature | Description |
|---|---|
| 📋 Tasks | Add, view, edit, delete, mark as done |
| ⏰ Deadlines | Date/time per task, automatic overdue detection |
| 🔥 Priorities | low / medium / high — auto-sorted |
| 🏷 Categories | Work / Personal / Study / Health / Other |
| 🔁 Recurring | Daily / weekly / monthly auto-repeat |
| 🔍 Search | Full-text search in title and description |
| 🔔 Reminders | Automatic notifications before deadline |
| 📊 Stats | Done / active / overdue + productivity % by category |
| 📤 Export | Download all tasks as a formatted CSV |
| 🤖 AI | Parse tasks from free text, generate subtasks, suggest priority |
| 🏆 Gamification | XP system, levels, streaks (Stage 5) |

---

## 🏗 Architecture

```
smart_planner/
├── bot/
│   ├── handlers/
│   │   ├── commands.py      ← /start /help /add_task /list_tasks /today /search /stats /export /ai
│   │   ├── add_task.py      ← FSM dialog: title → description → priority → category → repeat → deadline
│   │   ├── edit_task.py     ← FSM dialog for editing any task field
│   │   ├── search.py        ← /search FSM
│   │   ├── ai_task.py       ← /ai FSM: free text → AI parse → confirm → save
│   │   ├── gamification.py  ← /profile /leaderboard
│   │   └── callbacks.py     ← all inline button handlers
│   ├── keyboards/inline.py  ← all InlineKeyboardMarkup builders
│   ├── states.py            ← FSM states
│   └── main.py              ← entry point (polling + webhook)
│
├── database/
│   ├── models.py            ← ORM models: User, Task, UserStats
│   └── db.py                ← async engine + session factory
│
├── services/
│   ├── task_service.py      ← CRUD, search, stats, CSV export
│   ├── reminder_service.py  ← APScheduler: reminders + overdue check
│   ├── ai_service.py        ← OpenAI / Groq integration
│   └── gamification_service.py ← XP, levels, streaks
│
├── migrations/              ← Alembic migrations
│   └── versions/
│
└── core/
    ├── config.py            ← AppConfig (dataclasses + dotenv)
    ├── constants.py         ← Enums + display maps
    └── utils.py             ← Helpers
```

### Design principles

- **Separation of concerns** — handlers never import SQLAlchemy; services never import aiogram
- **Dependency direction** — `bot → services → database`, never the reverse
- **Async-first** — SQLAlchemy async + aiosqlite/asyncpg + asyncio APScheduler
- **Graceful degradation** — AI features silently disable when `OPENAI_API_KEY` is absent
- **No hardcode** — all constants in `core/constants.py`, all config in `.env`

---

## 🚀 Quick Start

### 1. Clone and install

```bash
git clone https://github.com/bqquiet/smart_planner.git
cd smart_planner
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Get a Telegram Bot Token

Open [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.

### 3. Configure `.env`

```bash
cp .env.example .env
```

Minimum required:
```
BOT_TOKEN=your_token_here
```

Optional AI (any provider — see below):
```
OPENAI_API_KEY=sk-...
# or
GROQ_API_KEY=gsk_...
```

### 4. Run

```bash
python -m bot.main
```

The SQLite database is created automatically on first run.

---

## ⚙️ Environment Variables

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | **Required.** Token from BotFather |
| `DATABASE_URL` | `sqlite+aiosqlite:///smart_planner.db` | DB connection URL |
| `DB_ECHO` | `false` | Log all SQL queries |
| `REMINDER_MINUTES_BEFORE` | `60` | Minutes before deadline to send reminder |
| `OVERDUE_CHECK_INTERVAL` | `300` | Overdue check interval in seconds |
| `OPENAI_API_KEY` | — | OpenAI key (optional) |
| `GROQ_API_KEY` | — | Groq key — free alternative to OpenAI (optional) |
| `AI_PROVIDER` | `openai` | `openai` or `groq` |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model name |
| `WEBHOOK_HOST` | — | Production webhook URL (Railway/Render) |
| `ADMIN_IDS` | — | Comma-separated Telegram user IDs |

---

## 🤖 AI Providers

The bot supports two AI providers — both are optional. Without a key, all AI features are hidden.

### OpenAI (paid, best quality)
```
OPENAI_API_KEY=sk-...
AI_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini   # ~$0.0001 per task parse
```
Get a key: https://platform.openai.com/api-keys

### Groq (free tier available)
```
GROQ_API_KEY=gsk_...
AI_PROVIDER=groq
OPENAI_MODEL=llama-3.1-8b-instant
```
Get a free key: https://console.groq.com — generous free tier, very fast.

---

## 🚀 Deploy to Railway (free tier)

1. Push to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add PostgreSQL plugin
4. Set environment variables: `BOT_TOKEN`, `WEBHOOK_HOST`, optionally `OPENAI_API_KEY` or `GROQ_API_KEY`
5. Railway auto-runs: `alembic upgrade head && python -m bot.main`

---

## 🗄 PostgreSQL

Switch from SQLite to PostgreSQL with one line in `.env`:

```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/smart_planner
```

Run migrations:
```bash
alembic upgrade head
```

---

## 📦 Tech Stack

| Tech | Version | Role |
|---|---|---|
| Python | 3.12+ | Language |
| aiogram | 3.x | Telegram Bot framework |
| SQLAlchemy | 2.x | Async ORM |
| Alembic | 1.x | DB migrations |
| aiosqlite / asyncpg | — | DB drivers |
| APScheduler | 3.x | Background scheduler |
| OpenAI / Groq | — | AI task parsing |
| python-dotenv | — | Config management |

---

## 🛣 Roadmap

- [x] Task CRUD with deadlines and priorities
- [x] Categories and filters
- [x] Recurring tasks
- [x] Search
- [x] CSV export
- [x] AI task parsing (OpenAI + Groq)
- [x] AI subtask generation
- [x] PostgreSQL + Alembic migrations
- [x] Railway deployment
- [x] XP system and levels (Stage 5)
- [x] Streak tracking (Stage 5)
- [ ] Admin panel with user analytics
- [ ] Repeating reminders (not just once)
- [ ] Task sharing between users
- [ ] Google Calendar sync
- [ ] Voice message → task (Whisper API)
- [ ] Weekly AI productivity report

---

## 📄 License

MIT © [bqquiet](https://github.com/bqquiet)
