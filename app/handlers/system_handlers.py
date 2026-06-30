from __future__ import annotations

import os
import asyncio
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BufferedInputFile,
)
from loguru import logger
from sqlalchemy import text

from app.config import settings, BASE_DIR
from app.database import async_session_factory, engine
from app.models.models import AdminLog
from app.handlers.admin_panel import _is_authorized

router = Router(name="system")


@router.callback_query(F.data == "menu:system")
async def cb_system_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text="💾 بکاپ دیتابیس", callback_data="sys:backup")],
        [InlineKeyboardButton(text="📋 لاگ‌های امروز", callback_data="sys:logs")],
        [InlineKeyboardButton(text="🔄 ری‌استارت شیدولر", callback_data="sys:restart")],
        [InlineKeyboardButton(text="🧹 پاک کردن کش", callback_data="sys:cache")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:main")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "🔧 *ابزارهای سیستم*",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data == "sys:backup")
async def cb_backup(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.answer("⏳ در حال تهیه بکاپ...")

    db_path = BASE_DIR / "data" / "curator.db"
    if not db_path.exists():
        await callback.message.answer("❌ فایل دیتابیس یافت نشد.")
        return

    try:
        import aiofiles
        async with aiofiles.open(db_path, "rb") as f:
            data = await f.read()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file = BufferedInputFile(data, filename=f"curator_backup_{timestamp}.db")
        await callback.message.answer_document(file, caption="💾 بکاپ دیتابیس")
    except Exception as e:
        logger.error(f"Backup error: {e}")
        await callback.message.answer(f"❌ خطا در تهیه بکاپ: {e}")


@router.callback_query(F.data == "sys:logs")
async def cb_logs(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    log_path = BASE_DIR / "data" / "logs" / "curator.log"
    if not log_path.exists():
        # Try default loguru path
        log_path = BASE_DIR / "logs" / "curator.log"

    if not log_path.exists():
        await callback.message.answer("📋 فایل لاگ یافت نشد. لاگ‌ها ممکن است در stdout نوشته شوند.")
        await callback.answer()
        return

    try:
        import aiofiles
        async with aiofiles.open(log_path, "r") as f:
            content = await f.read()

        # Get last 3000 characters
        if len(content) > 3000:
            content = "...\n" + content[-3000:]

        await callback.message.answer(
            f"📋 *لاگ‌های اخیر:*\n\n```\n{content}\n```",
            parse_mode="Markdown",
        )
    except Exception as e:
        await callback.message.answer(f"❌ خطا: {e}")

    await callback.answer()


@router.callback_query(F.data == "sys:restart")
async def cb_restart_scheduler(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    try:
        from app.services.scheduler import scheduler, setup_scheduler, shutdown_scheduler

        shutdown_scheduler()
        await asyncio.sleep(1)
        setup_scheduler()

        await callback.message.answer("✅ شیدولر با موفقیت ری‌استارت شد.")
    except Exception as e:
        logger.error(f"Scheduler restart error: {e}")
        await callback.message.answer(f"❌ خطا در ری‌استارت: {e}")

    await callback.answer()


@router.callback_query(F.data == "sys:cache")
async def cb_clear_cache(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    # Close and recreate AI service client
    from app.services.ai_service import ai_service
    await ai_service.close()

    await callback.message.answer("✅ کش سرویس AI پاک شد.")
    await callback.answer()


# ──────────────────── Quick Commands ────────────────────


@router.message(F.text == "/status")
async def cmd_status(message: Message) -> None:
    """Quick status command."""
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    from app.handlers.admin_panel import cb_status
    # Create a fake-like callback to reuse the status handler
    from aiogram.types import CallbackQuery as CQ
    # Just send a simpler inline keyboard
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 داشبورد", callback_data="menu:status")],
    ])
    await message.answer("برای مشاهده وضعیت، از دکمه زیر استفاده کنید:", reply_markup=kb)


@router.message(F.text == "/crawl")
async def cmd_crawl(message: Message) -> None:
    """Quick manual crawl command."""
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    from app.services.scheduler import _run_collectors
    asyncio.create_task(_run_collectors())
    await message.answer("🚀 کراول شروع شد. نتایج به‌زودی در دیتابیس ذخیره می‌شوند.")


@router.message(F.text == "/digest")
async def cmd_digest(message: Message) -> None:
    """Quick manual digest command."""
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    from app.services.delivery import deliver_digest
    from aiogram import Bot
    await deliver_digest(message.bot)
    await message.answer("📤 خلاصه روزانه ارسال شد.")