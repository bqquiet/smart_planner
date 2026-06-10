"""
FSM: title → description → priority → category → repeat → deadline → save
"""
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import (
    priority_keyboard, category_keyboard, repeat_keyboard,
    skip_deadline_keyboard, main_menu_keyboard,
)
from bot.states import AddTaskFSM
from database.db import get_session
from services import create_task, get_or_create_user
from core.constants import PRIORITY_LABEL, PRIORITY_EMOJI, CATEGORY_LABEL, CATEGORY_EMOJI, REPEAT_LABEL, REPEAT_EMOJI

logger = logging.getLogger(__name__)
router = Router(name="add_task_fsm")

_LOCAL_TZ = ZoneInfo("Europe/Kyiv")
_DEADLINE_FORMATS = ["%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"]


@router.message(AddTaskFSM.waiting_title)
async def fsm_got_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip()
    if not title or len(title) > 256:
        await message.answer("❌ Назва має бути від 1 до 256 символів:")
        return
    await state.update_data(title=title)
    await state.set_state(AddTaskFSM.waiting_description)
    await message.answer(f"✏️ <b>{title}</b>\n\nВведи опис або /skip:", parse_mode="HTML")


@router.message(AddTaskFSM.waiting_description, F.text.in_({"/skip", "skip"}))
async def fsm_skip_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=None)
    await _ask_priority(message, state)


@router.message(AddTaskFSM.waiting_description)
async def fsm_got_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=message.text.strip())
    await _ask_priority(message, state)


async def _ask_priority(message: Message, state: FSMContext) -> None:
    await state.set_state(AddTaskFSM.waiting_priority)
    await message.answer("🎯 Пріоритет:", reply_markup=priority_keyboard())


@router.callback_query(AddTaskFSM.waiting_priority, F.data.startswith("set_priority:"))
async def fsm_got_priority(callback: CallbackQuery, state: FSMContext) -> None:
    priority = callback.data.split(":")[1]
    await state.update_data(priority=priority)
    await state.set_state(AddTaskFSM.waiting_category)
    await callback.message.edit_text(
        f"🎯 {PRIORITY_EMOJI.get(priority,'')}{PRIORITY_LABEL.get(priority,'')}\n\n🏷 Категорія:",
        parse_mode="HTML", reply_markup=category_keyboard(),
    )
    await callback.answer()


@router.callback_query(AddTaskFSM.waiting_category, F.data.startswith("set_category:"))
async def fsm_got_category(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":")[1]
    category = None if value == "skip" else value
    await state.update_data(category=category)
    await state.set_state(AddTaskFSM.waiting_repeat)
    await callback.message.edit_text("🔁 Повторювати задачу?", reply_markup=repeat_keyboard())
    await callback.answer()


@router.callback_query(AddTaskFSM.waiting_repeat, F.data.startswith("set_repeat:"))
async def fsm_got_repeat(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.split(":")[1]
    repeat = None if value == "none" else value
    await state.update_data(repeat=repeat)
    await state.set_state(AddTaskFSM.waiting_deadline)

    repeat_line = ""
    if repeat:
        repeat_line = f"🔁 {REPEAT_EMOJI.get(repeat,'')} {REPEAT_LABEL.get(repeat,'')}\n\n"

    await callback.message.edit_text(
        f"{repeat_line}⏰ Дедлайн: <code>ДД.ММ.РРРР ГГ:ХХ</code>\nНаприклад: <code>25.12.2025 18:00</code>",
        parse_mode="HTML", reply_markup=skip_deadline_keyboard(),
    )
    await callback.answer()


@router.callback_query(AddTaskFSM.waiting_deadline, F.data == "skip_deadline")
async def fsm_skip_deadline(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(deadline=None)
    await _save_task(callback.message, state, callback.from_user.id, callback.from_user.first_name)
    await callback.answer()


@router.message(AddTaskFSM.waiting_deadline)
async def fsm_got_deadline(message: Message, state: FSMContext) -> None:
    deadline = _parse_deadline(message.text.strip())
    if deadline is None:
        await message.answer(
            "❌ Формат: <code>ДД.ММ.РРРР ГГ:ХХ</code>", parse_mode="HTML",
            reply_markup=skip_deadline_keyboard(),
        )
        return
    await state.update_data(deadline=deadline)
    await _save_task(message, state, message.from_user.id, message.from_user.first_name)


async def _save_task(message: Message, state: FSMContext, tg_id: int, first_name: str) -> None:
    data = await state.get_data()
    await state.clear()

    async with get_session() as session:
        user = await get_or_create_user(session, telegram_id=tg_id, first_name=first_name)
        task = await create_task(
            session, user_id=user.id,
            title=data["title"], description=data.get("description"),
            priority=data.get("priority", "medium"),
            category=data.get("category"),
            deadline=data.get("deadline"),
            repeat=data.get("repeat"),
        )

    from core.utils import format_deadline
    priority = data.get("priority", "medium")
    category = data.get("category")
    repeat = data.get("repeat")

    lines = [
        f"🎉 <b>Задача створена!</b>\n",
        f"📌 <b>{task.title}</b>",
        f"📝 {data.get('description') or '—'}",
        f"🎯 {PRIORITY_EMOJI.get(priority,'')}{PRIORITY_LABEL.get(priority,'')}",
    ]
    if category:
        lines.append(f"🏷 {CATEGORY_EMOJI.get(category,'')} {CATEGORY_LABEL.get(category,'')}")
    if repeat:
        lines.append(f"🔁 {REPEAT_EMOJI.get(repeat,'')} {REPEAT_LABEL.get(repeat,'')}")
    lines.append(f"📅 {format_deadline(task.deadline)}")
    lines.append(f"🆔 ID: <code>{task.id}</code>")

    await message.answer("\n".join(lines), parse_mode="HTML", reply_markup=main_menu_keyboard())


def _parse_deadline(raw: str) -> datetime | None:
    for fmt in _DEADLINE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=_LOCAL_TZ)
        except ValueError:
            continue
    return None
