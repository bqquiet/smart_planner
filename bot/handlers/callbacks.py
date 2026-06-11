"""
Callback query handlers — all inline button interactions.
"""
import logging
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import (
    main_menu_keyboard, task_list_keyboard, task_detail_keyboard,
    delete_confirm_keyboard, filter_keyboard,
)
from bot.states import AddTaskFSM, SearchFSM
from database.db import get_session
from services import (
    get_or_create_user, list_tasks, list_tasks_today,
    get_task, mark_done, delete_task, get_user_stats, export_tasks_csv,
)
from core.utils import format_deadline, deadline_delta_label
from core.constants import (
    PRIORITY_LABEL, PRIORITY_EMOJI, STATUS_LABEL,
    CATEGORY_LABEL, CATEGORY_EMOJI, REPEAT_LABEL, REPEAT_EMOJI,
)

logger = logging.getLogger(__name__)
router = Router(name="callbacks")


async def _get_user(session, callback: CallbackQuery):
    return await get_or_create_user(
        session, telegram_id=callback.from_user.id, first_name=callback.from_user.first_name
    )


@router.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("🏠 <b>Головне меню</b>", parse_mode="HTML", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "list_tasks")
async def cb_list_tasks(callback: CallbackQuery) -> None:
    async with get_session() as session:
        user = await _get_user(session, callback)
        tasks = await list_tasks(session, user.id)
    if not tasks:
        await callback.message.edit_text("📭 Задач немає.", reply_markup=main_menu_keyboard())
        await callback.answer()
        return
    await callback.message.edit_text(
        f"📋 <b>Твої задачі</b> ({len(tasks)} шт.):", parse_mode="HTML",
        reply_markup=task_list_keyboard(tasks),
    )
    await callback.answer()


@router.callback_query(F.data == "today_tasks")
async def cb_today_tasks(callback: CallbackQuery) -> None:
    async with get_session() as session:
        user = await _get_user(session, callback)
        tasks = await list_tasks_today(session, user.id)
    if not tasks:
        await callback.message.edit_text(
            "🎉 На сьогодні задач немає!", reply_markup=main_menu_keyboard()
        )
        await callback.answer()
        return
    await callback.message.edit_text(
        f"📅 <b>Сьогодні</b> ({len(tasks)} шт.):", parse_mode="HTML",
        reply_markup=task_list_keyboard(tasks),
    )
    await callback.answer()


@router.callback_query(F.data == "search_start")
async def cb_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchFSM.waiting_query)
    await callback.message.edit_text("🔍 Введи текст для пошуку:")
    await callback.answer()


