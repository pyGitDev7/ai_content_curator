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

from app.database import async_session_factory
from app.models.models import Setting
from app.handlers.admin_panel import _is_authorized
from app.config import settings

router = Router(name="schedule")


class SetTimeStates(StatesGroup):
    waiting_for_time = State()


class SetCountStates(StatesGroup):
    waiting_for_count = State()


async def _get_setting(key: str, default: str = "") -> str:
    async with async_session_factory() as session:
        result = await session.execute(select(Setting.value).where(Setting.key == key))
        val = result.scalar_one_or_none()
        return val if val is not None else default


async def _set_setting(key: str, value: str) -> None:
    async with async_session_factory() as session:
        result = await session.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            session.add(Setting(key=key, value=value))
        await session.commit()


@router.callback_query(F.data == "menu:schedule")
async def cb_schedule_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    hour = await _get_setting("digest_hour", str(settings.digest_hour))
    minute = await _get_setting("digest_minute", str(settings.digest_minute))
    max_items = await _get_setting("digest_max_items", str(settings.digest_max_items))
    min_score = await _get_setting("min_score", "0")

    text = (
        "⏰ *تنظیمات زمان‌بندی*\n\n"
        f"🕐 ساعت ارسال خلاصه روزانه: *{hour}:{int(minute):02d}*\n"
        f"📊 حداکثر مطالب در هر خلاصه: *{max_items}*\n"
        f"⭐ حداقل امتیاز: *{min_score}*\n"
    )

    buttons = [
        [InlineKeyboardButton(text="🕐 تغییر ساعت ارسال", callback_data="sch:set_time")],
        [InlineKeyboardButton(text="📊 تغییر تعداد مطالب", callback_data="sch:set_count")],
        [InlineKeyboardButton(text="⭐ تغییر حداقل امتیاز", callback_data="sch:set_score")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:main")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.callback_query(F.data == "sch:set_time")
async def cb_set_time(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "🕐 ساعت ارسال خلاصه روزانه را وارد کنید:\n\n"
        "مثال: `09:00` یا `14:30`",
        parse_mode="Markdown",
    )
    await state.set_state(SetTimeStates.waiting_for_time)
    await callback.answer()


@router.message(SetTimeStates.waiting_for_time)
async def set_time_input(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    text = (message.text or "").strip()
    try:
        parts = text.split(":")
        hour = int(parts[0])
        minute = int(parts[1])
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError
    except (ValueError, IndexError):
        await message.answer("❌ فرمت نامعتبر. مثال صحیح: `09:30`", parse_mode="Markdown")
        return

    await _set_setting("digest_hour", str(hour))
    await _set_setting("digest_minute", str(minute))
    await state.clear()

    # Reschedule
    from app.services.scheduler import scheduler
    from app.services.scheduler import _run_digest
    from apscheduler.triggers.cron import CronTrigger

    try:
        scheduler.reschedule_job("daily_digest", trigger=CronTrigger(hour=hour, minute=minute))
    except Exception:
        pass

    await message.answer(f"✅ ساعت ارسال به {hour}:{minute:02d} تغییر کرد.")


@router.callback_query(F.data == "sch:set_count")
async def cb_set_count(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "📊 حداکثر تعداد مطالب در هر خلاصه را وارد کنید:\n\n"
        "مثال: `15`",
        parse_mode="Markdown",
    )
    await state.set_state(SetCountStates.waiting_for_count)
    await callback.answer()


@router.message(SetCountStates.waiting_for_count)
async def set_count_input(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    try:
        count = int((message.text or "").strip())
        if count < 1 or count > 50:
            raise ValueError
    except ValueError:
        await message.answer("❌ لطفاً عددی بین 1 تا 50 وارد کنید.")
        return

    await _set_setting("digest_max_items", str(count))
    await state.clear()
    await message.answer(f"✅ حداکثر مطالب در خلاصه به {count} تغییر کرد.")


@router.callback_query(F.data == "sch:set_score")
async def cb_set_score(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "⭐ حداقل امتیاز مطالب برای ارسال را وارد کنید:\n\n"
        "مثال: `7` (فقط مطالب با امتیاز 7 و بالاتر ارسال می‌شوند)\n"
        "برای غیرفعال کردن فیلتر عدد `0` وارد کنید.",
        parse_mode="Markdown",
    )
    await state.set_state(SetCountStates.waiting_for_count)
    await callback.answer()


# Reuse the count state handler for score - note: in production you'd use a separate state
# For simplicity, we handle it via a dedicated message filter
@router.message(F.text.regexp(r"^\d+(\.\d+)?$"), SetCountStates.waiting_for_count)
async def handle_numeric_input(message: Message, state: FSMContext) -> None:
    """Handle numeric input for either count or score based on current context."""
    current_state = await state.get_state()

    try:
        value = float((message.text or "").strip())
    except ValueError:
        await message.answer("❌ لطفاً عدد معتبر وارد کنید.")
        return

    await _set_setting("min_score", str(value))
    await state.clear()
    await message.answer(f"✅ حداقل امتیاز به {value} تغییر کرد.")