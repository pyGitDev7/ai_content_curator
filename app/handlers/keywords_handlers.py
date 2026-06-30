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
from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory
from app.models.models import Keyword, Hashtag, AdminLog
from app.handlers.admin_panel import _is_authorized

router = Router(name="keywords")


class AddKeywordStates(StatesGroup):
    waiting_for_word = State()
    is_negative = State()


class AddHashtagStates(StatesGroup):
    waiting_for_tag = State()


# ──────────────────── Keywords & Hashtags Menu ────────────────────


@router.callback_query(F.data == "menu:keywords")
async def cb_keywords_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text="🔑 لیست کلمات کلیدی", callback_data="kw:list")],
        [InlineKeyboardButton(text="➕ افزودن کلمه مثبت", callback_data="kw:add:pos")],
        [InlineKeyboardButton(text="➖ افزودن کلمه منفی", callback_data="kw:add:neg")],
        [InlineKeyboardButton(text="🏷️ لیست هشتگ‌ها", callback_data="ht:list")],
        [InlineKeyboardButton(text="➕ افزودن هشتگ", callback_data="ht:add")],
        [InlineKeyboardButton(text="🗑️ حذف کلمه", callback_data="kw:del_prompt")],
        [InlineKeyboardButton(text="🗑️ حذف هشتگ", callback_data="ht:del_prompt")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:main")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "🏷️ *هشتگ‌ها و کلمات کلیدی*\n\n"
        "• کلمات مثبت: محتوا باید حداقل یکی از این‌ها را داشته باشد\n"
        "• کلمات منفی: محتوای حاوی این کلمات رد می‌شود",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


# ──────────────────── List Keywords ────────────────────


@router.callback_query(F.data == "kw:list")
async def cb_list_keywords(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    async with async_session_factory() as session:
        result = await session.execute(select(Keyword).order_by(Keyword.is_negative, Keyword.id))
        keywords = result.scalars().all()

    if not keywords:
        text = "🔑 هیچ کلمه کلیدی ثبت نشده است."
    else:
        positive = [kw for kw in keywords if not kw.is_negative]
        negative = [kw for kw in keywords if kw.is_negative]

        lines: list[str] = ["🔑 *کلمات کلیدی:*\n"]

        if positive:
            lines.append("✅ *کلمات مثبت:*")
            for kw in positive:
                lines.append(f"  • `{kw.word}` (ID: {kw.id})")
            lines.append("")

        if negative:
            lines.append("🚫 *کلمات منفی (مسدود):*")
            for kw in negative:
                lines.append(f"  • `{kw.word}` (ID: {kw.id})")

        text = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:keywords")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


# ──────────────────── Add Keyword ────────────────────


@router.callback_query(F.data.startswith("kw:add:"))
async def cb_add_keyword(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    mode = (callback.data or "").split(":")[2]  # "pos" or "neg"
    is_neg = mode == "neg"
    await state.update_data(is_negative=is_neg)

    kind = "منفی (مسدود)" if is_neg else "مثبت"
    await callback.message.edit_text(
        f"➕ کلمه کلیدی {kind} را وارد کنید:\n\n"
        "می‌توانید چند کلمه را با کاما جدا کنید.\n"
        "مثال: `AI, LLM, ChatGPT`",
        parse_mode="Markdown",
    )
    await state.set_state(AddKeywordStates.waiting_for_word)
    await callback.answer()


@router.message(AddKeywordStates.waiting_for_word)
async def add_keyword_input(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    data = await state.get_data()
    is_negative = data.get("is_negative", False)
    words_text = (message.text or "").strip()

    if not words_text:
        await message.answer("❌ لطفاً حداقل یک کلمه وارد کنید.")
        return

    words = [w.strip() for w in words_text.split(",") if w.strip()]

    async with async_session_factory() as session:
        added = []
        for word in words:
            kw = Keyword(word=word, is_negative=is_negative)
            session.add(kw)
            added.append(word)
        await session.commit()

    await state.clear()

    kind = "منفی" if is_negative else "مثبت"
    await message.answer(f"✅ کلمات {kind} اضافه شدند:\n• " + "\n• ".join(added))


# ──────────────────── Delete Keyword ────────────────────


@router.callback_query(F.data == "kw:del_prompt")
async def cb_del_keyword_prompt(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "🗑️ شناسه (ID) کلمه‌ای که می‌خواهید حذف کنید را بفرستید:\n\n"
        "مثال: `/del_kw 3`",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(F.text.startswith("/del_kw"))
async def cmd_del_keyword(message: Message) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("❌ مثال: `/del_kw 3`", parse_mode="Markdown")
        return

    try:
        kw_id = int(parts[1])
    except ValueError:
        await message.answer("❌ شناسه باید عدد باشد.")
        return

    async with async_session_factory() as session:
        result = await session.execute(select(Keyword).where(Keyword.id == kw_id))
        kw = result.scalar_one_or_none()
        if not kw:
            await message.answer(f"❌ کلمه با شناسه {kw_id} یافت نشد.")
            return

        word = kw.word
        await session.delete(kw)
        await session.commit()

    await message.answer(f"✅ کلمه «{word}» حذف شد.")


# ──────────────────── List Hashtags ────────────────────


@router.callback_query(F.data == "ht:list")
async def cb_list_hashtags(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    async with async_session_factory() as session:
        result = await session.execute(select(Hashtag).order_by(Hashtag.id))
        hashtags = result.scalars().all()

    if not hashtags:
        text = "🏷️ هیچ هشتگی ثبت نشده است."
    else:
        lines = ["🏷️ *هشتگ‌های فعال:*\n"]
        for ht in hashtags:
            lines.append(f"  • `#{ht.tag}` (ID: {ht.id})")
        text = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:keywords")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


# ──────────────────── Add Hashtag ────────────────────


@router.callback_query(F.data == "ht:add")
async def cb_add_hashtag(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "➕ هشتگ‌ها را وارد کنید (بدون # و با کاما جدا کنید):\n\n"
        "مثال: `ChatGPT, PromptEngineering, AItools`",
        parse_mode="Markdown",
    )
    await state.set_state(AddHashtagStates.waiting_for_tag)
    await callback.answer()


@router.message(AddHashtagStates.waiting_for_tag)
async def add_hashtag_input(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    tags_text = (message.text or "").strip()
    if not tags_text:
        await message.answer("❌ لطفاً حداقل یک هشتگ وارد کنید.")
        return

    tags = [t.strip().lstrip("#") for t in tags_text.split(",") if t.strip()]

    async with async_session_factory() as session:
        added = []
        for tag in tags:
            existing = await session.execute(select(Hashtag).where(Hashtag.tag == tag))
            if existing.scalar_one_or_none():
                continue
            ht = Hashtag(tag=tag)
            session.add(ht)
            added.append(tag)
        await session.commit()

    await state.clear()

    if added:
        await message.answer("✅ هشتگ‌ها اضافه شدند:\n• " + "\n• ".join(f"#{t}" for t in added))
    else:
        await message.answer("⚠️ همه هشتگ‌ها قبلاً ثبت شده بودند.")


# ──────────────────── Delete Hashtag ────────────────────


@router.callback_query(F.data == "ht:del_prompt")
async def cb_del_hashtag_prompt(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.message.edit_text(
        "🗑️ شناسه (ID) هشتگی که می‌خواهید حذف کنید:\n\n"
        "مثال: `/del_ht 2`",
        parse_mode="Markdown",
    )
    await callback.answer()


@router.message(F.text.startswith("/del_ht"))
async def cmd_del_hashtag(message: Message) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("❌ مثال: `/del_ht 2`", parse_mode="Markdown")
        return

    try:
        ht_id = int(parts[1])
    except ValueError:
        await message.answer("❌ شناسه باید عدد باشد.")
        return

    async with async_session_factory() as session:
        result = await session.execute(select(Hashtag).where(Hashtag.id == ht_id))
        ht = result.scalar_one_or_none()
        if not ht:
            await message.answer(f"❌ هشتگ با شناسه {ht_id} یافت نشد.")
            return

        tag = ht.tag
        await session.delete(ht)
        await session.commit()

    await message.answer(f"✅ هشتگ «#{tag}» حذف شد.")