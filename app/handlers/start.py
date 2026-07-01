from __future__ import annotations

from aiogram import Router, F
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

    if uid == settings.super_admin_id:
        async with async_session_factory() as session:
            result = await session.execute(
                select(User).where(User.telegram_id == uid)
            )
            user = result.scalar_one_or_none()
            if user is None:
                user = User(
                    telegram_id=uid,
                    username=message.from_user.username or "",
                    is_super_admin=True,
                )
                session.add(user)
                await session.commit()
        from app.handlers.admin_panel import show_main_menu
        await show_main_menu(message)
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == uid)
        )
        user = result.scalar_one_or_none()

    if user is not None:
        from app.handlers.admin_panel import show_main_menu
        await show_main_menu(message)
        return

    await message.answer(
        "⛔ شما دسترسی به این ربات ندارید.\n"
        "برای دسترسی، آیدی شما باید توسط مدیر اصلی ثبت شود."
    )
    logger.warning(f"Unauthorized access attempt: {uid}")
