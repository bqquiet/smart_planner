from enum import StrEnum


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TaskStatus(StrEnum):
    ACTIVE = "active"
    DONE = "done"
    OVERDUE = "overdue"


class Category(StrEnum):
    WORK = "work"
    PERSONAL = "personal"
    STUDY = "study"
    HEALTH = "health"
    OTHER = "other"


class RepeatInterval(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


# ─── Display maps ──────────────────────────────────────────────────────────────

PRIORITY_EMOJI: dict[str, str] = {
    Priority.LOW: "🟢 ", Priority.MEDIUM: "🟡 ", Priority.HIGH: "🔴 ",
}
STATUS_EMOJI: dict[str, str] = {
    TaskStatus.ACTIVE: "", TaskStatus.DONE: "✅ ", TaskStatus.OVERDUE: "⚠️ ",
}
PRIORITY_LABEL: dict[str, str] = {
    Priority.LOW: "Низький", Priority.MEDIUM: "Середній", Priority.HIGH: "Високий",
}
STATUS_LABEL: dict[str, str] = {
    TaskStatus.ACTIVE: "Активна", TaskStatus.DONE: "Виконана", TaskStatus.OVERDUE: "Прострочена",
}
CATEGORY_EMOJI: dict[str, str] = {
    Category.WORK: "💼", Category.PERSONAL: "🏠",
    Category.STUDY: "📚", Category.HEALTH: "💪", Category.OTHER: "📌",
}
CATEGORY_LABEL: dict[str, str] = {
    Category.WORK: "Робота", Category.PERSONAL: "Особисте",
    Category.STUDY: "Навчання", Category.HEALTH: "Здоров'я", Category.OTHER: "Інше",
}
REPEAT_EMOJI: dict[str, str] = {
    RepeatInterval.DAILY: "📆", RepeatInterval.WEEKLY: "🗓", RepeatInterval.MONTHLY: "📅",
}
REPEAT_LABEL: dict[str, str] = {
    RepeatInterval.DAILY: "Щодня", RepeatInterval.WEEKLY: "Щотижня", RepeatInterval.MONTHLY: "Щомісяця",
}
PRIORITY_WEIGHT: dict[str, int] = {
    Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2,
}
