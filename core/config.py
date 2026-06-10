"""
Core configuration — loaded from environment variables.
"""
from dataclasses import dataclass, field
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _default_db_url() -> str:
    url = os.getenv("DATABASE_URL", "")
    if url:
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    return f"sqlite+aiosqlite:///{BASE_DIR / 'smart_planner.db'}"


@dataclass(frozen=True)
class DatabaseConfig:
    url: str = field(default_factory=_default_db_url)
    echo: bool = field(default_factory=lambda: os.getenv("DB_ECHO", "false").lower() == "true")


@dataclass(frozen=True)
class BotConfig:
    token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))
    admin_ids: list[int] = field(
        default_factory=lambda: [
            int(i) for i in os.getenv("ADMIN_IDS", "").split(",") if i.strip()
        ]
    )
    webhook_host: str = field(default_factory=lambda: os.getenv("WEBHOOK_HOST", ""))
    webhook_path: str = field(default_factory=lambda: os.getenv("WEBHOOK_PATH", "/webhook"))


@dataclass(frozen=True)
class SchedulerConfig:
    reminder_minutes_before: int = field(
        default_factory=lambda: int(os.getenv("REMINDER_MINUTES_BEFORE", "60"))
    )
    overdue_check_interval: int = field(
        default_factory=lambda: int(os.getenv("OVERDUE_CHECK_INTERVAL", "300"))
    )


@dataclass(frozen=True)
class AIConfig:
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    enabled: bool = field(
        default_factory=lambda: bool(os.getenv("OPENAI_API_KEY", ""))
    )


@dataclass(frozen=True)
class AppConfig:
    bot: BotConfig = field(default_factory=BotConfig)
    db: DatabaseConfig = field(default_factory=DatabaseConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    ai: AIConfig = field(default_factory=AIConfig)

    @property
    def is_production(self) -> bool:
        return bool(os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RENDER"))

    @property
    def use_webhook(self) -> bool:
        return bool(self.bot.webhook_host)

    def validate(self) -> None:
        if not self.bot.token:
            raise ValueError("BOT_TOKEN is not set.")


settings = AppConfig()
