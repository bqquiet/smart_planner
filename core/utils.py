from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .constants import PRIORITY_EMOJI, STATUS_EMOJI


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def format_deadline(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo("Europe/Kyiv")).strftime("%d.%m.%Y %H:%M")


def deadline_delta_label(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    total_seconds = int((dt - utc_now()).total_seconds())
    if total_seconds > 0:
        return f"через {_humanize_seconds(total_seconds)}"
    return f"прострочено {_humanize_seconds(-total_seconds)} тому"


def _humanize_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds} сек"
    if seconds < 3600:
        return f"{seconds // 60} хв"
    if seconds < 86400:
        h, m = seconds // 3600, (seconds % 3600) // 60
        return f"{h} год {m} хв" if m else f"{h} год"
    return f"{seconds // 86400} дн"


def task_summary_line(task) -> str:
    priority_icon = PRIORITY_EMOJI.get(task.priority, "")
    status_icon = STATUS_EMOJI.get(task.status, "")
    deadline_str = format_deadline(task.deadline)
    return (
        f"{priority_icon}{status_icon} <b>{task.title}</b>\n"
        f"   📅 {deadline_str}  |  {deadline_delta_label(task.deadline)}"
    )


def next_deadline(current: datetime, repeat: str) -> datetime:
    """Calculate next deadline based on repeat interval."""
    from datetime import timedelta
    from dateutil.relativedelta import relativedelta
    if repeat == "daily":
        return current + timedelta(days=1)
    if repeat == "weekly":
        return current + timedelta(weeks=1)
    if repeat == "monthly":
        return current + relativedelta(months=1)
    return current
