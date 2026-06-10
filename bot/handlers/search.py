"""
FSM handler for /search and search callback.
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.keyboards import task_list_keyboard, main_menu_keyboard
from bot.states import SearchFSM
from database.db import get_session
from services import get_or_create_user, search_tasks

logger = logging.getLogger(__name__)
router = Router(name="search_fsm")


@router.message(Command("search"))
async def cmd_search(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchFSM.waiting_query)
    await message.answer("🔍 Введи текст для пошуку по назві та опису задач:")


@router.callback_query(F.data == "search_start")
async def cb_search_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchFSM.waiting_query)
    await callback.message.edit_text("🔍 Введи текст для пошуку:")
    await callback.answer()


@router.message(SearchFSM.waiting_query)
async def fsm_got_query(message: Message, state: FSMContext) -> None:
    query = message.text.strip()
    await state.clear()

    if len(query) < 2:
        await message.answer("❌ Запит надто короткий. Мінімум 2 символи.")
        return

    async with get_session() as session:
        user = await get_or_create_user(
            session, telegram_id=message.from_user.id, first_name=message.from_user.first_name
        )
        tasks = await search_tasks(session, user.id, query)

    if not tasks:
        await message.answer(
            f"🔍 За запитом «<b>{query}</b>» нічого не знайдено.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    await message.answer(
        f"🔍 Результати для «<b>{query}</b>» — {len(tasks)} шт.:",
        parse_mode="HTML",
        reply_markup=task_list_keyboard(tasks),
    )
