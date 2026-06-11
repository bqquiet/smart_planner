"""
AI Service — supports OpenAI and Groq (free tier).
Robust parser that handles any language and vague input gracefully.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from core.config import settings
from core.utils import utc_now

logger = logging.getLogger(__name__)


class ParsedTask(TypedDict, total=False):
    title: str
    description: str | None
    priority: str
    category: str | None
    deadline: datetime | None
    confidence: float


class SubtaskList(TypedDict):
    subtasks: list[str]
    explanation: str


def _get_client():
    try:
        from openai import AsyncOpenAI
        cfg = settings.ai
        kwargs = {"api_key": cfg.active_key}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        return AsyncOpenAI(**kwargs)
    except ImportError:
        logger.warning("openai package not installed.")
        return None


_PARSE_SYSTEM = """You are a task parser for a productivity Telegram bot.
The user writes in ANY language (Ukrainian, English, Russian, mixed slang, abbreviations).
Your job: extract structured data from whatever they write — even vague or short inputs.

ALWAYS return valid JSON. Never return empty or null for title.
If input is vague like "зробити англійську" — interpret it as a task about English homework/studying.

JSON schema (return ONLY this, no markdown):
{{
  "title": "concise task title (max 60 chars, same language as input)",
  "description": "extra details or null",
  "priority": "low|medium|high",
  "category": "work|personal|study|health|other",
  "deadline_iso": "ISO8601 UTC datetime or null",
  "confidence": 0.0-1.0
}}

Priority rules:
- high: терміново, asap, сьогодні/today, deadline/дедлайн, важливо, критично, срочно
- low:  колись, maybe, можливо, не горить, someday, потім
- medium: everything else

Category rules:
- work:    зустріч/meeting, проєкт/project, клієнт/client, звіт/report, офіс/office
- study:   англійська/english/homework, курс/course, іспит/exam, лекція/lecture, вчити/learn, домашнє
- health:  лікар/doctor, тренування/gym/workout, біг/run, дієта/diet, аптека/pharmacy
- personal: купити/buy, дім/home, родина/family, подарунок/gift, відпочинок/rest
- other:   anything else

Deadline parsing examples (current UTC: {now}):
- "завтра" / "tomorrow" → next day at 09:00 UTC
- "до п'ятниці" / "by friday" → next friday at 17:00 UTC
- "сьогодні" / "today" → today at 20:00 UTC
- "наступного тижня" / "next week" → 7 days from now at 09:00 UTC
- "через годину" / "in 1 hour" → now + 1 hour
- "18:00" → today at 18:00 UTC
- "25.12" or "dec 25" → that date at 09:00 UTC
- no time mentioned → null

