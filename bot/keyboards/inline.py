from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from core.config import settings
from core.constants import (
    Priority, PRIORITY_LABEL, PRIORITY_EMOJI,
    TaskStatus, STATUS_LABEL,
    Category, CATEGORY_LABEL, CATEGORY_EMOJI,
    RepeatInterval, REPEAT_LABEL, REPEAT_EMOJI,
)
from database.models import Task


def main_menu_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Мої задачі", callback_data="list_tasks")
    builder.button(text="➕ Додати задачу", callback_data="add_task_start")
    builder.button(text="📅 Сьогодні", callback_data="today_tasks")
    builder.button(text="🔍 Пошук", callback_data="search_start")
    if settings.ai.enabled:
        builder.button(text="🤖 AI задача", callback_data="ai_task_start")
    builder.button(text="📊 Статистика", callback_data="stats")
    builder.button(text="🏅 Профіль", callback_data="profile")
    builder.button(text="📤 Експорт CSV", callback_data="export_csv")
    builder.adjust(2, 2, 1 if settings.ai.enabled else 0, 2, 1)
    return builder.as_markup()


def task_list_keyboard(tasks: list[Task]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for task in tasks:
        p_icon = PRIORITY_EMOJI.get(task.priority, "")
        s_icon = "✅ " if task.status == "done" else "⚠️ " if task.status == "overdue" else ""
        c_icon = CATEGORY_EMOJI.get(task.category, "") + " " if task.category else ""
        r_icon = "🔁 " if task.repeat else ""
        builder.button(
            text=f"{p_icon}{s_icon}{c_icon}{r_icon}{task.title[:25]}",
            callback_data=f"task_detail:{task.id}",
        )
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="🔍 Фільтр", callback_data="show_filter"),
        InlineKeyboardButton(text="➕ Нова", callback_data="add_task_start"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def task_detail_keyboard(task: Task) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if task.status != TaskStatus.DONE:
        builder.button(text="✅ Виконано", callback_data=f"done:{task.id}")
    builder.button(text="✏️ Редагувати", callback_data=f"edit_task:{task.id}")
    if settings.ai.enabled:
        builder.button(text="🤖 Підзадачі AI", callback_data=f"ai_subtasks:{task.id}")
    builder.button(text="🗑 Видалити", callback_data=f"delete_confirm:{task.id}")
    builder.button(text="⬅️ Назад", callback_data="list_tasks")
    builder.adjust(2, 2, 1)
    return builder.as_markup()


def edit_field_keyboard(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Назва", callback_data=f"edit_field:{task_id}:title")
    builder.button(text="📄 Опис", callback_data=f"edit_field:{task_id}:description")
    builder.button(text="🎯 Пріоритет", callback_data=f"edit_field:{task_id}:priority")
    builder.button(text="🏷 Категорія", callback_data=f"edit_field:{task_id}:category")
    builder.button(text="🔁 Повтор", callback_data=f"edit_field:{task_id}:repeat")
    builder.button(text="📅 Дедлайн", callback_data=f"edit_field:{task_id}:deadline")
    builder.button(text="❌ Скасувати", callback_data=f"task_detail:{task_id}")
    builder.adjust(2, 2, 2, 1)
    return builder.as_markup()


def delete_confirm_keyboard(task_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Так, видалити", callback_data=f"delete_ok:{task_id}")
    builder.button(text="❌ Скасувати", callback_data=f"task_detail:{task_id}")
    builder.adjust(2)
    return builder.as_markup()


def priority_keyboard(prefix: str = "set_priority") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in Priority:
        builder.button(text=f"{PRIORITY_EMOJI[p]}{PRIORITY_LABEL[p]}", callback_data=f"{prefix}:{p.value}")
    builder.adjust(3)
    return builder.as_markup()


def category_keyboard(prefix: str = "set_category") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for c in Category:
        builder.button(text=f"{CATEGORY_EMOJI[c]} {CATEGORY_LABEL[c]}", callback_data=f"{prefix}:{c.value}")
    builder.button(text="⏭ Пропустити", callback_data=f"{prefix}:skip")
    builder.adjust(2)
    return builder.as_markup()


def repeat_keyboard(prefix: str = "set_repeat") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for r in RepeatInterval:
        builder.button(text=f"{REPEAT_EMOJI[r]} {REPEAT_LABEL[r]}", callback_data=f"{prefix}:{r.value}")
    builder.button(text="🚫 Без повтору", callback_data=f"{prefix}:none")
    builder.adjust(3, 1)
    return builder.as_markup()


def skip_deadline_keyboard(prefix: str = "skip_deadline") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустити дедлайн", callback_data=prefix)
    return builder.as_markup()


def filter_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📋 Всі", callback_data="filter:all")
    for status in TaskStatus:
        builder.button(text=STATUS_LABEL[status], callback_data=f"filter:{status.value}")
    builder.button(text="🔁 Повторювані", callback_data="filter:repeat")
    builder.button(text="━━ За категорією ━━", callback_data="noop")
    for cat in Category:
        builder.button(text=f"{CATEGORY_EMOJI[cat]} {CATEGORY_LABEL[cat]}", callback_data=f"filter_cat:{cat.value}")
    builder.button(text="❌ Закрити", callback_data="list_tasks")
    builder.adjust(2, 2, 1, 1, 2, 2, 1, 1)
    return builder.as_markup()
