from __future__ import annotations

from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.models import User
from app.handlers.admin_panel import _is_authorized, safe_edit

router = Router(name="admins")


class AddAdminStates(StatesGroup):
    waiting_for_telegram_id = State()


@router.callback_query(F.data == "menu:admins")
async def cb_admins_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    async with async_session_factory() as session:
        result = await session.execute(select(User).order_by(User.id))
        admins = result.scalars().all()

    await callback.answer()

    if not admins:
        text = "👥 هیچ مدیری ثبت نشده است."
    else:
        lines = ["👥 *لیست مدیران:*\n"]
        for admin in admins:
            badge = " 👑" if admin.is_super_admin else ""
            uname = f"@{admin.username}" if admin.username else "—"
            lines.append(f"  • {uname}{badge} | `{admin.telegram_id}`")
        text = "\n".join(lines)

    is_super = callback.from_user.id == settings.super_admin_id
    buttons: list[list[InlineKeyboardButton]] = []
    if is_super:
        buttons.append([InlineKeyboardButton(text="➕ افزودن مدیر", callback_data="adm:add")])
        buttons.append([InlineKeyboardButton(text="🗑️ حذف مدیر", callback_data="adm:del_prompt")])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:main")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await safe_edit(callback.message, text, kb)


@router.callback_query(F.data == "adm:add")
async def cb_add_admin(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or callback.from_user.id != settings.super_admin_id:
        await callback.answer("⛔ فقط سوپرادمین", show_alert=True)
        return

    await callback.answer()
    await safe_edit(callback.message, "➕ آیدی عددی مدیر جدید:\n\nمثال: `987654321`")
    await state.set_state(AddAdminStates.waiting_for_telegram_id)


@router.message(AddAdminStates.waiting_for_telegram_id)
async def add_admin_input(message: Message, state: FSMContext) -> None:
    if not message.from_user or message.from_user.id != settings.super_admin_id:
        return

    try:
        tid = int((message.text or "").strip())
    except ValueError:
        await message.answer("❌ آیدی باید عدد باشد.")
        return

    async with async_session_factory() as session:
        existing = await session.execute(select(User).where(User.telegram_id == tid))
        if existing.scalar_one_or_none():
            await message.answer("⚠️ قبلاً مدیر است.")
            await state.clear()
            return
        session.add(User(telegram_id=tid, is_super_admin=False))
        await session.commit()

    await state.clear()
    await message.answer(f"✅ مدیر جدید: `{tid}`", parse_mode="Markdown")


@router.callback_query(F.data == "adm:del_prompt")
async def cb_del_admin_prompt(callback: CallbackQuery) -> None:
    if not callback.from_user or callback.from_user.id != settings.super_admin_id:
        await callback.answer("⛔", show_alert=True)
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.is_super_admin == False).order_by(User.id)
        )
        admins = result.scalars().all()

    await callback.answer()

    if not admins:
        await safe_edit(callback.message, "❌ مدیر دیگری وجود ندارد.")
        return

    buttons = [
        [InlineKeyboardButton(text=f"🗑️ {a.username or a.telegram_id}", callback_data=f"adm:del:{a.id}")]
        for a in admins
    ]
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:admins")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await safe_edit(callback.message, "🗑️ مدیر موردنظر:", kb)


@router.callback_query(F.data.startswith("adm:del:"))
async def cb_del_admin(callback: CallbackQuery) -> None:
    if not callback.from_user or callback.from_user.id != settings.super_admin_id:
        await callback.answer("⛔", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    admin_db_id = int(parts[2]) if len(parts) >= 3 else 0

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == admin_db_id))
        admin = result.scalar_one_or_none()
        if not admin:
            await callback.answer("❌ یافت نشد", show_alert=True)
            return
        if admin.is_super_admin:
            await callback.answer("⛔ سوپرادمین قابل حذف نیست", show_alert=True)
            return
        await session.delete(admin)
        await session.commit()

    await callback.answer("✅ مدیر حذف شد")

    callback.data = "menu:admins"
    await cb_admins_menu(callback)
