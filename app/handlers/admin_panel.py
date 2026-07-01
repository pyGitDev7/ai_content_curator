from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from sqlalchemy import select, func as sqlfunc

from app.config import settings
from app.database import async_session_factory
from app.models.models import User, Source, ContentItem, DeliveredLog

router = Router(name="admin_panel")


async def is_authorized(uid: int) -> bool:
    if uid == settings.super_admin_id:
        return True
    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.telegram_id == uid))
        return result.scalar_one_or_none() is not None


def main_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="📊 داشبورد وضعیت", callback_data="dash:status")],
        [InlineKeyboardButton(text="📡 مدیریت منابع", callback_data="src_menu:show")],
        [InlineKeyboardButton(text="🏷️ هشتگ‌ها و کلمات", callback_data="kw_menu:show")],
        [InlineKeyboardButton(text="📂 دسته‌بندی‌ها", callback_data="cat_menu:show")],
        [InlineKeyboardButton(text="📬 دریافت‌کنندگان", callback_data="rcv_menu:show")],
        [InlineKeyboardButton(text="⏰ زمان‌بندی", callback_data="sch_menu:show")],
        [InlineKeyboardButton(text="👥 مدیران", callback_data="adm_menu:show")],
        [InlineKeyboardButton(text="🔧 ابزارهای سیستم", callback_data="sys_menu:show")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def show_main_menu(target) -> None:
    text = (
        "🤖 پنل مدیریت ربات کیوریتور هوش مصنوعی\n\n"
        "از منوی زیر بخش موردنظرتان را انتخاب کنید:"
    )
    kb = main_menu_keyboard()
    if isinstance(target, Message):
        await target.answer(text, reply_markup=kb)
    elif isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=kb)


@router.callback_query(F.data == "back:main")
async def cb_back_main(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return
    await show_main_menu(callback)
    await callback.answer()


@router.callback_query(F.data == "dash:status")
async def cb_status(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    async with async_session_factory() as session:
        active_res = await session.execute(
            select(sqlfunc.count(Source.id)).where(Source.is_active == True)
        )
        active_count = active_res.scalar() or 0

        total_res = await session.execute(select(sqlfunc.count(Source.id)))
        total_count = total_res.scalar() or 0

        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        today_res = await session.execute(
            select(sqlfunc.count(ContentItem.id)).where(
                ContentItem.created_at >= today_start
            )
        )
        today_count = today_res.scalar() or 0

        deliv_res = await session.execute(
            select(sqlfunc.count(DeliveredLog.id)).where(
                DeliveredLog.delivered_at >= today_start
            )
        )
        delivered_count = deliv_res.scalar() or 0

    from app.config import settings as cfg
    openai_ok = "✅" if cfg.openai_api_key else "❌"
    mimo_ok = "✅" if cfg.mimo_api_key and cfg.mimo_api_key != "your-mimo-api-key" else "❌"
    deepseek_ok = "✅" if cfg.deepseek_api_key else "❌"
    telethon_ok = "✅" if cfg.telethon_api_id else "❌"
    twitter_ok = "✅" if cfg.twitter_bearer_token else "❌"

    text = (
        "📊 داشبورد وضعیت\n\n"
        f"📡 منابع فعال: {active_count} از {total_count}\n"
        f"📥 مطالب امروز: {today_count}\n"
        f"📤 ارسال‌شده امروز: {delivered_count}\n\n"
        "🔌 وضعیت APIها:\n"
        f"  OpenAI: {openai_ok}\n"
        f"  MiMo: {mimo_ok}\n"
        f"  DeepSeek: {deepseek_ok}\n"
        f"  Telethon: {telethon_ok}\n"
        f"  Twitter: {twitter_ok}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="dash:status")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back:main")],
    ])

    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()
