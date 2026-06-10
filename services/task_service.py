"""
Task service — single source of truth for all task business logic.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import Priority, TaskStatus, PRIORITY_WEIGHT
from core.utils import utc_now, next_deadline
from database.models import Task, User


async def get_or_create_user(
    session: AsyncSession, telegram_id: int, first_name: str, username: str | None = None
) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(telegram_id=telegram_id, first_name=first_name, username=username)
        session.add(user)
        await session.flush()
    else:
        user.first_name = first_name
        user.username = username
    return user


async def create_task(
    session: AsyncSession,
    user_id: int,
    title: str,
    description: str | None = None,
    priority: str = Priority.MEDIUM,
    category: str | None = None,
    deadline: datetime | None = None,
    repeat: str | None = None,
) -> Task:
    task = Task(
        user_id=user_id, title=title, description=description,
        priority=priority, category=category,
        status=TaskStatus.ACTIVE, deadline=deadline, repeat=repeat,
    )
    session.add(task)
    await session.flush()
    return task


async def get_task(session: AsyncSession, task_id: int, user_id: int) -> Task | None:
    result = await session.execute(
        select(Task).where(Task.id == task_id, Task.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def list_tasks(
    session: AsyncSession,
    user_id: int,
    status_filter: str | None = None,
    category_filter: str | None = None,
) -> list[Task]:
    stmt = select(Task).where(Task.user_id == user_id)
    if status_filter:
        stmt = stmt.where(Task.status == status_filter)
    if category_filter:
        stmt = stmt.where(Task.category == category_filter)
    tasks = (await session.execute(stmt)).scalars().all()

    def sort_key(t: Task):
        w = PRIORITY_WEIGHT.get(t.priority, 99)
        dl = t.deadline or datetime.max.replace(tzinfo=timezone.utc)
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)
        return (w, dl)

    return sorted(tasks, key=sort_key)


async def list_tasks_today(session: AsyncSession, user_id: int) -> list[Task]:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Kyiv")
    now_local = datetime.now(tz)
    today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = now_local.replace(hour=23, minute=59, second=59, microsecond=999999)
    result = await session.execute(
        select(Task).where(
            Task.user_id == user_id,
            Task.status == TaskStatus.ACTIVE,
            Task.deadline.isnot(None),
            Task.deadline >= today_start,
            Task.deadline <= today_end,
        )
    )
    tasks = result.scalars().all()
    return sorted(tasks, key=lambda t: PRIORITY_WEIGHT.get(t.priority, 99))


async def search_tasks(session: AsyncSession, user_id: int, query: str) -> list[Task]:
    """Full-text search in title and description (case-insensitive)."""
    q = f"%{query.lower()}%"
    result = await session.execute(
        select(Task).where(
            Task.user_id == user_id,
            or_(
                func.lower(Task.title).like(q),
                func.lower(Task.description).like(q),
            ),
        )
    )
    tasks = result.scalars().all()
    return sorted(tasks, key=lambda t: PRIORITY_WEIGHT.get(t.priority, 99))


async def update_task(session: AsyncSession, task_id: int, user_id: int, **fields) -> Task | None:
    task = await get_task(session, task_id, user_id)
    if task is None:
        return None
    for key, value in fields.items():
        setattr(task, key, value)
    return task


async def mark_done(session: AsyncSession, task_id: int, user_id: int) -> Task | None:
    """
    Mark task as done. If it has a repeat interval, automatically
    create the next occurrence with an updated deadline.
    """
    task = await get_task(session, task_id, user_id)
    if task is None:
        return None
    task.status = TaskStatus.DONE

    # Auto-spawn next occurrence for repeating tasks
    if task.repeat and task.deadline:
        new_deadline = next_deadline(task.deadline, task.repeat)
        new_task = Task(
            user_id=task.user_id,
            title=task.title,
            description=task.description,
            priority=task.priority,
            category=task.category,
            status=TaskStatus.ACTIVE,
            deadline=new_deadline,
            repeat=task.repeat,
        )
        session.add(new_task)

    return task


async def delete_task(session: AsyncSession, task_id: int, user_id: int) -> bool:
    result = await session.execute(
        delete(Task).where(Task.id == task_id, Task.user_id == user_id)
    )
    return result.rowcount > 0


async def refresh_overdue_statuses(session: AsyncSession) -> list[Task]:
    now = utc_now()
    result = await session.execute(
        select(Task).where(
            Task.status == TaskStatus.ACTIVE,
            Task.deadline.isnot(None),
            Task.deadline < now,
        )
    )
    tasks = result.scalars().all()
    for task in tasks:
        task.status = TaskStatus.OVERDUE
    return list(tasks)


async def get_tasks_due_soon(session: AsyncSession, minutes_before: int) -> list[Task]:
    now = utc_now()
    cutoff = now + timedelta(minutes=minutes_before)
    result = await session.execute(
        select(Task).where(
            Task.status == TaskStatus.ACTIVE,
            Task.deadline.isnot(None),
            Task.deadline >= now,
            Task.deadline <= cutoff,
            Task.reminder_sent.is_(False),
        )
    )
    return result.scalars().all()


async def mark_reminder_sent(session: AsyncSession, task_id: int) -> None:
    await session.execute(update(Task).where(Task.id == task_id).values(reminder_sent=True))


async def get_user_stats(session: AsyncSession, user_id: int) -> dict:
    rows = await session.execute(
        select(Task.status, func.count(Task.id))
        .where(Task.user_id == user_id)
        .group_by(Task.status)
    )
    counts = {row[0]: row[1] for row in rows}
    total = sum(counts.values())
    done = counts.get(TaskStatus.DONE, 0)
    active = counts.get(TaskStatus.ACTIVE, 0)
    overdue = counts.get(TaskStatus.OVERDUE, 0)
    productivity = round(done / total * 100) if total else 0

    cat_rows = await session.execute(
        select(Task.category, func.count(Task.id))
        .where(Task.user_id == user_id)
        .group_by(Task.category)
    )
    by_category = {row[0] or "other": row[1] for row in cat_rows}

    return {
        "total": total, "done": done, "active": active,
        "overdue": overdue, "productivity": productivity,
        "by_category": by_category,
    }


async def export_tasks_csv(session: AsyncSession, user_id: int) -> str:
    """Return all tasks as a CSV string."""
    import csv, io
    from core.utils import format_deadline
    from core.constants import PRIORITY_LABEL, STATUS_LABEL, CATEGORY_LABEL, REPEAT_LABEL

    tasks = await list_tasks(session, user_id)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Назва", "Опис", "Пріоритет", "Статус", "Категорія", "Дедлайн", "Повтор", "Створено"])
    for t in tasks:
        writer.writerow([
            t.id,
            t.title,
            t.description or "",
            PRIORITY_LABEL.get(t.priority, t.priority),
            STATUS_LABEL.get(t.status, t.status),
            CATEGORY_LABEL.get(t.category or "", t.category or ""),
            format_deadline(t.deadline),
            REPEAT_LABEL.get(t.repeat or "", ""),
            format_deadline(t.created_at),
        ])
    return output.getvalue()
