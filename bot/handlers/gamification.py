"""
Gamification handlers — /profile command and XP notifications.
"""
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.keyboards import main_menu_keyboard
from database.db import get_session
from services import get_or_create_user
from services.gamification_service import get_profile

logger = logging.getLogger(__name__)
router = Router(name="gamification")


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    async with get_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name,
        )
        profile = await get_profile(session, user.id)

    await message.answer(
        _profile_text(message.from_user.first_name, profile),
        parse_mode="HTML",
        reply_markup=_profile_keyboard(),
    )


@router.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery) -> None:
    async with get_session() as session:
        user = await get_or_create_user(
            session,
            telegram_id=callback.from_user.id,
            first_name=callback.from_user.first_name,
        )
        profile = await get_profile(session, user.id)

    await callback.message.edit_text(
        _profile_text(callback.from_user.first_name, profile),
        parse_mode="HTML",
        reply_markup=_profile_keyboard(),
    )
    await callback.answer()


def _profile_text(first_name: str, p: dict) -> str:
    streak_fire = "🔥" * min(p["streak"], 7)
    achievements = _get_achievements(p)
    ach_text = "  " + "\n  ".join(achievements) if achievements else "  None yet — complete tasks to earn!"

    return (
        f"👤 <b>{first_name}'s Profile</b>\n\n"
        f"🏅 <b>{p['level_name']}</b>  (Level {p['level']})\n"
        f"⚡ XP: <b>{p['xp']}</b>  (+{p['xp_needed']} to next level)\n"
        f"{p['bar']}\n\n"
        f"🔥 Streak: <b>{p['streak']} days</b>  {streak_fire}\n"
        f"🏆 Longest streak: <b>{p['longest_streak']} days</b>\n"
        f"✅ Tasks completed: <b>{p['tasks_done_total']}</b>\n\n"
        f"<b>🎖 Achievements:</b>\n{ach_text}"
    )


def _get_achievements(p: dict) -> list[str]:
    badges = []
    if p["tasks_done_total"] >= 1:
        badges.append("🎯 First Task — completed your first task")
    if p["tasks_done_total"] >= 10:
        badges.append("💪 Getting Things Done — 10 tasks completed")
    if p["tasks_done_total"] >= 50:
        badges.append("🚀 Productivity Machine — 50 tasks completed")
    if p["tasks_done_total"] >= 100:
        badges.append("👑 Century Club — 100 tasks completed")
    if p["streak"] >= 3:
        badges.append("🔥 On a Roll — 3-day streak")
    if p["streak"] >= 7:
        badges.append("⚡ Week Warrior — 7-day streak")
    if p["longest_streak"] >= 30:
        badges.append("🌟 Monthly Master — 30-day streak")
    if p["level"] >= 3:
        badges.append("💎 Rising Star — reached Level 3")
    if p["level"] >= 5:
        badges.append("🏆 Pro Planner — reached Level 5")
    return badges


def _profile_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Menu", callback_data="main_menu")
    builder.button(text="📊 Stats", callback_data="stats")
    builder.adjust(2)
    return builder.as_markup()


# ─── XP notification helper (called from task service hooks) ──────────────────

def format_xp_notification(result: dict) -> str:
    """Build a short XP gain message to append to task responses."""
    lines = [f"\n⚡ <b>+{result['xp_gained']} XP</b>"]

    if result.get("streak_bonus"):
        lines.append(f"🔥 Streak bonus: +{result['streak_bonus']} XP")

    if result.get("level_up"):
        lines.append(
            f"\n🎉 <b>LEVEL UP!</b> You are now {result['level_name']} (Level {result['level']})"
        )

    if result.get("streak", 0) > 1:
        lines.append(f"🔥 {result['streak']}-day streak!")

    return "".join(lines)
