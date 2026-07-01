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

from app.database import async_session_factory
from app.models.models import Source, AdminLog
from app.handlers.admin_panel import _is_authorized, safe_edit

router = Router(name="sources")


class AddSourceStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_config = State()


async def _log_admin(admin_id: int, action_type: str, description: str) -> None:
    async with async_session_factory() as session:
        session.add(AdminLog(admin_id=admin_id, action_type=action_type, description=description))
        await session.commit()


def _parse_src_list(data: str):
    """Parse 'src:list:PAGE' and return page number."""
    parts = data.split(":")
    if len(parts) >= 3:
        try:
            return int(parts[2])
        except ValueError:
            pass
    return 0


def _parse_src_id_and_page(data: str):
    """Parse 'src:ACTION:ID:PAGE' and return (id, page)."""
    parts = data.split(":")
    src_id = 0
    page = 0
    if len(parts) >= 3:
        try:
            src_id = int(parts[2])
        except ValueError:
            pass
    if len(parts) >= 4:
        try:
            page = int(parts[3])
        except ValueError:
            pass
    return src_id, page


def _parse_src_id(data: str):
    """Parse 'src:ACTION:ID' and return id."""
    parts = data.split(":")
    if len(parts) >= 3:
        try:
            return int(parts[2])
        except ValueError:
            pass
    return 0


# ──────────────────── List Sources ────────────────────


@router.callback_query(F.data.startswith("src:list:"))
async def cb_list_sources(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    page = _parse_src_list(callback.data or "")
    per_page = 6
    offset = page * per_page

    async with async_session_factory() as session:
        result = await session.execute(
            select(Source).order_by(Source.id).offset(offset).limit(per_page)
        )
        sources = result.scalars().all()

        total_result = await session.execute(select(Source))
        total = len(total_result.scalars().all())

    await callback.answer()

    if not sources:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:sources")]
        ])
        await safe_edit(callback.message, "📋 هیچ منبعی ثبت نشده است.", kb)
        return

    type_emoji = {
        "rss": "📰", "telegram": "✈️", "twitter": "🐦",
        "reddit": "🟠", "website": "🌐", "github": "🐙",
        "hackernews": "🔶", "arxiv": "📄",
    }

    lines: list[str] = ["📋 *لیست منابع:*\n"]
    buttons: list[list[InlineKeyboardButton]] = []

    for src in sources:
        status = "🟢" if src.is_active else "🔴"
        emoji = type_emoji.get(src.type, "📁")

        lines.append(f"{status} *ID {src.id}* {emoji} {src.type} — {src.name}")

        toggle_label = "🔴 OFF" if src.is_active else "🟢 ON"
        buttons.append([
            InlineKeyboardButton(text=src.name[:20], callback_data=f"src:detail:{src.id}"),
            InlineKeyboardButton(text=toggle_label, callback_data=f"src:toggle:{src.id}:{page}"),
            InlineKeyboardButton(text="🔄", callback_data=f"src:crawl:{src.id}:{page}"),
        ])

    nav_row: list[InlineKeyboardButton] = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"src:list:{page - 1}"))
    if offset + per_page < total:
        nav_row.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"src:list:{page + 1}"))
    if nav_row:
        buttons.append(nav_row)

    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="menu:sources")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await safe_edit(callback.message, "\n".join(lines), kb)


# ──────────────────── Source Detail ────────────────────


@router.callback_query(F.data.startswith("src:detail:"))
async def cb_source_detail(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    src_id = _parse_src_id(callback.data or "")

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()

    await callback.answer()

    if not src:
        await safe_edit(callback.message, "❌ منبع یافت نشد.")
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
                callback_data=f"src:toggle:{src.id}:0",
            ),
            InlineKeyboardButton(text="🔄 کراول", callback_data=f"src:crawl:{src.id}:0"),
        ],
        [InlineKeyboardButton(text="🗑️ حذف", callback_data=f"src:delete:{src.id}")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="src:list:0")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await safe_edit(callback.message, text, kb)


# ──────────────────── Toggle Source ────────────────────