IMPORTANT: if you cannot parse a deadline, set deadline_iso to null. Never fail the whole parse because of deadline."""

_PRIORITY_SYSTEM = """Rate the priority of this task. Return ONLY JSON:
{"priority": "low|medium|high", "reason": "one sentence"}"""

_SUBTASKS_SYSTEM = """Break this task into 3-6 concrete, actionable subtasks.
Return ONLY JSON (no markdown): {"subtasks": ["step 1", ...], "explanation": "brief note"}
Use the same language as the input. Make steps specific and short."""

_INSIGHTS_SYSTEM = """You are a productivity coach analyzing a user's task list.
Given task statistics, provide 2-3 short, actionable insights.
Return ONLY JSON: {"insights": ["insight 1", "insight 2"], "tip": "one motivational tip"}
Be specific, constructive, max 1-2 sentences each. Use the same language as the data."""


async def parse_task_from_text(user_text: str) -> ParsedTask | None:
    if not settings.ai.enabled:
        return None
    client = _get_client()
    if client is None:
        return None

    # Pre-process: normalize common abbreviations
    text = _preprocess(user_text)

    try:
        now_str = utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")
        response = await client.chat.completions.create(
            model=settings.ai.active_model,
            max_tokens=400,
            temperature=0.1,
            messages=[
                {"role": "system", "content": _PARSE_SYSTEM.format(now=now_str)},
                {"role": "user", "content": text},
            ],
        )
        raw = response.choices[0].message.content.strip()
        data = _safe_parse_json(raw)
        if data is None:
            # Fallback: build minimal task from text
            return _fallback_parse(user_text)
        result = _build_parsed_task(data)
        # If AI returned empty title, use original text
        if not result.get("title"):
            result["title"] = user_text[:60]
        return result
    except Exception as exc:
        logger.warning("AI parse_task failed: %s", exc)
        return _fallback_parse(user_text)


def _fallback_parse(text: str) -> ParsedTask:
    """When AI fails, build a basic task so the user never gets an error."""
    return ParsedTask(
        title=text[:60].strip(),
        description=None,
        priority="medium",
        category=_guess_category(text),
        deadline=_guess_deadline(text),
        confidence=0.3,
    )


def _preprocess(text: str) -> str:
    """Normalize abbreviations and common shorthands."""
    replacements = {
        r"\bенгл\b": "англійська",
        r"\bматем\b": "математика",
        r"\bдз\b": "домашнє завдання",
        r"\bасап\b": "терміново",
        r"\bшоб\b": "щоб",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _guess_category(text: str) -> str:
    text_lower = text.lower()
    study_words = ["англ", "english", "math", "матем", "іспит", "exam", "курс", "лекц", "вчити", "study", "homework", "дз"]
    work_words = ["зустріч", "meeting", "проєкт", "project", "звіт", "report", "клієнт", "офіс"]
    health_words = ["лікар", "doctor", "gym", "тренув", "workout", "аптека", "біг", "run"]
    personal_words = ["купити", "buy", "дім", "home", "родин", "family", "подарун", "gift"]
    for w in study_words:
        if w in text_lower:
            return "study"
    for w in work_words:
        if w in text_lower:
            return "work"
    for w in health_words:
        if w in text_lower:
            return "health"
    for w in personal_words:
        if w in text_lower:
            return "personal"
    return "other"


def _guess_deadline(text: str) -> datetime | None:
    """Simple keyword-based deadline guesser as fallback."""
    text_lower = text.lower()
    now = utc_now()
    if any(w in text_lower for w in ["завтра", "tomorrow"]):
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    if any(w in text_lower for w in ["сьогодні", "today"]):
        return now.replace(hour=20, minute=0, second=0, microsecond=0)
    if any(w in text_lower for w in ["наступного тижня", "next week"]):
        return (now + timedelta(weeks=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    return None


async def suggest_priority(title: str, description: str | None = None) -> str | None:
    if not settings.ai.enabled:
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        text = title + (f"\n{description}" if description else "")
        response = await client.chat.completions.create(
            model=settings.ai.active_model, max_tokens=100, temperature=0.1,
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
    if not settings.ai.enabled:
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        text = title + (f"\nContext: {description}" if description else "")
        response = await client.chat.completions.create(
            model=settings.ai.active_model, max_tokens=500, temperature=0.5,
            messages=[
                {"role": "system", "content": _SUBTASKS_SYSTEM},
                {"role": "user", "content": text},
            ],
        )
        data = _safe_parse_json(response.choices[0].message.content.strip())
        if data and isinstance(data.get("subtasks"), list):
            return SubtaskList(subtasks=data["subtasks"][:6], explanation=data.get("explanation", ""))
    except Exception as exc:
        logger.warning("AI generate_subtasks failed: %s", exc)
    return None


async def generate_productivity_insights(stats: dict) -> dict | None:
    """Analyze user stats and return actionable insights."""
    if not settings.ai.enabled:
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        stats_text = (
            f"Total tasks: {stats['total']}, Done: {stats['done']}, "
            f"Active: {stats['active']}, Overdue: {stats['overdue']}, "
            f"Productivity: {stats['productivity']}%, "
            f"Categories: {stats.get('by_category', {})}"
        )
        response = await client.chat.completions.create(
            model=settings.ai.active_model, max_tokens=300, temperature=0.7,
            messages=[
                {"role": "system", "content": _INSIGHTS_SYSTEM},
                {"role": "user", "content": stats_text},
            ],
        )
        return _safe_parse_json(response.choices[0].message.content.strip())
    except Exception as exc:
        logger.warning("AI insights failed: %s", exc)
    return None


def _safe_parse_json(raw: str) -> dict | None:
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to extract JSON from the middle of text
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


def _build_parsed_task(data: dict) -> ParsedTask:
    deadline: datetime | None = None
    raw_dl = data.get("deadline_iso")
    if raw_dl:
        try:
            deadline = datetime.fromisoformat(str(raw_dl).replace("Z", "+00:00"))
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
