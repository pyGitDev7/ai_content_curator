from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

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
from app.handlers.admin_panel import is_authorized

router = Router(name="sources")


# ──────────── FSM States ────────────

class AddSourceStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_name = State()
    waiting_for_config = State()


# ──────────── Helpers ─────────────────

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

TYPE_EMOJI = {
    "rss": "📰", "telegram": "✈️", "twitter": "🐦",
    "reddit": "🟠", "website": "🌐", "github": "🐙",
    "hackernews": "🔶", "arxiv": "📄",
}


async def _log_admin(admin_id: int, action_type: str, description: str) -> None:
    async with async_session_factory() as session:
        log = AdminLog(admin_id=admin_id, action_type=action_type, description=description)
        session.add(log)
        await session.commit()


# ──────────── Sources Menu ────────────

@router.callback_query(F.data == "src_menu:show")
async def cb_sources_menu(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text="📋 لیست منابع", callback_data="srcpg:0")],
        [InlineKeyboardButton(text="➕ افزودن منبع جدید", callback_data="srcadd:start")],
        [InlineKeyboardButton(text="🔄 کراول دستی (همه)", callback_data="srccrawl:all")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="back:main")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(
        "📡 مدیریت منابع\n\nاز گزینه‌های زیر استفاده کنید:",
        reply_markup=kb,
    )
    await callback.answer()


# ──────────── List Sources (Paginated) ────────────

@router.callback_query(F.data.startswith("srcpg:"))
async def cb_list_sources(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    parts = callback.data.split(":")
    page = int(parts[1]) if len(parts) > 1 else 0

    per_page = 5
    offset = page * per_page

    async with async_session_factory() as session:
        all_res = await session.execute(select(Source).order_by(Source.id))
        all_sources = list(all_res.scalars().all())
        total = len(all_sources)

        page_sources = all_sources[offset : offset + per_page]

    if not page_sources:
        text = "📋 منبعی ثبت نشده است." if total == 0 else "📋 منبعی در این صفحه نیست."
        buttons = [[InlineKeyboardButton(text="🔙 بازگشت", callback_data="src_menu:show")]]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        await callback.message.edit_text(text, reply_markup=kb)
        await callback.answer()
        return

    lines = ["📋 لیست منابع:\n"]
    buttons: list[list[InlineKeyboardButton]] = []

    for src in page_sources:
        status = "🟢" if src.is_active else "🔴"
        emoji = TYPE_EMOJI.get(src.type, "📁")
        lines.append(f"{status} ID:{src.id} | {emoji} {src.type} | {src.name}")

        toggle_label = "🔴 غیرفعال" if src.is_active else "🟢 فعال"
        buttons.append([
            InlineKeyboardButton(
                text=toggle_label,
                callback_data=f"srctoggle:{src.id}:{page}",
            ),
            InlineKeyboardButton(
                text="🔄 کراول",
                callback_data=f"srccrawl:{src.id}",
            ),
            InlineKeyboardButton(
                text="🗑️ حذف",
                callback_data=f"srcdel:{src.id}:{page}",
            ),
        ])

    # Pagination buttons
    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton(text="◀️ قبلی", callback_data=f"srcpg:{page - 1}")
        )
    if offset + per_page < total:
        nav_row.append(
            InlineKeyboardButton(text="بعدی ▶️", callback_data=f"srcpg:{page + 1}")
        )
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="src_menu:show")])

    text = "\n".join(lines)
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.edit_text(text, reply_markup=kb)
    await callback.answer()


# ──────────── Toggle Source ────────────

