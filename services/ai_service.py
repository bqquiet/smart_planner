"""
AI Service — OpenAI integration for smart task parsing.

Features:
  1. parse_task_from_text  — extract title, description, priority, category,
                             deadline from a free-form message
  2. suggest_priority      — re-evaluate priority for an existing task
  3. generate_subtasks     — break a big task into smaller steps

All functions gracefully degrade: if OpenAI is unavailable or the key is
missing, they return None so callers can fall back to the manual flow.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TypedDict

from core.config import settings
from core.utils import utc_now

logger = logging.getLogger(__name__)


# ─── Return types ─────────────────────────────────────────────────────────────

class ParsedTask(TypedDict, total=False):
    title: str
    description: str | None
    priority: str          # low | medium | high
    category: str | None   # work | personal | study | health | other
    deadline: datetime | None
    confidence: float      # 0–1, how confident the model is


class SubtaskList(TypedDict):
    subtasks: list[str]
    explanation: str


# ─── Client factory ───────────────────────────────────────────────────────────

def _get_client():
    """Lazy-import openai so the bot starts even without the package."""
    try:
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=settings.ai.openai_api_key)
    except ImportError:
        logger.warning("openai package not installed — AI features disabled.")
        return None


# ─── System prompts ───────────────────────────────────────────────────────────

_PARSE_SYSTEM = """
You are a smart task parser for a Ukrainian productivity bot.
The user writes a task in any language (mostly Ukrainian or English).
Extract structured data and return ONLY a valid JSON object — no markdown, no explanation.

JSON schema:
{
  "title": "short task title (max 60 chars)",
  "description": "additional details or null",
  "priority": "low | medium | high",
  "category": "work | personal | study | health | other",
  "deadline_iso": "ISO 8601 datetime in UTC or null",
  "confidence": 0.0-1.0
}

Priority rules:
- high: urgent words (терміново, ASAP, сьогодні, deadline, важливо, критично)
- low:  vague future or optional tasks
- medium: everything else

Category rules:
- work:     зустріч, проєкт, дедлайн, клієнт, офіс, звіт, презентація
- study:    курс, лекція, іспит, завдання, домашнє, університет
- health:   лікар, тренування, gym, біг, дієта, аптека
- personal: купити, дім, родина, відпочинок, подарунок
- other:    anything else

Current UTC datetime: {now}
"""

_PRIORITY_SYSTEM = """
You are a task priority advisor.
Given a task title and description, return ONLY a JSON object:
{"priority": "low | medium | high", "reason": "one sentence explanation"}
"""

_SUBTASKS_SYSTEM = """
You are a productivity coach. Break down the given task into 3-6 concrete subtasks.
Return ONLY a JSON object:
{"subtasks": ["step 1", "step 2", ...], "explanation": "brief note"}
Subtasks should be short, actionable, in the same language as the input.
"""


# ─── Main functions ───────────────────────────────────────────────────────────

async def parse_task_from_text(user_text: str) -> ParsedTask | None:
    """
    Parse a free-form task description into structured data.

    Example input:  "терміново здати звіт по Q2 до п'ятниці 18:00"
    Example output: {title: "Здати звіт Q2", priority: "high",
                     category: "work", deadline: datetime(...)}
    """
    if not settings.ai.enabled:
        return None

    client = _get_client()
    if client is None:
        return None

    try:
        now_str = utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
        response = await client.chat.completions.create(
            model=settings.ai.model,
            max_tokens=300,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": _PARSE_SYSTEM.format(now=now_str),
                },
                {"role": "user", "content": user_text},
            ],
        )

        raw = response.choices[0].message.content.strip()
        data = _safe_parse_json(raw)
        if data is None:
            return None

        return _build_parsed_task(data)

    except Exception as exc:
        logger.warning("AI parse_task failed: %s", exc)
        return None


async def suggest_priority(title: str, description: str | None = None) -> str | None:
    """
    Ask AI to suggest the best priority for an existing task.
    Returns 'low' | 'medium' | 'high' or None on failure.
    """
    if not settings.ai.enabled:
        return None

    client = _get_client()
    if client is None:
        return None

    text = title
    if description:
        text += f"\n{description}"

    try:
        response = await client.chat.completions.create(
            model=settings.ai.model,
            max_tokens=100,
            temperature=0.1,
            messages=[
                {"role": "system", "content": _PRIORITY_SYSTEM},
                {"role": "user", "content": text},
            ],
        )
        data = _safe_parse_json(response.choices[0].message.content.strip())
        if data and data.get("priority") in ("low", "medium", "high"):
            return data["priority"]
    except Exception as exc:
        logger.warning("AI suggest_priority failed: %s", exc)

    return None


async def generate_subtasks(title: str, description: str | None = None) -> SubtaskList | None:
    """
    Generate a list of subtasks for a complex task.
    Returns a SubtaskList dict or None on failure.
    """
    if not settings.ai.enabled:
        return None

    client = _get_client()
    if client is None:
        return None

    text = title
    if description:
        text += f"\nКонтекст: {description}"

    try:
        response = await client.chat.completions.create(
            model=settings.ai.model,
            max_tokens=400,
            temperature=0.5,
            messages=[
                {"role": "system", "content": _SUBTASKS_SYSTEM},
                {"role": "user", "content": text},
            ],
        )
        data = _safe_parse_json(response.choices[0].message.content.strip())
        if data and isinstance(data.get("subtasks"), list):
            return SubtaskList(
                subtasks=data["subtasks"][:6],
                explanation=data.get("explanation", ""),
            )
    except Exception as exc:
        logger.warning("AI generate_subtasks failed: %s", exc)

    return None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_parse_json(raw: str) -> dict | None:
    """Strip markdown fences and parse JSON safely."""
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.debug("Could not parse AI JSON response: %r", raw)
        return None


def _build_parsed_task(data: dict) -> ParsedTask:
    """Convert raw AI JSON dict into a typed ParsedTask."""
    from zoneinfo import ZoneInfo

    deadline: datetime | None = None
    raw_dl = data.get("deadline_iso")
    if raw_dl:
        try:
            deadline = datetime.fromisoformat(raw_dl.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            deadline = None

    priority = data.get("priority", "medium")
    if priority not in ("low", "medium", "high"):
        priority = "medium"

    category = data.get("category")
    if category not in ("work", "personal", "study", "health", "other"):
        category = None

    return ParsedTask(
        title=str(data.get("title", ""))[:256].strip(),
        description=data.get("description") or None,
        priority=priority,
        category=category,
        deadline=deadline,
        confidence=float(data.get("confidence", 0.8)),
    )