@router.callback_query(F.data == "show_filter")
async def cb_show_filter(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🔍 <b>Фільтрувати:</b>", parse_mode="HTML", reply_markup=filter_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data.startswith("filter:"))
async def cb_filter_tasks(callback: CallbackQuery) -> None:
    status_filter = callback.data.split(":")[1]

    async with get_session() as session:
        user = await _get_user(session, callback)
        if status_filter == "repeat":
            from sqlalchemy import select
            from database.models import Task
            result = await session.execute(
                select(Task).where(Task.user_id == user.id, Task.repeat.isnot(None))
            )
            tasks = result.scalars().all()
            label = "🔁 Повторювані"
        else:
            filter_arg = None if status_filter == "all" else status_filter
            tasks = await list_tasks(session, user.id, status_filter=filter_arg)
            label = "Всі" if status_filter == "all" else STATUS_LABEL.get(status_filter, status_filter)

    if not tasks:
        await callback.answer(f"Немає задач у «{label}»", show_alert=True)
        return
    await callback.message.edit_text(
        f"📋 <b>{label}</b> ({len(tasks)} шт.):", parse_mode="HTML",
        reply_markup=task_list_keyboard(tasks),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("filter_cat:"))
async def cb_filter_category(callback: CallbackQuery) -> None:
    cat = callback.data.split(":")[1]
    async with get_session() as session:
        user = await _get_user(session, callback)
        tasks = await list_tasks(session, user.id, category_filter=cat)
    label = f"{CATEGORY_EMOJI.get(cat,'')} {CATEGORY_LABEL.get(cat, cat)}"
    if not tasks:
        await callback.answer(f"Немає задач у «{label}»", show_alert=True)
        return
    await callback.message.edit_text(
        f"📋 <b>{label}</b> ({len(tasks)} шт.):", parse_mode="HTML",
        reply_markup=task_list_keyboard(tasks),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("task_detail:"))
async def cb_task_detail(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        user = await _get_user(session, callback)
        task = await get_task(session, task_id, user.id)
    if task is None:
        await callback.answer("❌ Задачу не знайдено.", show_alert=True)
        return

    deadline_str = format_deadline(task.deadline)
    delta = deadline_delta_label(task.deadline) if task.deadline else ""

    lines = [
        f"📌 <b>{task.title}</b>  🆔<code>{task.id}</code>\n",
        f"📝 {task.description or '—'}\n",
        f"🎯 {PRIORITY_EMOJI.get(task.priority,'')}{PRIORITY_LABEL.get(task.priority,'')}",
        f"📊 {STATUS_LABEL.get(task.status,'')}",
    ]
    if task.category:
        lines.append(f"🏷 {CATEGORY_EMOJI.get(task.category,'')} {CATEGORY_LABEL.get(task.category,'')}")
    if task.repeat:
        lines.append(f"🔁 {REPEAT_EMOJI.get(task.repeat,'')} {REPEAT_LABEL.get(task.repeat,'')}")
    dl_line = f"📅 {deadline_str}"
    if delta:
        dl_line += f"  <i>({delta})</i>"
    lines.append(dl_line)

    await callback.message.edit_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=task_detail_keyboard(task)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("done:"))
async def cb_done(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        user = await _get_user(session, callback)
        task = await mark_done(session, task_id, user.id)
    if task is None:
        await callback.answer("❌ Задачу не знайдено.", show_alert=True)
        return

    # Award XP
    from services.gamification_service import record_task_done
    from bot.handlers.gamification import format_xp_notification
    from core.utils import utc_now
    was_on_time = task.deadline is None or task.deadline >= utc_now()
    async with get_session() as session2:
        xp_result = await record_task_done(session2, task.user_id, was_on_time)

    note = " (наступна створена 🔁)" if task.repeat else ""
    await callback.answer(f"✅ Виконано!{note}")

    xp_msg = format_xp_notification(xp_result)
    if xp_result.get("level_up"):
        await callback.message.answer(xp_msg, parse_mode="HTML")

    await cb_task_detail(callback)


@router.callback_query(F.data.startswith("delete_confirm:"))
async def cb_delete_confirm(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    await callback.message.edit_reply_markup(reply_markup=delete_confirm_keyboard(task_id))
    await callback.answer()


@router.callback_query(F.data.startswith("delete_ok:"))
async def cb_delete_ok(callback: CallbackQuery) -> None:
    task_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        user = await _get_user(session, callback)
        deleted = await delete_task(session, task_id, user.id)
    if not deleted:
        await callback.answer("❌ Задачу не знайдено.", show_alert=True)
        return
    await callback.answer("🗑 Видалено!")
    await cb_list_tasks(callback)


@router.callback_query(F.data == "add_task_start")
async def cb_add_task_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AddTaskFSM.waiting_title)
    await callback.message.edit_text("✏️ <b>Нова задача</b>\n\nВведи назву:", parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "export_csv")
async def cb_export_csv(callback: CallbackQuery) -> None:
    await callback.answer("⏳ Готую файл...")
    async with get_session() as session:
        user = await _get_user(session, callback)
        csv_data = await export_tasks_csv(session, user.id)

    if not csv_data.strip():
        await callback.message.answer("📭 Немає задач для експорту.")
        return

    from datetime import date
    from aiogram.types import BufferedInputFile
    filename = f"tasks_{date.today().isoformat()}.csv"
    file = BufferedInputFile(csv_data.encode("utf-8-sig"), filename=filename)
    await callback.message.answer_document(
        file, caption="📤 Твої задачі у CSV.\nВідкрий у Excel або Google Sheets."
    )


@router.callback_query(F.data == "stats")
async def cb_stats(callback: CallbackQuery) -> None:
    async with get_session() as session:
        user = await _get_user(session, callback)
        stats = await get_user_stats(session, user.id)

    from core.constants import CATEGORY_EMOJI, CATEGORY_LABEL
    filled = round(stats["productivity"] / 10)
    bar = "▓" * filled + "░" * (10 - filled)
    cat_lines = "".join(
        f"  {CATEGORY_EMOJI.get(cat,'📌')} {CATEGORY_LABEL.get(cat, cat)}: {count}\n"
        for cat, count in stats.get("by_category", {}).items()
    )
    await callback.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"📌 Всього: <b>{stats['total']}</b>\n"
        f"✅ Виконано: <b>{stats['done']}</b>\n"
        f"🔵 Активних: <b>{stats['active']}</b>\n"
        f"⚠️ Прострочених: <b>{stats['overdue']}</b>\n\n"
        f"🏆 Продуктивність: <b>{stats['productivity']}%</b>\n"
        f"{bar}\n\n"
        f"<b>По категоріях:</b>\n{cat_lines or '  —'}",
        parse_mode="HTML", reply_markup=main_menu_keyboard(),
    )
    await callback.answer()


# ─── AI subtasks from task detail ─────────────────────────────────────────────

@router.callback_query(F.data.startswith("ai_subtasks:"))
async def cb_ai_subtasks_from_detail(callback: CallbackQuery) -> None:
    from services import generate_subtasks, get_task
    from bot.keyboards import task_detail_keyboard

    task_id = int(callback.data.split(":")[1])
    async with get_session() as session:
        user = await _get_user(session, callback)
        task = await get_task(session, task_id, user.id)

    if task is None:
        await callback.answer("❌ Задачу не знайдено.", show_alert=True)
        return

    await callback.message.edit_text("🔀 Генерую підзадачі...")
    await callback.answer()

    result = await generate_subtasks(task.title, task.description)

    if result is None:
        await callback.message.edit_text(
            "😕 Не вдалося згенерувати підзадачі.",
            reply_markup=task_detail_keyboard(task),
        )
        return

    subtasks_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(result["subtasks"]))

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ До задачі", callback_data=f"task_detail:{task_id}")
    builder.adjust(1)

    await callback.message.edit_text(
        f"🔀 <b>Підзадачі для: {task.title}</b>\n\n"
        f"{subtasks_text}\n\n"
        f"<i>{result.get('explanation','')}</i>",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )
