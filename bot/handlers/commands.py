"""
Command handlers: /start /help /add_task /list_tasks /today /search /done_task /delete_task /stats /export
"""
import logging
import io

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, BufferedInputFile

from bot.keyboards import main_menu_keyboard, task_list_keyboard
from bot.states import AddTaskFSM
from database.db import get_session
from services import (
    get_or_create_user, list_tasks, list_tasks_today,
    mark_done, delete_task, get_user_stats, export_tasks_csv,
)
from core.constants import CATEGORY_EMOJI, CATEGORY_LABEL

logger = logging.getLogger(__name__)
router = Router(name="commands")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    async with get_session() as session:
        await get_or_create_user(
            session, telegram_id=message.from_user.id,
            first_name=message.from_user.first_name,
            username=message.from_user.username,
        )
    await message.answer(
        f"👋 Привіт, <b>{message.from_user.first_name}</b>!\n\n"
        "Я <b>Smart Planner</b> — твій менеджер задач. 🗂\n\n"
        "• Задачі з дедлайнами, пріоритетами та категоріями\n"
        "• 🔁 Повторювані задачі\n"
        "• 🔍 Пошук по задачах\n"
        "• 📤 Експорт у CSV\n"
        "• 🔔 Автоматичні нагадування\n\n"
        "Обери дію:",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "📖 <b>Команди:</b>\n\n"
        "/start — Головне меню\n"
        "/add_task — Додати задачу\n"
        "/list_tasks — Всі задачі\n"
        "/today — Задачі на сьогодні\n"
        "/search — Пошук задач\n"
        "/done_task <code>&lt;id&gt;</code> — Виконати\n"
        "/delete_task <code>&lt;id&gt;</code> — Видалити\n"
        "/ai — Додати задачу через AI\n"
        "/profile — Мій профіль та XP\n"
        "/stats — Статистика\n"
        "/export — Експорт у CSV\n\n"
        "<i>💡 Більшість дій доступні через кнопки.</i>",
        parse_mode="HTML",
    )


@router.message(Command("add_task"))
async def cmd_add_task(message: Message, state: FSMContext) -> None:
    await state.set_state(AddTaskFSM.waiting_title)
    await message.answer("✏️ <b>Нова задача</b>\n\nВведи назву:", parse_mode="HTML")


@router.message(Command("list_tasks"))
async def cmd_list_tasks(message: Message) -> None:
    async with get_session() as session:
        user = await get_or_create_user(
            session, telegram_id=message.from_user.id, first_name=message.from_user.first_name
        )
        tasks = await list_tasks(session, user.id)
    if not tasks:
        await message.answer("📭 Задач немає. Додай першу: /add_task")
        return
    await message.answer(
        f"📋 <b>Твої задачі</b> ({len(tasks)} шт.):",
        parse_mode="HTML", reply_markup=task_list_keyboard(tasks),
    )


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    async with get_session() as session:
        user = await get_or_create_user(
            session, telegram_id=message.from_user.id, first_name=message.from_user.first_name
        )
        tasks = await list_tasks_today(session, user.id)
    if not tasks:
        await message.answer("🎉 На сьогодні задач немає!\n\nДодай нову: /add_task")
        return
    await message.answer(
        f"📅 <b>Сьогодні</b> ({len(tasks)} шт.):",
        parse_mode="HTML", reply_markup=task_list_keyboard(tasks),
    )


@router.message(Command("done_task"))
async def cmd_done_task(message: Message, command: CommandObject) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("❓ Вкажи ID: /done_task <code>5</code>", parse_mode="HTML")
        return
    async with get_session() as session:
        user = await get_or_create_user(
            session, telegram_id=message.from_user.id, first_name=message.from_user.first_name
        )
        task = await mark_done(session, int(command.args.strip()), user.id)
    if task is None:
        await message.answer("❌ Задачу не знайдено.")
        return
    repeat_note = ""
    if task.repeat:
        from core.constants import REPEAT_LABEL, REPEAT_EMOJI
        repeat_note = f"\n🔁 Наступна задача створена автоматично ({REPEAT_EMOJI.get(task.repeat,'')} {REPEAT_LABEL.get(task.repeat,'')})"
    await message.answer(
        f"✅ <b>{task.title}</b> — виконано!{repeat_note}", parse_mode="HTML"
    )


@router.message(Command("delete_task"))
async def cmd_delete_task(message: Message, command: CommandObject) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer("❓ Вкажи ID: /delete_task <code>5</code>", parse_mode="HTML")
        return
    async with get_session() as session:
        user = await get_or_create_user(
            session, telegram_id=message.from_user.id, first_name=message.from_user.first_name
        )
        deleted = await delete_task(session, int(command.args.strip()), user.id)
    if not deleted:
        await message.answer("❌ Задачу не знайдено.")
        return
    await message.answer("🗑 Видалено.")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    async with get_session() as session:
        user = await get_or_create_user(
            session, telegram_id=message.from_user.id, first_name=message.from_user.first_name
        )
        stats = await get_user_stats(session, user.id)
    await message.answer(
        _stats_text(stats), parse_mode="HTML", reply_markup=main_menu_keyboard()
    )


@router.message(Command("export"))
async def cmd_export(message: Message) -> None:
    await _send_export(message, message.from_user.id, message.from_user.first_name)


async def _send_export(message: Message, tg_id: int, first_name: str) -> None:
    async with get_session() as session:
        user = await get_or_create_user(session, telegram_id=tg_id, first_name=first_name)
        csv_data = await export_tasks_csv(session, user.id)

    if not csv_data.strip():
        await message.answer("📭 Немає задач для експорту.")
        return

    from datetime import date
    filename = f"tasks_{date.today().isoformat()}.csv"
    file = BufferedInputFile(csv_data.encode("utf-8-sig"), filename=filename)
    await message.answer_document(file, caption="📤 Твої задачі у форматі CSV.\nВідкрий у Excel або Google Sheets.")


def _stats_text(stats: dict) -> str:
    filled = round(stats["productivity"] / 10)
    bar = "▓" * filled + "░" * (10 - filled)
    cat_lines = ""
    for cat, count in stats.get("by_category", {}).items():
        icon = CATEGORY_EMOJI.get(cat, "📌")
        label = CATEGORY_LABEL.get(cat, cat)
        cat_lines += f"  {icon} {label}: {count}\n"
    return (
        f"📊 <b>Статистика</b>\n\n"
        f"📌 Всього: <b>{stats['total']}</b>\n"
        f"✅ Виконано: <b>{stats['done']}</b>\n"
        f"🔵 Активних: <b>{stats['active']}</b>\n"
        f"⚠️ Прострочених: <b>{stats['overdue']}</b>\n\n"
        f"🏆 Продуктивність: <b>{stats['productivity']}%</b>\n"
        f"{bar}\n\n"
        f"<b>По категоріях:</b>\n{cat_lines or '  —'}"
    )
