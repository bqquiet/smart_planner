"""
Gamification service — XP, levels, streaks, achievements.

XP rewards:
  +10  — task created
  +25  — task completed on time
  +15  — task completed (overdue)
  +50  — streak bonus (every 7 days)
  +100 — level up bonus

Level thresholds: 1→2: 100xp, 2→3: 250xp, 3→4: 500xp, 4→5: 1000xp, etc.
Formula: level N requires N*(N-1)*50 XP total
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.utils import utc_now
from database.models import UserStats

logger = logging.getLogger(__name__)

# ─── XP constants ─────────────────────────────────────────────────────────────
XP_TASK_CREATED = 10
XP_TASK_DONE_ON_TIME = 25
XP_TASK_DONE_LATE = 15
XP_STREAK_WEEKLY_BONUS = 50
XP_LEVEL_UP_BONUS = 100

LEVEL_NAMES = {
    1: "🌱 Beginner",
    2: "⚡ Starter",
    3: "🔥 Doer",
    4: "💎 Achiever",
    5: "🚀 Pro",
    6: "🏆 Master",
    7: "👑 Legend",
    8: "🌟 Grandmaster",
}


def xp_for_level(level: int) -> int:
    """Total XP needed to reach this level."""
    return level * (level - 1) * 50


def level_from_xp(xp: int) -> int:
    """Calculate level from total XP."""
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
        if level >= 8:
            break
    return level


def xp_to_next_level(current_xp: int, current_level: int) -> tuple[int, int]:
    """Returns (xp_needed, xp_in_current_level)."""
    next_level_xp = xp_for_level(current_level + 1)
    current_level_xp = xp_for_level(current_level)
    return next_level_xp - current_xp, current_xp - current_level_xp


def level_progress_bar(current_xp: int, level: int, width: int = 10) -> str:
    next_xp = xp_for_level(level + 1)
    current_xp_in_level = current_xp - xp_for_level(level)
    needed = next_xp - xp_for_level(level)
    if needed <= 0:
        return "▓" * width
    filled = min(width, round(current_xp_in_level / needed * width))
    return "▓" * filled + "░" * (width - filled)


def get_level_name(level: int) -> str:
    return LEVEL_NAMES.get(level, f"⭐ Level {level}")


# ─── DB helpers ───────────────────────────────────────────────────────────────

async def get_or_create_stats(session: AsyncSession, user_id: int) -> UserStats:
    result = await session.execute(
        select(UserStats).where(UserStats.user_id == user_id)
    )
    stats = result.scalar_one_or_none()
    if stats is None:
        stats = UserStats(user_id=user_id)
        session.add(stats)
        await session.flush()
    return stats


async def award_xp(
    session: AsyncSession,
    user_id: int,
    xp_amount: int,
    reason: str = "",
) -> dict:
    """
    Award XP and update level/streak.
    Returns a dict with level_up info so the caller can notify the user.
    """
    stats = await get_or_create_stats(session, user_id)
    old_level = stats.level

    stats.xp += xp_amount
    stats.level = level_from_xp(stats.xp)

    level_up = stats.level > old_level
    if level_up:
        stats.xp += XP_LEVEL_UP_BONUS  # bonus on level up
        logger.info("User %s leveled up to %d!", user_id, stats.level)

    return {
        "xp_gained": xp_amount,
        "total_xp": stats.xp,
        "level": stats.level,
        "level_up": level_up,
        "level_name": get_level_name(stats.level),
    }


async def record_task_done(
    session: AsyncSession,
    user_id: int,
    was_on_time: bool,
) -> dict:
    """Call when a task is completed. Updates streak and awards XP."""
    stats = await get_or_create_stats(session, user_id)
    now = utc_now()
    today = now.date()

    # ── Update streak ──────────────────────────────────────────────────────
    streak_bonus = 0
    if stats.last_activity_date:
        last_date = stats.last_activity_date.astimezone(timezone.utc).date()
        diff = (today - last_date).days
        if diff == 0:
            pass  # same day, streak unchanged
        elif diff == 1:
            stats.streak_days += 1
            if stats.streak_days > stats.longest_streak:
                stats.longest_streak = stats.streak_days
            # Weekly streak bonus
            if stats.streak_days % 7 == 0:
                streak_bonus = XP_STREAK_WEEKLY_BONUS
        else:
            stats.streak_days = 1  # streak broken
    else:
        stats.streak_days = 1

    stats.last_activity_date = now
    stats.tasks_done_total += 1

    # ── Award XP ──────────────────────────────────────────────────────────
    xp = XP_TASK_DONE_ON_TIME if was_on_time else XP_TASK_DONE_LATE
    xp += streak_bonus

    result = await award_xp(session, user_id, xp)
    result["streak"] = stats.streak_days
    result["streak_bonus"] = streak_bonus
    return result


async def record_task_created(session: AsyncSession, user_id: int) -> None:
    await award_xp(session, user_id, XP_TASK_CREATED, "task_created")


async def get_profile(session: AsyncSession, user_id: int) -> dict:
    """Full profile data for /profile command."""
    stats = await get_or_create_stats(session, user_id)
    level = stats.level
    xp_needed, xp_in_level = xp_to_next_level(stats.xp, level)
    bar = level_progress_bar(stats.xp, level)

    return {
        "xp": stats.xp,
        "level": level,
        "level_name": get_level_name(level),
        "xp_needed": xp_needed,
        "xp_in_level": xp_in_level,
        "bar": bar,
        "streak": stats.streak_days,
        "longest_streak": stats.longest_streak,
        "tasks_done_total": stats.tasks_done_total,
    }
