"""
Smart Planner Bot — entry point.
Supports both polling (local dev) and webhook (Railway/Render production).

Run locally:
    py -m bot.main

Deploy: push to Railway — it reads WEBHOOK_HOST automatically.
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.handlers import get_all_routers
from core.config import settings
from database.db import init_db
from services.reminder_service import create_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def _build_bot_and_dp() -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=settings.bot.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    for router in get_all_routers():
        dp.include_router(router)
    return bot, dp


# ─── Polling (local dev) ──────────────────────────────────────────────────────

async def run_polling() -> None:
    logger.info("Starting in POLLING mode (local dev)…")
    bot, dp = await _build_bot_and_dp()

    scheduler = create_scheduler(bot)
    scheduler.start()
    logger.info("Scheduler started.")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot stopped.")


# ─── Webhook (production) ─────────────────────────────────────────────────────

async def run_webhook() -> None:
    webhook_url = f"{settings.bot.webhook_host}{settings.bot.webhook_path}"
    logger.info("Starting in WEBHOOK mode: %s", webhook_url)

    bot, dp = await _build_bot_and_dp()
    scheduler = create_scheduler(bot)

    async def on_startup(app: web.Application) -> None:
        await bot.set_webhook(webhook_url)
        scheduler.start()
        logger.info("Webhook set to %s", webhook_url)

    async def on_shutdown(app: web.Application) -> None:
        scheduler.shutdown(wait=False)
        await bot.delete_webhook()
        await bot.session.close()
        logger.info("Webhook removed, bot stopped.")

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=settings.bot.webhook_path)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    port = int(__import__("os").getenv("PORT", "8080"))
    logger.info("Listening on port %d", port)
    web.run_app(app, host="0.0.0.0", port=port)


# ─── Entry point ──────────────────────────────────────────────────────────────

async def main() -> None:
    settings.validate()
    logger.info("Initialising database…")
    await init_db()

    if settings.use_webhook:
        await run_webhook()
    else:
        await run_polling()


if __name__ == "__main__":
    asyncio.run(main())
