from __future__ import annotations

import asyncio

from aiogram import Router, F
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup

from app.config import settings
from app.database import async_session_factory
from app.models.models import User
from sqlalchemy import select

router = Router(name="commands")


async def is_auth(uid):
    if uid == settings.super_admin_id:
        return True
    async with async_session_factory() as s:
        r = await s.execute(select(User).where(User.telegram_id == uid))
        return r.scalar_one_or_none() is not None


@router.message(F.text == "/panel")
async def cmd_panel(msg: Message):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    from app.handlers.panel import main_kb
    await msg.answer("🤖 <b>پنل مدیریت</b>", reply_markup=main_kb(), parse_mode="HTML")


@router.message(F.text == "/crawl")
async def cmd_crawl(msg: Message):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    from app.services.scheduler import _run_collectors
    asyncio.create_task(_run_collectors())
    await msg.answer("🚀 کراول شروع شد.")


@router.message(F.text == "/digest")
async def cmd_digest(msg: Message):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    from app.services.delivery import deliver_digest
    await deliver_digest(msg.bot)
    await msg.answer("📤 ارسال شد.")


@router.message(F.text == "/status")
async def cmd_status(msg: Message):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 داشبورد", callback_data="p:status")],
        [InlineKeyboardButton(text="🤖 پنل", callback_data="p:main")],
    ])
    await msg.answer("از دکمه‌ها:", reply_markup=kb)
