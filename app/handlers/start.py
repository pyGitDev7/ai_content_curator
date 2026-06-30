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


def is_admin(telegram_id: int) -> bool:
    """Check if a user is an admin (for use in filters)."""
    # This is a quick check; actual admin check happens in the panel
    return True  # We'll do proper checking in the admin panel


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not message.from_user:
        return

    uid = message.from_user.id

    # Check if super admin or registered admin
    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == uid)
        )
        user = result.scalar_one_or_none()

        if user is None and uid == settings.super_admin_id:
            # First time super admin
            user = User(
                telegram_id=uid,
                username=message.from_user.username or "",
                is_super_admin=True,
            )
            session.add(user)
            await session.commit()
            user = user

    if uid != settings.super_admin_id and (user is None or not user):
        await message.answer(
            "⛔ شما دسترسی به این ربات ندارید.\n"
            "برای دسترسی، آیدی شما باید توسط مدیر اصلی ثبت شود."
        )
        logger.warning(f"Unauthorized access attempt: {uid}")
        return

    # Import and show admin panel
    from app.handlers.admin_panel import show_main_menu
    await show_main_menu(message)