# 🗂 Smart Planner — Telegram Task Manager Bot

> Pet-project рівня junior+ для портфоліо. Повнофункціональний Telegram-бот для керування задачами з дедлайнами, пріоритетами та автоматичними нагадуваннями.

---

## ✨ Функціонал

| Категорія | Що вміє |
|---|---|
| 📋 Задачі | Додавати, переглядати, видаляти, позначати виконаними |
| ⏰ Дедлайни | Дата/час на кожну задачу, автоматичний статус overdue |
| 🔥 Пріоритети | low / medium / high — сортування за важливістю |
| 🔔 Нагадування | Автоматичні повідомлення за 60 хв до дедлайну |
| 📊 Статистика | Виконано / активних / прострочених / % продуктивності |
| 🎨 UX | Inline-кнопки, FSM-діалог для додавання задач |

---

## 🏗 Архітектура проєкту

```
smart_planner/
├── bot/                        # Telegram-специфічний шар
│   ├── handlers/
│   │   ├── commands.py         # /start, /help, /add_task, /list_tasks, /stats
│   │   ├── add_task.py         # FSM-діалог: назва → опис → пріоритет → дедлайн
│   │   └── callbacks.py        # Всі inline-кнопки
│   ├── keyboards/
│   │   └── inline.py           # Всі InlineKeyboardMarkup-будівники
│   ├── states.py               # FSM-стани (AddTaskFSM)
│   └── main.py                 # 🚀 Точка входу
│
├── database/                   # Persistence шар
│   ├── models.py               # SQLAlchemy ORM: User, Task
│   └── db.py                   # Engine, session factory, init_db()
│
├── services/                   # Бізнес-логіка (не залежить від aiogram)
│   ├── task_service.py         # CRUD задач, статистика, overdue-refresh
│   └── reminder_service.py     # APScheduler jobs: нагадування + overdue-check
│
├── core/                       # Shared utilities
│   ├── config.py               # AppConfig (dataclasses + dotenv)
│   ├── constants.py            # Enums: Priority, TaskStatus; emoji-мапи
│   └── utils.py                # format_deadline, deadline_delta_label, тощо
│
├── requirements.txt
├── .env.example
└── README.md
```

### Принципи архітектури

- **Separation of concerns** — handlers не знають про SQL, services не знають про aiogram
- **Dependency direction** — `bot → services → database`, ніколи навпаки
- **No hardcode** — всі константи в `core/constants.py`, налаштування в `.env`
- **Async-first** — SQLAlchemy async + aiosqlite + asyncio APScheduler

---

## 🚀 Запуск

### 1. Клонувати та встановити залежності

```bash
git clone https://github.com/yourname/smart_planner.git
cd smart_planner
python -m venv venv
source venv/bin/activate        # Linux/Mac
# або: venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

### 2. Отримати Telegram Bot Token

1. Відкрий [@BotFather](https://t.me/BotFather) у Telegram
2. Відправ `/newbot`, вкажи ім'я та username бота
3. Скопіюй отриманий токен

### 3. Налаштувати `.env`

```bash
cp .env.example .env
```

Відкрий `.env` та встав свій токен:
```
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxyz
```

### 4. Запустити бота

```bash
python bot/main.py
```

При першому запуску автоматично створюється SQLite база даних `smart_planner.db`.

---

## 💬 Приклади використання

### Додати задачу через FSM-діалог

```
/add_task
→ Бот: Введи назву задачі:
→ Ти:  Підготувати презентацію
→ Бот: Введи опис або /skip:
→ Ти:  /skip
→ Бот: [🟢 Низький] [🟡 Середній] [🔴 Високий]
→ Ти:  [натискаєш 🔴 Високий]
→ Бот: Введи дедлайн (ДД.ММ.РРРР ГГ:ХХ) або [⏭ Пропустити]:
→ Ти:  25.12.2025 14:00
→ Бот: 🎉 Задача створена!
       📌 Підготувати презентацію
       🎯 Пріоритет: 🔴 Високий
       📅 Дедлайн: 25.12.2025 14:00
```

### Перегляд задач

```
/list_tasks
→ Бот показує список з кнопками:
  [🔴 Підготувати презентацію]
  [🟡 Купити продукти       ]
  [➕ Нова задача] [🏠 Меню]
```

### Автоматичне нагадування (через 60 хв до дедлайну)

```
⏰ Нагадування!

Задача Підготувати презентацію наближається до дедлайну.
📅 Дедлайн: 25.12.2025 14:00 (через 55 хв)
```

### Статистика

```
/stats
→ 📊 Твоя статистика
   📌 Всього задач: 8
   ✅ Виконано: 5
   🔵 Активних: 2
   ⚠️ Прострочених: 1
   🏆 Продуктивність: 63%
   ▓▓▓▓▓▓░░░░
```

---

## ⚙️ PostgreSQL (замість SQLite)

В `.env` замінити:
```
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/smart_planner
```

Додати залежність:
```bash
pip install asyncpg
```

---

## 🔧 Змінні оточення

| Змінна | За замовчуванням | Опис |
|---|---|---|
| `BOT_TOKEN` | — | **Обов'язковий.** Токен від BotFather |
| `DATABASE_URL` | `sqlite+aiosqlite:///smart_planner.db` | URL бази даних |
| `DB_ECHO` | `false` | Логувати SQL-запити |
| `REMINDER_MINUTES_BEFORE` | `60` | За скільки хвилин надсилати нагадування |
| `OVERDUE_CHECK_INTERVAL` | `300` | Інтервал перевірки прострочених (секунди) |
| `ADMIN_IDS` | — | Telegram ID адмінів через кому |

---

## 🛣 Roadmap / Можливі розширення

- [ ] **AI-пріоритизація** — інтеграція з OpenAI для авто-розстановки пріоритетів
- [ ] **Повторювані задачі** — щодня / щотижня / щомісяця
- [ ] **Категорії та теги** — фільтрація за проєктом
- [ ] **Webhook mode** — для production-деплою на VPS
- [ ] **PostgreSQL + Alembic** — міграції для production
- [ ] **Адмін-панель** — статистика по всіх користувачах
- [ ] **Експорт** — вивантаження задач у CSV/PDF

---

## 📦 Стек технологій

| Технологія | Версія | Роль |
|---|---|---|
| Python | 3.10+ | Мова |
| aiogram | 3.x | Telegram Bot framework |
| SQLAlchemy | 2.x | ORM (async) |
| aiosqlite | 0.20 | Async SQLite driver |
| APScheduler | 3.x | Планувальник нагадувань |
| python-dotenv | 1.x | Завантаження .env |