@router.callback_query(F.data.startswith("srctoggle:"))
async def cb_toggle_source(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    parts = callback.data.split(":")
    src_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()
        if not src:
            await callback.answer("❌ منبع یافت نشد", show_alert=True)
            return

        src.is_active = not src.is_active
        new_status = "فعال" if src.is_active else "غیرفعال"
        src_name = src.name
        await session.commit()

    await _log_admin(callback.from_user.id, "toggle_source", f"{src_name} -> {new_status}")
    await callback.answer(f"✅ {src_name}: {new_status}")

    # Rebuild the list page
    fake_data = f"srcpg:{page}"
    callback.data = fake_data
    await cb_list_sources(callback)


# ──────────── Delete Source ────────────

@router.callback_query(F.data.startswith("srcdel:"))
async def cb_delete_source(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    parts = callback.data.split(":")
    src_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()
        if not src:
            await callback.answer("❌ یافت نشد", show_alert=True)
            return
        src_name = src.name
        await session.delete(src)
        await session.commit()

    await _log_admin(callback.from_user.id, "delete_source", f"Deleted: {src_name} ({src_id})")
    await callback.answer(f"🗑️ {src_name} حذف شد")

    # Rebuild the list page
    fake_data = f"srcpg:{page}"
    callback.data = fake_data
    await cb_list_sources(callback)


# ──────────── Add Source (FSM) ────────────

@router.callback_query(F.data == "srcadd:start")
async def cb_add_source_start(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(text=label, callback_data=f"srctype:{key}")]
        for key, label in SOURCE_TYPES.items()
    ]
    buttons.append([InlineKeyboardButton(text="🔙 انصراف", callback_data="src_menu:show")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.message.edit_text(
        "➕ افزودن منبع جدید\n\nنوع منبع را انتخاب کنید:",
        reply_markup=kb,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("srctype:"))
async def cb_add_source_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    src_type = callback.data.split(":")[1]
    await state.update_data(src_type=src_type)

    await callback.message.edit_text(
        "📝 نام منبع را وارد کنید\n\n"
        "مثال: وبلاگ OpenAI"
    )
    await state.set_state(AddSourceStates.waiting_for_name)
    await callback.answer()


@router.message(AddSourceStates.waiting_for_name)
async def add_source_name(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await is_authorized(message.from_user.id):
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
        f"نمونه:\n{hint}"
    )
    await state.set_state(AddSourceStates.waiting_for_config)


@router.message(AddSourceStates.waiting_for_config)
async def add_source_config(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await is_authorized(message.from_user.id):
        return

    config_str = (message.text or "").strip()

    try:
        json.loads(config_str)
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
            config_json=json.dumps(json.loads(config_str), ensure_ascii=False),
            is_active=True,
        )
        session.add(new_source)
        await session.commit()

    await _log_admin(message.from_user.id, "add_source", f"Added: {src_name} ({src_type})")
    await state.clear()

    await message.answer(
        f"✅ منبع جدید اضافه شد!\n\n"
        f"📝 نام: {src_name}\n"
        f"📁 نوع: {src_type}\n"
        f"⚙️ تنظیمات: {config_str}"
    )


# ──────────── Manual Crawl ────────────

@router.callback_query(F.data.startswith("srccrawl:"))
async def cb_crawl(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    target = callback.data.split(":")[1]

    if target == "all":
        await callback.answer("⏳ کراول همه منابع شروع شد")
        from app.services.scheduler import _run_collectors
        asyncio.create_task(_run_collectors())
        await callback.message.answer("🚀 کراول تمام منابع شروع شد. نتایج به‌زودی ذخیره می‌شوند.")
        return

    src_id = int(target)
    await callback.answer("⏳ در حال کراول...")

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()

    if not src:
        await callback.message.answer("❌ منبع یافت نشد.")
        return

    from app.collectors import COLLECTOR_MAP
    from app.processors.pipeline import process_single_item

    collector_cls = COLLECTOR_MAP.get(src.type)
    if not collector_cls:
        await callback.message.answer("❌ نوع منبع پشتیبانی نمی‌شود.")
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

    async with async_session_factory() as session:
        await session.execute(
            update(Source).where(Source.id == src_id).values(
                last_fetch_at=datetime.now(timezone.utc)
            )
        )
        await session.commit()

    await callback.message.answer(f"✅ کراول «{src.name}»: {new_count} مطلب جدید.")
