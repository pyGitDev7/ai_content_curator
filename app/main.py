from __future__ import annotations

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from loguru import logger

from app.config import settings, BASE_DIR

LOG_DIR = BASE_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger.remove()
logger.add(sys.stderr, level=settings.log_level, format="{time:HH:mm:ss} | {level} | {message}")
logger.add(str(LOG_DIR / "curator.log"), level="DEBUG", rotation="10 MB", retention="30 days", encoding="utf-8")

_bot_instance: Bot | None = None


def get_bot_instance() -> Bot | None:
    return _bot_instance


async def main() -> None:
    global _bot_instance

    logger.info("🤖 AI Curator Bot Starting...")

    if not settings.bot_token:
        logger.error("BOT_TOKEN not set!")
        sys.exit(1)
    if not settings.super_admin_id:
        logger.error("SUPER_ADMIN_ID not set!")
        sys.exit(1)

    from app.database import init_db, seed_defaults
    await init_db()
    await seed_defaults()
    logger.info("Database ready.")

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    _bot_instance = bot
    dp = Dispatcher(storage=MemoryStorage())

    from app.handlers.wizard import router as r_wizard
    from app.handlers.panel import router as r_panel
    from app.handlers.commands import router as r_commands
    from app.handlers.start import router as r_start

    dp.include_router(r_wizard)
    dp.include_router(r_panel)
    dp.include_router(r_commands)
    dp.include_router(r_start)

    logger.info("Routers registered.")

    from app.services.scheduler import setup_scheduler
    setup_scheduler()

    if settings.telethon_api_id and settings.telethon_api_hash:
        logger.info("Telethon available.")
    else:
        logger.info("Telethon not configured.")

    try:
        await bot.send_message(
            chat_id=settings.super_admin_id,
            text="🤖 <b>ربات فعال شد!</b>\n\n/start = خوش‌آمد\n/panel = پنل مدیریت",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"Notify admin failed: {e}")

    async def delayed_first_collect():
        await asyncio.sleep(30)
        logger.info("Running first collection...")
        from app.services.scheduler import _run_collectors
        await _run_collectors()

    asyncio.create_task(delayed_first_collect())

    logger.info("Polling started.")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        from app.services.scheduler import shutdown_scheduler
        from app.services.ai_service import ai_service
        shutdown_scheduler()
        await ai_service.close()
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    asyncio.run(main())
