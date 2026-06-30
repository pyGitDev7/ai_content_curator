from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from app.config import settings, BASE_DIR

# ──────────────────── Logging Setup ────────────────────

LOG_DIR = BASE_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(sys.stderr, level=settings.log_level, format="{time:HH:mm:ss} | {level} | {message}")
logger.add(
    str(LOG_DIR / "curator.log"),
    level="DEBUG",
    rotation="10 MB",
    retention="30 days",
    encoding="utf-8",
)

# ──────────────────── Global Bot Instance ────────────────────

_bot_instance: Bot | None = None


def get_bot_instance() -> Bot | None:
    return _bot_instance


# ──────────────────── Main Entry Point ────────────────────


async def main() -> None:
    global _bot_instance

    logger.info("=" * 50)
    logger.info("🤖 AI Content Curator Bot Starting...")
    logger.info("=" * 50)

    # ── Validate config ──
    if not settings.bot_token:
        logger.error("BOT_TOKEN is not set! Please check your .env file.")
        sys.exit(1)

    if not settings.super_admin_id:
        logger.error("SUPER_ADMIN_ID is not set! Please check your .env file.")
        sys.exit(1)

    # ── Initialize database ──
    from app.database import init_db, seed_defaults
    await init_db()
    await seed_defaults()
    logger.info("Database initialized and defaults seeded.")

    # ── Create bot and dispatcher ──
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    _bot_instance = bot

    dp = Dispatcher(storage=MemoryStorage())

    # ── Register routers ──
    from app.handlers.start import router as start_router
    from app.handlers.admin_panel import router as admin_router
    from app.handlers.sources_handlers import router as sources_router
    from app.handlers.keywords_handlers import router as keywords_router
    from app.handlers.categories_handlers import router as categories_router
    from app.handlers.receivers_handlers import router as receivers_router
    from app.handlers.schedule_handlers import router as schedule_router
    from app.handlers.admins_handlers import router as admins_router
    from app.handlers.system_handlers import router as system_router

    dp.include_router(start_router)
    dp.include_router(admin_router)
    dp.include_router(sources_router)
    dp.include_router(keywords_router)
    dp.include_router(categories_router)
    dp.include_router(receivers_router)
    dp.include_router(schedule_router)
    dp.include_router(admins_router)
    dp.include_router(system_router)

    logger.info("All routers registered.")

    # ── Setup scheduler ──
    from app.services.scheduler import setup_scheduler
    setup_scheduler()
    logger.info("Scheduler started.")

    # ── Setup Telethon (optional) ──
    if settings.telethon_api_id and settings.telethon_api_hash:
        logger.info("Telethon credentials found. Telegram channel monitoring is available.")
    else:
        logger.info("Telethon not configured. Telegram channel monitoring is disabled.")

    # ── Notify super admin ──
    try:
        await bot.send_message(
            chat_id=settings.super_admin_id,
            text="🤖 *ربات کیوریتور هوش مصنوعی فعال شد!*\n\n"
                 "برای دسترسی به پنل مدیریت، /start را بفرستید.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.warning(f"Could not notify super admin: {e}")

    # ── Start polling ──
    logger.info("Starting polling...")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        # Cleanup
        from app.services.scheduler import shutdown_scheduler
        from app.services.ai_service import ai_service

        shutdown_scheduler()
        await ai_service.close()
        await bot.session.close()
        logger.info("Bot shut down cleanly.")


if __name__ == "__main__":
    asyncio.run(main())