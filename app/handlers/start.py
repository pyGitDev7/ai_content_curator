from __future__ import annotations

from aiogram import Router
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
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

    is_admin = (uid == settings.super_admin_id) or (user is not None)

    if is_admin:
        name = message.from_user.first_name or "ادمین"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🤖 پنل مدیریت", callback_data="p:main")],
        ])
        await message.answer(
            f"سلام <b>{name}</b> 👋\n\n"
            f"من ربات کیوریتور هوش مصنوعی هستم.\n"
            f"از دکمه زیر به پنل مدیریت برو:\n\n"
            f"📌 همچنین می‌تونی از <code>/panel</code> استفاده کنی.",
            reply_markup=kb,
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "سلام! 👋\n\nمن یه ربات کیوریتور هوش مصنوعی هستم.\n"
            "به این ربات دسترسی ندارید.\n\n"
            "برای دسترسی، آیدی شما باید توسط مدیر ثبت شود.",
        )
        logger.warning(f"Unauthorized /start: {uid}")