@router.callback_query(F.data.startswith("src:toggle:"))
async def cb_toggle_source(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    src_id, page = _parse_src_id_and_page(callback.data or "")

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()
        if not src:
            await callback.answer("❌ منبع یافت نشد", show_alert=True)
            return

        src.is_active = not src.is_active
        new_status = src.is_active
        src_name = src.name
        await session.commit()

    await _log_admin(callback.from_user.id, "toggle_source",
                     f"Toggled {src_name} to {'active' if new_status else 'inactive'}")

    status_text = "✅ فعال" if new_status else "🔴 غیرفعال"
    await callback.answer(f"{status_text}: {src_name}")

    callback.data = f"src:list:{page}"
    await cb_list_sources(callback)


# ──────────────────── Delete Source ────────────────────


@router.callback_query(F.data == "src:del_prompt")
async def cb_delete_prompt(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.answer()
    await safe_edit(
        callback.message,
        "🗑️ شناسه منبع رو بفرست:\n\n`/del_source 5`",
    )


@router.message(F.text.startswith("/del_source"))
async def cmd_del_source(message: Message) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    parts = (message.text or "").split()
    if len(parts) < 2:
        await message.answer("❌ مثال: `/del_source 5`", parse_mode="Markdown")
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
            await message.answer(f"❌ منبع {src_id} یافت نشد.")
            return
        name = src.name
        await session.delete(src)
        await session.commit()

    await _log_admin(message.from_user.id, "delete_source", f"Deleted: {name} ({src_id})")
    await message.answer(f"✅ منبع «{name}» حذف شد.")


@router.callback_query(F.data.startswith("src:delete:"))
async def cb_delete_source(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    src_id = _parse_src_id(callback.data or "")

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()
        if not src:
            await callback.answer("❌ یافت نشد", show_alert=True)
            return
        name = src.name
        await session.delete(src)
        await session.commit()

    await _log_admin(callback.from_user.id, "delete_source", f"Deleted: {name} ({src_id})")
    await callback.answer(f"✅ {name} حذف شد")

    callback.data = "src:list:0"
    await cb_list_sources(callback)


# ──────────────────── Add Source ────────────────────


SOURCE_TYPES = {
    "rss": "📰 RSS/Atom",
    "telegram": "✈️ کانال تلگرام",
    "twitter": "🐦 توییتر (X)",
    "reddit": "🟠 ساب‌ردیت Reddit",
    "website": "🌐 وبسایت",
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
        [InlineKeyboardButton(text=label, callback_data=f"srctype:{key}")]
        for key, label in SOURCE_TYPES.items()
    ]
    buttons.append([InlineKeyboardButton(text="🔙 انصراف", callback_data="menu:sources")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await callback.answer()
    await safe_edit(callback.message, "➕ *افزودن منبع جدید*\n\nنوع منبع:", kb)


@router.callback_query(F.data.startswith("srctype:"))
async def cb_add_source_type(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    src_type = callback.data.split(":")[1]
    await state.update_data(src_type=src_type)

    await callback.answer()
    await safe_edit(callback.message, "📝 نام منبع را وارد کنید:\n\nمثال: «وبلاگ OpenAI»")
    await state.set_state(AddSourceStates.waiting_for_name)


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
        f"⚙️ تنظیمات منبع را به صورت JSON وارد کنید:\n\n💡 نمونه:\n<code>{hint}</code>",
        parse_mode="HTML",
    )
    await state.set_state(AddSourceStates.waiting_for_config)


@router.message(AddSourceStates.waiting_for_config)
async def add_source_config(message: Message, state: FSMContext) -> None:
    if not message.from_user or not await _is_authorized(message.from_user.id):
        return

    config_str = (message.text or "").strip()
    try:
        config = json.loads(config_str)
    except json.JSONDecodeError:
        await message.answer("❌ فرمت JSON نامعتبر.")
        return

    data = await state.get_data()
    src_type = data.get("src_type", "rss")
    src_name = data.get("src_name", "Unnamed")

    async with async_session_factory() as session:
        session.add(Source(
            name=src_name,
            type=src_type,
            config_json=json.dumps(config, ensure_ascii=False),
            is_active=True,
        ))
        await session.commit()

    await _log_admin(message.from_user.id, "add_source", f"Added: {src_name} ({src_type})")
    await state.clear()
    await message.answer(f"✅ منبع «{src_name}» اضافه شد!")


# ──────────────────── Crawl ────────────────────


@router.callback_query(F.data.startswith("src:crawl:"))
async def cb_crawl_single(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    src_id, page = _parse_src_id_and_page(callback.data or "")

    await callback.answer("⏳ در حال کراول...")

    async with async_session_factory() as session:
        result = await session.execute(select(Source).where(Source.id == src_id))
        src = result.scalar_one_or_none()

    if not src:
        return

    from app.collectors import COLLECTOR_MAP
    from app.processors.pipeline import process_single_item

    collector_cls = COLLECTOR_MAP.get(src.type)
    if not collector_cls:
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
            update(Source).where(Source.id == src.id).values(
                last_fetch_at=datetime.now(timezone.utc)
            )
        )
        await session.commit()

    await callback.message.answer(f"✅ کراول «{src.name}»: {new_count} مطلب جدید.")


@router.callback_query(F.data == "src:crawl_all")
async def cb_crawl_all(callback: CallbackQuery) -> None:
    if not callback.from_user or not await _is_authorized(callback.from_user.id):
        await callback.answer("⛔", show_alert=True)
        return

    await callback.answer("⏳ در حال کراول...")

    from app.services.scheduler import _run_collectors
    asyncio.create_task(_run_collectors())
    await callback.message.answer("🚀 کراول همه منابع شروع شد.")
