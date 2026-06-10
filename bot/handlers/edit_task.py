"""
FSM handler for editing an existing task (all fields including repeat).
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import (
    edit_field_keyboard, priority_keyboard, category_keyboard,
    repeat_keyboard, skip_deadline_keyboard, task_detail_keyboard,
)
from bot.states import EditTaskFSM
from database.db import get_session
from services import get_or_create_user, update_task

logger = logging.getLogger(__name__)
router = Router(name="edit_task_fsm")

_LOCAL_TZ = ZoneInfo("Europe/Kyiv")
_DEADLINE_FORMATS = ["%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"]


@router.callback_query(F.data.startswith("edit_task:"))
async def cb_edit_task_start(callback: CallbackQuery, state: FSMContext) -> None:
    task_id = int(callback.data.split(":")[1])
    await state.set_state(EditTaskFSM.choose_field)
    await state.update_data(task_id=task_id)
    await callback.message.edit_text(
        "✏️ <b>Що хочеш змінити?</b>", parse_mode="HTML",
        reply_markup=edit_field_keyboard(task_id),
    )
    await callback.answer()


@router.callback_query(EditTaskFSM.choose_field, F.data.startswith("edit_field:"))
async def cb_choose_field(callback: CallbackQuery, state: FSMContext) -> None:
    _, task_id_str, field = callback.data.split(":")
    await state.update_data(task_id=int(task_id_str), field=field)

    prompts = {
        "title": (EditTaskFSM.waiting_new_title, "📝 Нова назва:"),
        "description": (EditTaskFSM.waiting_new_description, "📄 Новий опис або /skip:"),
    }
    if field in prompts:
        new_state, text = prompts[field]
        await state.set_state(new_state)
        await callback.message.edit_text(text)
    elif field == "priority":
        await state.set_state(EditTaskFSM.waiting_new_priority)
        await callback.message.edit_text("🎯 Новий пріоритет:", reply_markup=priority_keyboard("edit_priority"))
    elif field == "category":
        await state.set_state(EditTaskFSM.waiting_new_category)
        await callback.message.edit_text("🏷 Нова категорія:", reply_markup=category_keyboard("edit_category"))
    elif field == "repeat":
        await state.set_state(EditTaskFSM.waiting_new_repeat)
        await callback.message.edit_text("🔁 Повтор:", reply_markup=repeat_keyboard("edit_repeat"))
    elif field == "deadline":
        await state.set_state(EditTaskFSM.waiting_new_deadline)
        await callback.message.edit_text(
            "📅 Новий дедлайн <code>ДД.ММ.РРРР ГГ:ХХ</code>:", parse_mode="HTML",
            reply_markup=skip_deadline_keyboard("edit_skip_deadline"),
        )
    await callback.answer()


@router.message(EditTaskFSM.waiting_new_title)
async def edit_got_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title or len(title) > 256:
        await message.answer("❌ Від 1 до 256 символів:")
        return
    await _apply_edit(message, state, title=title)


@router.message(EditTaskFSM.waiting_new_description)
async def edit_got_description(message: Message, state: FSMContext) -> None:
    desc = None if message.text.strip() in ("/skip", "skip") else message.text.strip()
    await _apply_edit(message, state, description=desc)


@router.callback_query(EditTaskFSM.waiting_new_priority, F.data.startswith("edit_priority:"))
async def edit_got_priority(callback: CallbackQuery, state: FSMContext) -> None:
    await _apply_edit_cb(callback, state, priority=callback.data.split(":")[1])


@router.callback_query(EditTaskFSM.waiting_new_category, F.data.startswith("edit_category:"))
async def edit_got_category(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":")[1]
    await _apply_edit_cb(callback, state, category=None if value == "skip" else value)


@router.callback_query(EditTaskFSM.waiting_new_repeat, F.data.startswith("edit_repeat:"))
async def edit_got_repeat(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":")[1]
    await _apply_edit_cb(callback, state, repeat=None if value == "none" else value)


@router.callback_query(EditTaskFSM.waiting_new_deadline, F.data == "edit_skip_deadline")
async def edit_skip_deadline(callback: CallbackQuery, state: FSMContext) -> None:
    await _apply_edit_cb(callback, state, deadline=None)


@router.message(EditTaskFSM.waiting_new_deadline)
async def edit_got_deadline(message: Message, state: FSMContext) -> None:
    deadline = _parse_deadline(message.text.strip())
    if deadline is None:
        await message.answer(
            "❌ Формат: <code>ДД.ММ.РРРР ГГ:ХХ</code>", parse_mode="HTML",
            reply_markup=skip_deadline_keyboard("edit_skip_deadline"),
        )
        return
    await _apply_edit(message, state, deadline=deadline)


async def _apply_edit(message: Message, state: FSMContext, **fields) -> None:
    data = await state.get_data()
    await state.clear()
    async with get_session() as session:
        user = await get_or_create_user(
            session, telegram_id=message.from_user.id, first_name=message.from_user.first_name
        )
        task = await update_task(session, data["task_id"], user.id, **fields)
    if task is None:
        await message.answer("❌ Задачу не знайдено.")
        return
    await message.answer(
        f"✅ <b>{task.title}</b> оновлено!", parse_mode="HTML",
        reply_markup=task_detail_keyboard(task),
    )


async def _apply_edit_cb(callback: CallbackQuery, state: FSMContext, **fields) -> None:
    data = await state.get_data()
    await state.clear()
    async with get_session() as session:
        user = await get_or_create_user(
            session, telegram_id=callback.from_user.id, first_name=callback.from_user.first_name
        )
        task = await update_task(session, data["task_id"], user.id, **fields)
    if task is None:
        await callback.answer("❌ Задачу не знайдено.", show_alert=True)
        return
    await callback.answer("✅ Оновлено!")
    await callback.message.edit_text(
        f"✅ <b>{task.title}</b> оновлено!", parse_mode="HTML",
        reply_markup=task_detail_keyboard(task),
    )


def _parse_deadline(raw: str) -> datetime | None:
    for fmt in _DEADLINE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=_LOCAL_TZ)
        except ValueError:
            continue
    return None
