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
from loguru import logger
from sqlalchemy import select, update

from app.config import settings
from app.database import async_session_factory
from app.models.models import Source, AdminLog
from app.handlers.admin_panel import _is_authorized

router = Router(name="sources")


# ──────────────────── FSM States ────────────────────


class AddSourceStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_name = State()
    waiting_for_config = State()


# ──────────────────── List Sources ────────────────────


@router.callback_query(F.data.startswith("src:list"))
async def cb_list_sources(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    page = 0
    parts = (callback.data or "").split(":")
    if len(parts) >= 3:
        try:
            page = int(parts[2])
        except ValueError:
            pass

    per_page = 8
    offset = page * per_page

    async with async_session_factory() as session:
        result = await session.execute(
            select(Source).order_by(Source.id).offset(offset).limit(per_page)
        )
        sources = result.scalars().all()

        total_result = await session.execute(select(Source))
        all_sources = total_result.scalars().all()
        total = len(all_sources)

    if not sources:
        text = "📋 هیچ منبعی ثبت نشده است."
        buttons = [[InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:sources")]]
    else:
        lines: list[str] = ["📋 *لیست منابع:*\n"]
        for src in sources:
            status = "🟢" if src.is_active else "🔴"
            type_emoji = {
                "rss": "📰", "telegram": "✈️", "twitter": "🐦",
                "reddit": "🟠", "website": "🌐", "github": "🐙",
                "hackernews": "🔶", "arxiv": "📄",
            }.get(src.type, "📁")
            lines.append(
                f"{status} *ID {src.id}* | {type_emoji} {src.type}\n"
                f"   📝 {src.name}\n"
                f"   {'✅ فعال' if src.is_active else '❌ غیرفعال'}"
            )

        buttons: list[list[InlineKeyboardButton]] = []

        # Toggle buttons for each source
        for src in sources:
            toggle_text = "🔴 غیرفعال" if src.is_active else "🟢 فعال"
            buttons.append([
                InlineKeyboardButton(
                    text=f"{src.name[:25]}",
                    callback_data=f"src:detail:{src.id}",
                ),
                InlineKeyboardButton(
                    text=toggle_text,
                    callback_data=f"src:toggle:{src.id}",
                ),
                InlineKeyboardButton(
                    text="🔄",
                    callback_data=f"src:crawl:{src.id}",
                ),
            ])

        # Pagination
        nav_row: list[InlineKeyboardButton] = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"src:list:{page - 1}"))
        if offset + per_page < total:
            nav_row.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"src:list:{page + 1}"))
        if nav_row:
            buttons.append(nav_row)

        buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:sources")])
        text = "\n".join(lines)

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


# ──────────────────── Source Detail ────────────────────


