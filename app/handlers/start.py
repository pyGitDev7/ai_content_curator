from __future__ import annotations

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import CommandStart
from loguru import logger

from app.config import settings
from app.database import async_session_factory
from app.models.models import User
from sqlalchemy import select

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return
    uid = message.from_user.id

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.telegram_id == uid))
        user = result.scalar_one_or_none()
        if user is None and uid == settings.super_admin_id:
            user = User(
                telegram_id=uid,
                username=message.from_user.username or "",
                is_super_admin=True,
            )
            session.add(user)
            await session.commit()

    if uid == settings.super_admin_id or user is not None:
        from app.handlers.panel import main_kb
        await message.answer(
            "🤖 <b>پنل مدیریت ربات کیوریتور AI</b>\n\nاز منوی زیر انتخاب کنید:",
            reply_markup=main_kb(),
            parse_mode="HTML",
        )
    else:
        await message.answer("⛔ دسترسی ندارید.")
        logger.warning(f"Unauthorized: {uid}")
