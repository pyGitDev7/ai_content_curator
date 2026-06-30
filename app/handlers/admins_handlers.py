from __future__ import annotations

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from loguru import logger
from sqlalchemy import select, func as sqlfunc

from app.config import settings
from app.database import async_session_factory
from app.models.models import User, Source, ContentItem, DeliveredLog

router = Router(name="admin_panel")


async def _is_authorized(uid: int) -> bool:
    if uid == settings.super_admin_id:
        return True
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.telegram_id == uid))
        return result.scalar_one_or_none() is not None


def main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📊 داشبورد وضعیت", callback_data="menu:status")],
        [InlineKeyboardButton(text="📡 مدیریت منابع", callback_data="menu:sources")],
        [InlineKeyboardButton(text="🏷️ هشتگ‌ها و کلمات", callback_data="menu:keywords")],
        [InlineKeyboardButton(text="📂 دسته‌بندی‌ها", callback_data="menu:categories")],
        [InlineKeyboardButton(text="📬 دریافت‌کنندگان", callback_data="menu:receivers")],
        [InlineKeyboardButton(text="⏰ زمان‌بندی", callback_data="menu:schedule")],
        [InlineKeyboardButton(text="👥 مدیران", callback_data="menu:admins")],
        [InlineKeyboardButton(text="🔧 ابزارهای سیستم", callback_data="menu:system")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def show_main_menu(target) -> None:
    text = (
        "🤖 *پنل مدیریت ربات کیوریتور هوش مصنوعی*\n\n"
        "از منوی زیر بخش موردنظرتان را انتخاب کنید:"
    )
    kb = main_menu_keyboard()
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb, parse_mode="Markdown")
    elif isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔ دسترسی ندارید", show_alert=True)
        return
    await show_main_menu(callback)
    await callback.answer()


@router.callback_query(F.data == "menu:status")
async def cb_status(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    async with async_session_factory() as session:
        active_sources = await session.execute(
            select(sqlfunc.count(Source.id)).where(Source.is_active == True)
        )
        active_count = active_sources.scalar() or 0

        total_sources = await session.execute(select(sqlfunc.count(Source.id)))
        total_count = total_sources.scalar() or 0

        from datetime import datetime, timezone
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        today_items = await session.execute(
            select(sqlfunc.count(ContentItem.id)).where(
                ContentItem.created_at >= today_start
            )
        )
        today_count = today_items.scalar() or 0

        today_delivered = await session.execute(
            select(sqlfunc.count(DeliveredLog.id)).where(
                DeliveredLog.delivered_at >= today_start
            )
        )
        delivered_count = today_delivered.scalar() or 0

    from app.config import settings as cfg
    openai_ok = "✅" if cfg.openai_api_key else "❌"
    mimo_ok = "✅" if cfg.mimo_api_key else "❌"
    deepseek_ok = "✅" if cfg.deepseek_api_key else "❌"
    telethon_ok = "✅" if cfg.telethon_api_id else "❌"
    twitter_ok = "✅" if cfg.twitter_bearer_token else "❌"

    text = (
        "📊 *داشبورد وضعیت*\n\n"
        f"📡 منابع فعال: *{active_count}* از *{total_count}*\n"
        f"📥 مطالب امروز: *{today_count}*\n"
        f"📤 ارسال‌شده امروز: *{delivered_count}*\n\n"
        "🔌 *وضعیت APIها:*\n"
        f"  OpenAI: {openai_ok}\n"
        f"  MiMo: {mimo_ok}\n"
        f"  DeepSeek: {deepseek_ok}\n"
        f"  Telethon: {telethon_ok}\n"
        f"  Twitter: {twitter_ok}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="menu:status")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:main")],
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "menu:sources")
async def cb_sources_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text="📋 لیست منابع", callback_data="src:list:0")],
        [InlineKeyboardButton(text="➕ افزودن منبع جدید", callback_data="src:add")],
        [InlineKeyboardButton(text="🗑️ حذف منبع", callback_data="src:del_prompt")],
        [InlineKeyboardButton(text="🔄 کراول دستی (همه)", callback_data="src:crawl_all")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:main")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "📡 *مدیریت منابع*\n\nاز گزینه‌های زیر استفاده کنید:",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()