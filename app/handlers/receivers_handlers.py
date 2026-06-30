from __future__ import annotations

import json

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

from app.database import async_session_factory
from app.models.models import Setting
from app.handlers.admin_panel import _is_authorized

router = Router(name="receivers")


class AddReceiverStates(StatesGroup):
    waiting_for_chat_id = State()


async def _get_receivers() -> list[int]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Setting.value).where(Setting.key == "receiver_ids")
        )
        val = result.scalar_one_or_none()
        if not val:
            return []
        try:
            return json.loads(val)
        except Exception:
            return []


async def _set_receivers(ids: list[int]) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Setting).where(Setting.key == "receiver_ids")
        )
        setting = result.scalar_one_or_none()
        value = json.dumps(ids)
        if setting:
            setting.value = value
        else:
            session.add(Setting(key="receiver_ids", value=value))
        await session.commit()


@router.callback_query(F.data == "menu:receivers")
async def cb_receivers_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    receivers = await _get_receivers()

    if receivers:
        list_text = "\n".join(f"  • `{rid}`" for rid in receivers)
        text = f"📬 *دریافت‌کنندگان فعلی:*\n{list_text}"
    else:
        text = "📬 هیچ دریافت‌کننده‌ای ثبت نشده است."

    buttons = [
        [InlineKeyboardButton(text="➕ افزودن Chat ID", callback_data="rcv:add")],
        [InlineKeyboardButton(text="🗑️ حذف Chat ID", callback_data="rcv:del_prompt")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:main")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "rcv:add")
async def cb_add_receiver(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "➕ *Chat ID* دریافت‌کننده را وارد کنید:\n\n"
        "می‌توانید چند Chat ID را با کاما جدا کنید.\n"
        "مثال: `123456789, -1001234567890`\n\n"
        "💡 برای پیدا کردن Chat ID کانال، پیامی به ربات @userinfobot فوروارد کنید.",
        parse_mode="Markdown",
    )
    await state.set_state(AddReceiverStates.waiting_for_chat_id)
    await callback.answer()


@router.message(AddReceiverStates.waiting_for_chat_id)
async def add_receiver_input(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("❌ لطفاً Chat ID را وارد کنید.")
        return

    new_ids = []
    for part in text.split(","):
        part = part.strip()
        try:
            cid = int(part)
            new_ids.append(cid)
        except ValueError:
            await message.answer(f"❌ «{part}» Chat ID معتبر نیست.")
            return

    current = await _get_receivers()
    for cid in new_ids:
        if cid not in current:
            current.append(cid)

    await _set_receivers(current)
    await state.clear()

    await message.answer(
        f"✅ {len(new_ids)} دریافت‌کننده اضافه شد.\n"
        f"کل دریافت‌کنندگان: {len(current)}"
    )


@router.callback_query(F.data == "rcv:del_prompt")
async def cb_del_receiver_prompt(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    receivers = await _get_receivers()
    if not receivers:
        await callback.answer("❌ دریافت‌کننده‌ای وجود ندارد", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"🗑️ {rid}",
            callback_data=f"rcv:del:{rid}",
        )]
        for rid in receivers
    ]
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:receivers")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        "🗑️ Chat ID موردنظر برای حذف را انتخاب کنید:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("rcv:del:"))
async def cb_del_receiver(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    chat_id = int((callback.data or "").split(":")[2])
    current = await _get_receivers()

    if chat_id in current:
        current.remove(chat_id)
        await _set_receivers(current)
        await callback.answer(f"✅ {chat_id} حذف شد")
    else:
        await callback.answer("❌ یافت نشد", show_alert=True)

    await cb_receivers_menu(callback)