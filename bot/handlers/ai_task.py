"""
AI Task handler — create tasks from free-form text using OpenAI.

Flow:
  /ai  →  user types anything  →  AI parses it  →  confirm screen
       →  [Зберегти] saves the task
       →  [✏️ Змінити] falls back into regular AddTaskFSM
       →  [🔀 Підзадачі] generates subtasks list
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards import main_menu_keyboard
from bot.states import AITaskFSM, AddTaskFSM
from core.config import settings
from core.constants import (
    PRIORITY_EMOJI, PRIORITY_LABEL,
    CATEGORY_EMOJI, CATEGORY_LABEL,
)
from core.utils import format_deadline
from database.db import get_session
from services import create_task, get_or_create_user, parse_task_from_text, generate_subtasks

logger = logging.getLogger(__name__)
router = Router(name="ai_task_fsm")


# ─── Entry points ─────────────────────────────────────────────────────────────

@router.message(Command("ai"))
async def cmd_ai(message: Message, state: FSMContext) -> None:
    if not settings.ai.enabled:
        await message.answer(
            "🤖 AI-функції вимкнені.\n\n"
            "Щоб увімкнути — додай <code>OPENAI_API_KEY=sk-...</code> у файл <code>.env</code>\n"
            "Отримати ключ: https://platform.openai.com/api-keys",
            parse_mode="HTML",
        )
        return

    await state.set_state(AITaskFSM.waiting_text)
    await message.answer(
        "🤖 <b>Розумне додавання задачі</b>\n\n"
        "Напиши задачу своїми словами — будь-якою мовою.\n\n"
        "<b>Приклади:</b>\n"
        "• <i>Терміново здати звіт по Q2 до п'ятниці 18:00</i>\n"
        "• <i>Купити продукти на вихідні, молоко та хліб</i>\n"
        "• <i>Підготуватись до іспиту з математики наступного тижня</i>\n\n"
        "AI сам визначить пріоритет, категорію та дедлайн 🧠",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "ai_task_start")
async def cb_ai_task_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not settings.ai.enabled:
        await callback.answer("AI вимкнений — потрібен OPENAI_API_KEY", show_alert=True)
        return
    await state.set_state(AITaskFSM.waiting_text)
    await callback.message.edit_text(
        "🤖 <b>Розумне додавання</b>\n\nНапиши задачу своїми словами:",
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Step 1: receive free-form text ───────────────────────────────────────────

@router.message(AITaskFSM.waiting_text)
async def fsm_ai_got_text(message: Message, state: FSMContext) -> None:
    user_text = message.text.strip()
    if len(user_text) < 3:
        await message.answer("❌ Занадто коротко. Опиши задачу детальніше:")
        return

    thinking = await message.answer("🧠 Аналізую задачу...")

    parsed = await parse_task_from_text(user_text)

    await thinking.delete()

    if parsed is None:
        await message.answer(
            "😕 Не вдалося розпарсити задачу. Спробуй ще раз або скористайся /add_task",
            reply_markup=main_menu_keyboard(),
        )
        await state.clear()
        return

    await state.update_data(parsed=parsed, original_text=user_text)
    await state.set_state(AITaskFSM.confirm_parsed)
    await _show_confirm(message, parsed)


# ─── Step 2: confirmation screen ──────────────────────────────────────────────

async def _show_confirm(message: Message, parsed: dict) -> None:
    priority = parsed.get("priority", "medium")
    category = parsed.get("category")
    deadline = parsed.get("deadline")
    confidence = parsed.get("confidence", 0.8)

    confidence_bar = "🟢" if confidence >= 0.8 else "🟡" if confidence >= 0.5 else "🔴"

    lines = [
        f"🤖 <b>AI розпізнав задачу</b> {confidence_bar} {round(confidence * 100)}%\n",
        f"📌 <b>{parsed.get('title', '—')}</b>",
        f"📝 {parsed.get('description') or '—'}",
        f"🎯 {PRIORITY_EMOJI.get(priority,'')}{PRIORITY_LABEL.get(priority,'')}",
    ]
    if category:
        lines.append(f"🏷 {CATEGORY_EMOJI.get(category,'')} {CATEGORY_LABEL.get(category,'')}")
    lines.append(f"📅 {format_deadline(deadline)}")
    lines.append("\nВсе вірно?")

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_confirm_keyboard(),
    )


def _confirm_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Зберегти", callback_data="ai_confirm_save")
    builder.button(text="✏️ Змінити вручну", callback_data="ai_confirm_edit")
    builder.button(text="🔀 Розбити на підзадачі", callback_data="ai_confirm_subtasks")
    builder.button(text="❌ Скасувати", callback_data="main_menu")
    builder.adjust(2, 1, 1)
    return builder.as_markup()


# ─── Save confirmed task ──────────────────────────────────────────────────────

@router.callback_query(AITaskFSM.confirm_parsed, F.data == "ai_confirm_save")
async def cb_ai_save(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    parsed = data["parsed"]
    await state.clear()

    async with get_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name,
        )
        task = await create_task(
            session,
            user_id=user.id,
            title=parsed.get("title", "Нова задача"),
            description=parsed.get("description"),
            priority=parsed.get("priority", "medium"),
            category=parsed.get("category"),
            deadline=parsed.get("deadline"),
        )

    await callback.answer("✅ Збережено!")
    await callback.message.edit_text(
        f"🎉 <b>Задачу створено!</b>\n\n"
        f"📌 <b>{task.title}</b>\n"
        f"🆔 ID: <code>{task.id}</code>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


# ─── Edit manually — fall into regular AddTaskFSM ────────────────────────────

@router.callback_query(AITaskFSM.confirm_parsed, F.data == "ai_confirm_edit")
async def cb_ai_edit(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    parsed = data["parsed"]

    # Pre-fill FSM data with AI results so user can adjust
    await state.set_state(AddTaskFSM.waiting_description)
    await state.update_data(
        title=parsed.get("title", ""),
        description=parsed.get("description"),
        priority=parsed.get("priority", "medium"),
        category=parsed.get("category"),
        deadline=parsed.get("deadline"),
    )

    await callback.message.edit_text(
        f"✏️ Назва: <b>{parsed.get('title','')}</b>\n\n"
        "Введи новий опис або /skip:",
        parse_mode="HTML",
    )
    await callback.answer()


# ─── Generate subtasks ────────────────────────────────────────────────────────

@router.callback_query(AITaskFSM.confirm_parsed, F.data == "ai_confirm_subtasks")
async def cb_ai_subtasks(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    parsed = data["parsed"]

    await callback.message.edit_text("🔀 Генерую підзадачі...")
    await callback.answer()

    result = await generate_subtasks(
        title=parsed.get("title", ""),
        description=parsed.get("description"),
    )

    if result is None:
        await callback.message.edit_text(
            "😕 Не вдалося згенерувати підзадачі. Спробуй пізніше.",
            reply_markup=_confirm_keyboard(),
        )
        return

    subtasks_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(result["subtasks"]))
    explanation = result.get("explanation", "")

    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Зберегти основну задачу", callback_data="ai_confirm_save")
    builder.button(text="⬅️ Назад", callback_data="ai_back_to_confirm")
    builder.adjust(1)

    await callback.message.edit_text(
        f"🔀 <b>Підзадачі для: {parsed.get('title','')}</b>\n\n"
        f"{subtasks_text}\n\n"
        f"<i>{explanation}</i>\n\n"
        "Збережи основну задачу і додай підзадачі вручну через /add_task:",
        parse_mode="HTML",
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "ai_back_to_confirm")
async def cb_ai_back(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    parsed = data.get("parsed", {})
    await state.set_state(AITaskFSM.confirm_parsed)
    await _show_confirm(callback.message, parsed)
    await callback.answer()
