"""
Reminder service — APScheduler jobs that run in the background.

Two periodic jobs:
  1. check_reminders  — fires reminders for tasks due soon
  2. check_overdue    — marks overdue tasks and notifies users
"""
import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from core.config import settings
from database.db import get_session
from database.models import Task, User
from services.task_service import (
    get_tasks_due_soon,
    mark_reminder_sent,
    refresh_overdue_statuses,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ─── Message builders ─────────────────────────────────────────────────────────

def _reminder_text(task: Task) -> str:
    from core.utils import format_deadline, deadline_delta_label
    return (
        f"⏰ <b>Нагадування!</b>\n\n"
        f"Задача <b>{task.title}</b> наближається до дедлайну.\n"
        f"📅 Дедлайн: {format_deadline(task.deadline)} "
        f"({deadline_delta_label(task.deadline)})"
    )


def _overdue_text(task: Task) -> str:
    from core.utils import format_deadline
    return (
        f"🚨 <b>Прострочена задача!</b>\n\n"
        f"Задача <b>{task.title}</b> не виконана вчасно.\n"
        f"📅 Дедлайн був: {format_deadline(task.deadline)}"
    )


# ─── Job functions ────────────────────────────────────────────────────────────

async def _get_user_telegram_id(session: AsyncSession, user_id: int) -> int | None:
    result = await session.execute(
        select(User.telegram_id).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def job_check_reminders(bot: Bot) -> None:
    """Send reminders for tasks approaching their deadline."""
    minutes = settings.scheduler.reminder_minutes_before
    async with get_session() as session:
        tasks = await get_tasks_due_soon(session, minutes)
        for task in tasks:
            tg_id = await _get_user_telegram_id(session, task.user_id)
            if tg_id:
                try:
                    await bot.send_message(
                        tg_id, _reminder_text(task), parse_mode="HTML"
                    )
                    await mark_reminder_sent(session, task.id)
                except Exception as exc:
                    logger.warning("Could not send reminder to %s: %s", tg_id, exc)


async def job_check_overdue(bot: Bot) -> None:
    """Mark overdue tasks and notify their owners."""
    async with get_session() as session:
        tasks = await refresh_overdue_statuses(session)
        for task in tasks:
            tg_id = await _get_user_telegram_id(session, task.user_id)
            if tg_id:
                try:
                    await bot.send_message(
                        tg_id, _overdue_text(task), parse_mode="HTML"
                    )
                except Exception as exc:
                    logger.warning("Could not send overdue notice to %s: %s", tg_id, exc)


# ─── Scheduler factory ────────────────────────────────────────────────────────

def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    # Reminder job: every minute (fine-grained; actual filter is in get_tasks_due_soon)
    scheduler.add_job(
        job_check_reminders,
        trigger="interval",
        minutes=1,
        kwargs={"bot": bot},
        id="check_reminders",
        replace_existing=True,
    )

    # Overdue job: configurable interval (default 5 min)
    scheduler.add_job(
        job_check_overdue,
        trigger="interval",
        seconds=settings.scheduler.overdue_check_interval,
        kwargs={"bot": bot},
        id="check_overdue",
        replace_existing=True,
    )

    return scheduler
