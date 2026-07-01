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
from app.handlers.admin_panel import is_authorized

router = Router(name="admins")


class AddAdminStates(StatesGroup):
    waiting_for_id = State()


@router.callback_query(F.data == "adm_menu:show")
async def cb_admins_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    async with async_session_factory() as session:
        result = await session.execute(select(User).order_by(User.id))
        admins = list(result.scalars().all())

    if not admins:
        text = "👥 هیچ مدیری ثبت نشده است."
    else:
        lines = ["👥 لیست مدیران:\n"]
        for a in admins:
            badge = " 👑 سوپرادمین" if a.is_super_admin else ""
            uname = f"@{a.username}" if a.username else "—"
            lines.append(f"  • {uname}{badge} | ID: {a.telegram_id}")
        text = "\n".join(lines)

    is_super = callback.from_user and callback.from_user.id == settings.super_admin_id
    buttons: list[list[InlineKeyboardButton]] = []

    if is_super:
        buttons.append([InlineKeyboardButton(text="➕ افزودن مدیر", callback_data="admadd:start")])
        buttons.append([InlineKeyboardButton(text="🗑️ حذف مدیر", callback_data="admdel:list")])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="back:main")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ──────────── Add Admin ────────────

@router.callback_query(F.data == "admadd:start")
async def cb_add_admin(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or callback.from_user.id != settings.super_admin_id:
        await callback.answer("⛔ فقط سوپرادمین", show_alert=True)
        return

    await callback.message.edit_text(
        "➕ آیدی عددی تلگرام مدیر جدید را وارد کنید:\n\n"
        "مثال: 987654321"
    )
    await state.set_state(AddAdminStates.waiting_for_id)
    await callback.answer()


@router.message(AddAdminStates.waiting_for_id)
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
            await message.answer("⚠️ این کاربر قبلاً مدیر است.")
            await state.clear()
            return

        admin = User(telegram_id=tid, is_super_admin=False)
        session.add(admin)
        await session.commit()

    await state.clear()
    await message.answer(f"✅ مدیر جدید با آیدی {tid} اضافه شد.")


# ──────────── Delete Admin ────────────

@router.callback_query(F.data == "admdel:list")
async def cb_del_admin_list(callback: CallbackQuery) -> None:
    if not callback.from_user or callback.from_user.id != settings.super_admin_id:
        await callback.answer("⛔", show_alert=True)
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(User).where(User.is_super_admin == False).order_by(User.id)
        )
        admins = list(result.scalars().all())

    if not admins:
        await callback.answer("❌ مدیر دیگری وجود ندارد", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"🗑️ {a.username or a.telegram_id}",
            callback_data=f"admdel:{a.id}",
        )]
        for a in admins
    ]
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="adm_menu:show")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text("🗑️ مدیر موردنظر برای حذف:", reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("admdel:"))
async def cb_del_admin(callback: CallbackQuery) -> None:
    if not callback.from_user or callback.from_user.id != settings.super_admin_id:
        await callback.answer("⛔", show_alert=True)
        return

    admin_id = int(callback.data.split(":")[1])

    async with async_session_factory() as session:
        result = await session.execute(select(User).where(User.id == admin_id))
        admin = result.scalar_one_or_none()
        if not admin:
            await callback.answer("❌ یافت نشد", show_alert=True)
            return
        if admin.is_super_admin:
            await callback.answer("⛔ نمی‌توانید سوپرادمین را حذف کنید", show_alert=True)
            return
        await session.delete(admin)
        await session.commit()

    await callback.answer("✅ مدیر حذف شد")
    await cb_admins_menu(callback)
