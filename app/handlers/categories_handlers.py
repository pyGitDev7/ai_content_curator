from __future__ import annotations

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory
from app.models.models import Setting
from app.handlers.admin_panel import _is_authorized

router = Router(name="categories")

CATEGORIES = {
    "tutorial": "📚 آموزشی",
    "news": "📰 خبر",
    "tool": "🔧 ابزار",
    "prompt": "💬 پرامپت",
    "paper": "📄 مقاله علمی",
    "other": "📌 متفرقه",
}


async def _get_enabled_categories() -> list[str]:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Setting.value).where(Setting.key == "enabled_categories")
        )
        val = result.scalar_one_or_none()
        if not val:
            return list(CATEGORIES.keys())  # All enabled by default
        return [c.strip() for c in val.split(",") if c.strip()]


async def _set_enabled_categories(categories: list[str]) -> None:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Setting).where(Setting.key == "enabled_categories")
        )
        setting = result.scalar_one_or_none()
        value = ",".join(categories)
        if setting:
            setting.value = value
        else:
            session.add(Setting(key="enabled_categories", value=value))
        await session.commit()


@router.callback_query(F.data == "menu:categories")
async def cb_categories_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    enabled = await _get_enabled_categories()

    buttons: list[list[InlineKeyboardButton]] = []
    for key, label in CATEGORIES.items():
        is_on = key in enabled
        status = "✅" if is_on else "❌"
        buttons.append([
            InlineKeyboardButton(
                text=f"{status} {label}",
                callback_data=f"cat:toggle:{key}",
            )
        ])

    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        "📂 *دسته‌بندی‌ها*\n\n"
        "دسته‌بندی‌هایی که فعال هستند، در خلاصه روزانه ارسال می‌شوند.\n"
        "برای روشن/خاموش کردن، روی هر کدام کلیک کنید:",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cat:toggle:"))
async def cb_toggle_category(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    cat_key = (callback.data or "").split(":")[2]

    enabled = await _get_enabled_categories()

    if cat_key in enabled:
        enabled.remove(cat_key)
    else:
        enabled.append(cat_key)

    await _set_enabled_categories(enabled)

    # Refresh the menu
    await cb_categories_menu(callback)