@router.callback_query(F.data.startswith("src:detail:"))
async def cb_source_detail(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    src_id = int((callback.data or "").split(":")[2])

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()

    if not src:
        await callback.answer("❌ منبع یافت نشد", show_alert=True)
        return

    config = json.loads(src.config_json) if src.config_json else {}
    config_str = "\n".join(f"  🔹 {k}: {v}" for k, v in config.items())
    last_fetch = src.last_fetch_at.strftime("%Y-%m-%d %H:%M") if src.last_fetch_at else "هرگز"

    text = (
        f"📡 *جزئیات منبع*\n\n"
        f"🆔 شناسه: `{src.id}`\n"
        f"📝 نام: {src.name}\n"
        f"📁 نوع: {src.type}\n"
        f"{'✅ فعال' if src.is_active else '❌ غیرفعال'}\n"
        f"🕐 آخرین کراول: {last_fetch}\n\n"
        f"⚙️ *تنظیمات:*\n{config_str}"
    )

    buttons = [
        [
            InlineKeyboardButton(
                text="🔴 غیرفعال" if src.is_active else "🟢 فعال",
                callback_data=f"src:toggle:{src.id}",
            ),
            InlineKeyboardButton(text="🔄 کراول", callback_data=f"src:crawl:{src.id}"),
        ],
        [InlineKeyboardButton(text="🗑️ حذف", callback_data=f"src:delete:{src.id}")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="src:list:0")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


# ──────────────────── Toggle Source ────────────────────


@router.callback_query(F.data.startswith("src:toggle:"))
async def cb_toggle_source(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    src_id = int((callback.data or "").split(":")[2])

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()
        if not src:
            await callback.answer("❌ منبع یافت نشد", show_alert=True)
            return

        src.is_active = not src.is_active
        await session.commit()

        await _log_admin(session, callback.from_user.id, "toggle_source",
                         f"Toggled source {src.name} ({src.id}) to {'active' if src.is_active else 'inactive'}")

    status = "فعال ✅" if src.is_active else "غیرفعال ❌"
    await callback.answer(f"منبع {src.name} اکنون {status}")

    # Refresh list
    await cb_list_sources(callback)


# ──────────────────── Delete Source ────────────────────


@router.callback_query(F.data == "src:del_prompt")
async def cb_delete_prompt(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    text = "🗑️ برای حذف یک منبع، شناسه (ID) آن را ارسال کنید:\n\nمثال: `/del_source 5`"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:sources")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    await callback.answer()


@router.message(F.text.startswith("/del_source"))
async def cmd_del_source(message: Message) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("❌ لطفاً شناسه منبع را وارد کنید. مثال: `/del_source 5`", parse_mode="Markdown")
        return

    try:
        src_id = int(parts[1])
    except ValueError:
        await message.answer("❌ شناسه باید عدد باشد.")
        return

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()
        if not src:
            await message.answer(f"❌ منبع با شناسه {src_id} یافت نشد.")
            return

        name = src.name
        await session.delete(src)
        await session.commit()

        await _log_admin(session, message.from_user.id, "delete_source", f"Deleted source: {name} ({src_id})")

    await message.answer(f"✅ منبع «{name}» با موفقیت حذف شد.")


@router.callback_query(F.data.startswith("src:delete:"))
async def cb_delete_source(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    src_id = int((callback.data or "").split(":")[2])

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()
        if not src:
            await callback.answer("❌ یافت نشد", show_alert=True)
            return

        name = src.name
        await session.delete(src)
        await session.commit()

        await _log_admin(session, callback.from_user.id, "delete_source", f"Deleted source: {name} ({src_id})")

    await callback.answer(f"✅ {name} حذف شد")
    await cb_list_sources(callback)


# ──────────────────── Add Source (FSM) ────────────────────


SOURCE_TYPES = {
    "rss": "📰 RSS/Atom",
    "telegram": "✈️ کانال تلگرام",
    "twitter": "🐦 توییتر (X)",
    "reddit": "🟠 ساب‌ردیت Reddit",
    "website": "🌐 وبسایت (اسکرپ)",
    "github": "🐙 گیت‌هاب ترندینگ",
    "hackernews": "🔶 Hacker News",
    "arxiv": "📄 arXiv",
}

SOURCE_CONFIG_HINTS = {
    "rss": '{"url": "https://example.com/feed.xml"}',
    "telegram": '{"channel": "channel_username"}',
    "twitter": '{"username": "TwitterHandle"}',
    "reddit": '{"subreddit": "SubredditName"}',
    "website": '{"url": "https://example.com", "selector": "article", "title_selector": "h2"}',
    "github": '{"language": "python", "since": "daily"}',
    "hackernews": '{"max_items": 30, "keywords": "AI,LLM"}',
    "arxiv": '{"query": "cat:cs.AI", "max_results": 20, "keywords": "LLM,GPT"}',
}


@router.callback_query(F.data == "src:add")
async def cb_add_source_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"src:type:{key}")]
        for key, label in SOURCE_TYPES.items()
    ]
    buttons.append([InlineKeyboardButton(text="🔙 انصراف", callback_data="menu:sources")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        "➕ *افزودن منبع جدید*\n\nنوع منبع را انتخاب کنید:",
        reply_markup=kb,
        parse_mode="Markdown",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("src:type:"))
async def cb_add_source_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    src_type = (callback.data or "").split(":")[2]
    await state.update_data(src_type=src_type)

    hint = SOURCE_CONFIG_HINTS.get(src_type, "{}")

    await callback.message.edit_text(
        f"📝 نام منبع را وارد کنید\n\n"
        f"مثال: «وبلاگ OpenAI» یا «کانال AI فارسی»",
    )
    await state.set_state(AddSourceStates.waiting_for_name)
    await callback.answer()


@router.message(AddSourceStates.waiting_for_name)
async def add_source_name(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    name = (message.text or "").strip()
    if not name:
        await message.answer("❌ لطفاً یک نام وارد کنید.")
        return

    await state.update_data(src_name=name)
    data = await state.get_data()
    src_type = data.get("src_type", "rss")
    hint = SOURCE_CONFIG_HINTS.get(src_type, "{}")

    await message.answer(
        f"⚙️ تنظیمات منبع را به صورت JSON وارد کنید:\n\n"
        f"💡 نمونه:\n<code>{hint}</code>",
        parse_mode="HTML",
    )
    await state.set_state(AddSourceStates.waiting_for_config)


@router.message(AddSourceStates.waiting_for_config)
async def add_source_config(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    config_str = (message.text or "").strip()

    # Validate JSON
    try:
        config = json.loads(config_str)
    except json.JSONDecodeError:
        await message.answer("❌ فرمت JSON نامعتبر است. لطفاً دوباره وارد کنید.")
        return

    data = await state.get_data()
    src_type = data.get("src_type", "rss")
    src_name = data.get("src_name", "Unnamed")

    async with async_session_factory() as session:
        new_source = Source(
            name=src_name,
            type=src_type,
            config_json=json.dumps(config, ensure_ascii=False),
            is_active=True,
        )
        session.add(new_source)
        await session.commit()

        await _log_admin(session, message.from_user.id, "add_source",
                         f"Added source: {src_name} ({src_type})")

    await state.clear()

    await message.answer(
        f"✅ منبع جدید با موفقیت اضافه شد!\n\n"
        f"📝 نام: {src_name}\n"
        f"📁 نوع: {src_type}\n"
        f"⚙️ تنظیمات: <code>{config_str}</code>",
        parse_mode="HTML",
    )


# ──────────────────── Manual Crawl ────────────────────


@router.callback_query(F.data.startswith("src:crawl:"))
async def cb_crawl_single(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    src_id = int((callback.data or "").split(":")[2])

    await callback.answer("⏳ در حال کراول...")

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()

    if not src:
        await callback.answer("❌ منبع یافت نشد", show_alert=True)
        return

    from app.collectors import COLLECTOR_MAP
    from app.processors.pipeline import process_single_item
    from datetime import datetime, timezone

    collector_cls = COLLECTOR_MAP.get(src.type)
    if not collector_cls:
        await callback.answer("❌ نوع منبع پشتیبانی نمی‌شود", show_alert=True)
        return

    config = json.loads(src.config_json) if src.config_json else {}
    collector = collector_cls(config)
    raw_items = await collector.safe_collect()

    new_count = 0
    for raw in raw_items:
        async with async_session_factory() as session:
            item = await process_single_item(
                session=session,
                source=src,
                title=raw.title,
                raw_text=raw.text,
                url=raw.url,
                html=raw.html,
                published_at=raw.published_at,
            )
            if item:
                new_count += 1
            await session.commit()

    # Update last fetch
    async with async_session_factory() as session:
        await session.execute(
            update(Source).where(Source.id == src.id).values(
                last_fetch_at=datetime.now(timezone.utc)
            )
        )
        await session.commit()

    await callback.message.answer(f"✅ کراول «{src.name}» انجام شد. {new_count} مطلب جدید.")


@router.callback_query(F.data == "src:crawl_all")
async def cb_crawl_all(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.answer("⏳ در حال کراول همه منابع...")

    from app.services.scheduler import _run_collectors
    asyncio.create_task(_run_collectors())

    await callback.message.answer("🚀 کراول تمام منابع شروع شد. نتایج به‌زودی ارسال می‌شوند.")


# ──────────────────── Helpers ────────────────────

import asyncio


async def _log_admin(session, admin_id: int, action_type: str, description: str) -> None:
    """Log an admin action."""
    log = AdminLog(admin_id=admin_id, action_type=action_type, description=description)
    session.add(log)
    await session.flush()