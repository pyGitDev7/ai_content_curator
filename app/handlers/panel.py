from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from loguru import logger
from sqlalchemy import select, func as sqlfunc, update

from app.config import settings, BASE_DIR
from app.database import async_session_factory
from app.models.models import User, Source, ContentItem, DeliveredLog, Keyword, Hashtag, Setting
from app.utils.helpers import format_single_item_html, is_persian, h

router = Router(name="panel")


async def is_authorized(uid: int) -> bool:
    if uid == settings.super_admin_id:
        return True
    async with async_session_factory() as s:
        r = await s.execute(select(User).where(User.telegram_id == uid))
        return r.scalar_one_or_none() is not None


async def safe_edit(msg, text, kb=None, parse_mode="HTML"):
    try:
        await msg.edit_text(text, reply_markup=kb, parse_mode=parse_mode)
    except Exception as e:
        if "message is not modified" not in str(e).lower():
            logger.debug(f"edit: {e}")


async def safe_answer(cb, text="", alert=False):
    try:
        await cb.answer(text, show_alert=alert)
    except Exception:
        pass


async def _setting(key, default=""):
    async with async_session_factory() as s:
        r = await s.execute(select(Setting.value).where(Setting.key == key))
        v = r.scalar_one_or_none()
        return v if v is not None else default


def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 داشبورد وضعیت", callback_data="p:status")],
        [InlineKeyboardButton(text="📡 مدیریت منابع", callback_data="p:sources")],
        [InlineKeyboardButton(text="📥 دریافت اخبار", callback_data="p:news")],
        [InlineKeyboardButton(text="🏷️ هشتگ‌ها و کلمات", callback_data="p:kw")],
        [InlineKeyboardButton(text="📂 دسته‌بندی‌ها", callback_data="p:cats")],
        [InlineKeyboardButton(text="📬 دریافت‌کنندگان", callback_data="p:rcv")],
        [InlineKeyboardButton(text="⏰ زمان‌بندی", callback_data="p:sched")],
        [InlineKeyboardButton(text="👥 مدیران", callback_data="p:admins")],
        [InlineKeyboardButton(text="🔧 سیستم", callback_data="p:sys")],
    ])


# ══════════════ MAIN MENU ══════════════

@router.callback_query(F.data == "p:main")
async def cb_main(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await safe_answer(callback)
    await safe_edit(callback.message, "🤖 <b>پنل مدیریت</b>\n\nاز منوی زیر انتخاب کنید:", main_kb())


# ══════════════ STATUS ══════════════

@router.callback_query(F.data == "p:status")
async def cb_status(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    async with async_session_factory() as s:
        active = (await s.execute(select(sqlfunc.count(Source.id)).where(Source.is_active == True))).scalar() or 0
        total = (await s.execute(select(sqlfunc.count(Source.id)))).scalar() or 0
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_n = (await s.execute(select(sqlfunc.count(ContentItem.id)).where(ContentItem.created_at >= today))).scalar() or 0
        deliv_n = (await s.execute(select(sqlfunc.count(DeliveredLog.id)).where(DeliveredLog.delivered_at >= today))).scalar() or 0
        total_n = (await s.execute(select(sqlfunc.count(ContentItem.id)))).scalar() or 0

    c = settings
    txt = (
        f"📊 <b>داشبورد</b>\n\n"
        f"📡 منابع: <b>{active}</b> فعال / <b>{total}</b> کل\n"
        f"📥 مطالب امروز: <b>{today_n}</b>\n"
        f"📚 کل مطالب: <b>{total_n}</b>\n"
        f"📤 ارسال امروز: <b>{deliv_n}</b>\n\n"
        f"🔌 <b>API:</b>\n"
        f"  OpenAI: {'✅' if c.openai_api_key else '❌'}\n"
        f"  MiMo: {'✅' if c.mimo_api_key else '❌'}\n"
        f"  DeepSeek: {'✅' if c.deepseek_api_key else '❌'}\n"
        f"  Telethon: {'✅' if c.telethon_api_id else '❌'}\n"
        f"  Twitter: {'✅' if c.twitter_bearer_token else '❌'}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 بروزرسانی", callback_data="p:status")],
        [InlineKeyboardButton(text="🔙", callback_data="p:main")],
    ])
    await safe_answer(callback)
    await safe_edit(callback.message, txt, kb)


# ══════════════ SOURCES ══════════════

SRC_EMOJI = {
    "rss": "📰", "telegram": "✈️", "twitter": "🐦", "reddit": "🟠",
    "website": "🌐", "github": "🐙", "hackernews": "🔶", "arxiv": "📄",
}


@router.callback_query(F.data == "p:sources")
async def cb_sources(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    txt = (
        "📡 <b>مدیریت منابع</b>\n\n"
        "💡 منابع = جاهایی که ربات ازشون محتوا جمع می‌کنه.\n"
        "RSS، کانال تلگرام، توییتر، Reddit، GitHub و ..."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 لیست منابع", callback_data="p:sl:0")],
        [InlineKeyboardButton(text="➕ افزودن منبع جدید", callback_data="wiz:src")],
        [InlineKeyboardButton(text="🔄 کراول همه الان", callback_data="p:crawl_all")],
        [InlineKeyboardButton(text="🔙", callback_data="p:main")],
    ])
    await safe_answer(callback)
    await safe_edit(callback.message, txt, kb)


@router.callback_query(F.data.startswith("p:sl:"))
async def cb_src_list(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    page = int(callback.data.split(":")[2])
    pp = 5
    off = page * pp
    async with async_session_factory() as s:
        srcs = (await s.execute(select(Source).order_by(Source.id).offset(off).limit(pp))).scalars().all()
        tot = len((await s.execute(select(Source))).scalars().all())
    await safe_answer(callback)
    if not srcs:
        await safe_edit(callback.message, "📋 منبعی نیست.",
                        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="p:sources")]]))
        return
    lines = ["📋 <b>منابع:</b>\n"]
    btns = []
    for src in srcs:
        st = "🟢" if src.is_active else "🔴"
        em = SRC_EMOJI.get(src.type, "📁")
        lf = ""
        if src.last_fetch_at:
            lf = f" | {src.last_fetch_at.strftime('%m/%d %H:%M')}"
        lines.append(f"{st} <code>{src.id}</code> {em} <b>{src.name}</b>")
        lines.append(f"    {src.type}{lf}")
        lines.append("")
        btns.append([
            InlineKeyboardButton(text="🔴OFF" if src.is_active else "🟢ON", callback_data=f"p:tg:{src.id}:{page}"),
            InlineKeyboardButton(text="🔄", callback_data=f"p:cr:{src.id}"),
            InlineKeyboardButton(text="🗑️", callback_data=f"p:sd:{src.id}:{page}"),
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"p:sl:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page + 1}", callback_data="p:none"))
    if off + pp < tot:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"p:sl:{page + 1}"))
    btns.append(nav)
    btns.append([InlineKeyboardButton(text="➕ افزودن", callback_data="wiz:src"), InlineKeyboardButton(text="🔙", callback_data="p:sources")])
    await safe_edit(callback.message, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=btns))


@router.callback_query(F.data == "p:none")
async def cb_none(callback: CallbackQuery):
    await safe_answer(callback)


@router.callback_query(F.data.startswith("p:tg:"))
async def cb_toggle(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    parts = callback.data.split(":")
    sid, page = int(parts[2]), int(parts[3])
    async with async_session_factory() as s:
        r = await s.execute(select(Source).where(Source.id == sid))
        src = r.scalar_one_or_none()
        if not src:
            await safe_answer(callback, "❌", True)
            return
        src.is_active = not src.is_active
        new_st, name = src.is_active, src.name
        await s.commit()
    await safe_answer(callback, f"{'✅ فعال' if new_st else '🔴 غیرفعال'}: {name}")
    callback.data = f"p:sl:{page}"
    await cb_src_list(callback)


@router.callback_query(F.data.startswith("p:sd:"))
async def cb_src_delete(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    parts = callback.data.split(":")
    sid, page = int(parts[2]), int(parts[3])
    async with async_session_factory() as s:
        r = await s.execute(select(Source).where(Source.id == sid))
        src = r.scalar_one_or_none()
        if not src:
            await safe_answer(callback, "❌", True)
            return
        name = src.name
        await s.delete(src)
        await s.commit()
    await safe_answer(callback, f"🗑️ «{name}» حذف شد")
    callback.data = f"p:sl:{page}"
    await cb_src_list(callback)


@router.callback_query(F.data.startswith("p:cr:"))
async def cb_crawl_one(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    sid = int(callback.data.split(":")[2])
    await safe_answer(callback, "⏳ ...")
    async with async_session_factory() as s:
        r = await s.execute(select(Source).where(Source.id == sid))
        src = r.scalar_one_or_none()
    if not src:
        return
    from app.collectors import COLLECTOR_MAP
    from app.processors.pipeline import process_single_item
    cls = COLLECTOR_MAP.get(src.type)
    if not cls:
        await callback.message.answer("❌ نوع پشتیبانی نمیشه.")
        return
    config = json.loads(src.config_json) if src.config_json else {}
    collector = cls(config)
    raws = await collector.safe_collect()
    new = 0
    for raw in raws:
        async with async_session_factory() as s:
            item = await process_single_item(s, src, raw.title, raw.text, raw.url, raw.html, raw.published_at)
            if item:
                new += 1
            await s.commit()
    async with async_session_factory() as s:
        await s.execute(update(Source).where(Source.id == src.id).values(last_fetch_at=datetime.now(timezone.utc)))
        await s.commit()
    await callback.message.answer(f"✅ «{src.name}»: {new} جدید از {len(raws)}")


@router.callback_query(F.data == "p:crawl_all")
async def cb_crawl_all(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    await safe_answer(callback, "⏳ ...")
    from app.services.scheduler import _run_collectors
    asyncio.create_task(_run_collectors())
    await callback.message.answer("🚀 کراول شروع شد. بسته به تعداد منابع، ۲-۱۰ دقیقه طول می‌کشه.")


# ══════════════ NEWS ══════════════

@router.callback_query(F.data == "p:news")
async def cb_news(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    async with async_session_factory() as s:
        rv = (await s.execute(select(Setting.value).where(Setting.key == "receiver_ids"))).scalar_one_or_none()
        try:
            rids = json.loads(rv) if rv else []
        except:
            rids = []
        undel = (await s.execute(select(sqlfunc.count(ContentItem.id)).where(
            ContentItem.processed == True, ContentItem.delivered == False))).scalar() or 0

    txt = (
        f"📥 <b>دریافت اخبار</b>\n\n"
        f"📬 دریافت‌کنندگان: <b>{len(rids)}</b>\n"
        f"📋 مطالب آماده: <b>{undel}</b>"
    )
    if not rids:
        txt += "\n\n⚠️ دریافت‌کننده تنظیم نشده!"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 جمع‌آوری الان", callback_data="p:fetch_now")],
        [InlineKeyboardButton(text="📤 ارسال خلاصه الان", callback_data="p:send_now")],
        [InlineKeyboardButton(text="📋 مطالب اخیر", callback_data="p:recent:0")],
        [InlineKeyboardButton(text="🔙", callback_data="p:main")],
    ])
    await safe_answer(callback)
    await safe_edit(callback.message, txt, kb)


@router.callback_query(F.data == "p:fetch_now")
async def cb_fetch_now(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    await safe_answer(callback, "⏳ ...")
    from app.services.scheduler import _run_collectors
    asyncio.create_task(_run_collectors())
    await callback.message.answer("🔄 جمع‌آوری شروع شد.\n⏳ ۲-۱۰ دقیقه طول می‌کشه.\nبعد از اتمام از «📋 مطالب اخیر» ببین.")


@router.callback_query(F.data == "p:send_now")
async def cb_send_now(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    await safe_answer(callback, "⏳ ...")
    from app.services.delivery import deliver_digest
    await deliver_digest(callback.bot)
    await callback.message.answer("📤 ارسال انجام شد.")


@router.callback_query(F.data.startswith("p:recent:"))
async def cb_recent(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    page = int(callback.data.split(":")[2])
    pp = 5
    off = page * pp
    async with async_session_factory() as s:
        items = (await s.execute(
            select(ContentItem).where(ContentItem.processed == True)
            .order_by(ContentItem.created_at.desc()).offset(off).limit(pp)
        )).scalars().all()
    await safe_answer(callback)
    if not items:
        await safe_edit(callback.message, "📋 مطلبی نیست.\n💡 اول «🔄 جمع‌آوری» رو بزن.",
                        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙", callback_data="p:news")]]))
        return

    await callback.message.answer(f"📋 <b>{len(items)} مطلب اخیر:</b>", parse_mode="HTML")

    for item in items:
        msg_text = format_single_item_html(item)
        raw_text = item.raw_text or item.title or ""
        fa = is_persian(raw_text)

        btns = []
        if fa:
            btns.append([InlineKeyboardButton(text="🇬🇧 ترجمه به انگلیسی", callback_data=f"p:tr_en:{item.id}")])
        else:
            btns.append([InlineKeyboardButton(text="🇮🇷 ترجمه به فارسی", callback_data=f"p:tr_fa:{item.id}")])
        btns.append([InlineKeyboardButton(text="📄 متن کامل", callback_data=f"p:full:{item.id}")])

        try:
            await callback.message.answer(
                msg_text, parse_mode="HTML", disable_web_page_preview=False,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=btns),
            )
        except Exception as e:
            logger.error(f"Send recent: {e}")

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"p:recent:{page - 1}"))
    if len(items) == pp:
        nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"p:recent:{page + 1}"))
    btns_back = []
    if nav:
        btns_back.append(nav)
    btns_back.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="p:news")])
    await callback.message.answer("──────────────", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns_back))


# ══════════════ TRANSLATION ══════════════

@router.callback_query(F.data.startswith("p:tr_fa:"))
async def cb_translate_fa(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    item_id = int(callback.data.split(":")[2])
    await safe_answer(callback, "⏳ در حال ترجمه...")

    from app.services.ai_service import ai_service
    async with async_session_factory() as s:
        result = await s.execute(select(ContentItem).where(ContentItem.id == item_id))
        item = result.scalar_one_or_none()

    if not item:
        await callback.message.answer("❌ مطلب یافت نشد.")
        return

    text = item.raw_text or item.title or ""
    if not text:
        await callback.message.answer("❌ متنی برای ترجمه نیست.")
        return

    translated = await ai_service.translate_to_farsi(text[:3000])

    async with async_session_factory() as s:
        result = await s.execute(select(ContentItem).where(ContentItem.id == item_id))
        db_item = result.scalar_one_or_none()
        if db_item:
            db_item.translated_fa = translated
            await s.commit()

    msg = f"🇮🇷 <b>ترجمه فارسی:</b>\n\n📰 <b>{h(item.title)}</b>\n\n{h(translated[:2000])}"
    if item.url:
        msg += f'\n\n🔗 <a href="{item.url}">مطلب اصلی</a>'
    await callback.message.answer(msg, parse_mode="HTML", disable_web_page_preview=True)


@router.callback_query(F.data.startswith("p:tr_en:"))
async def cb_translate_en(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    item_id = int(callback.data.split(":")[2])
    await safe_answer(callback, "⏳ Translating...")

    from app.services.ai_service import ai_service
    async with async_session_factory() as s:
        result = await s.execute(select(ContentItem).where(ContentItem.id == item_id))
        item = result.scalar_one_or_none()

    if not item:
        await callback.message.answer("❌ Item not found.")
        return

    text = item.raw_text or item.title or ""
    if not text:
        await callback.message.answer("❌ No text.")
        return

    translated = await ai_service.translate_to_english(text[:3000])
    msg = f"🇬🇧 <b>English Translation:</b>\n\n📰 <b>{h(item.title)}</b>\n\n{h(translated[:2000])}"
    if item.url:
        msg += f'\n\n🔗 <a href="{item.url}">Original</a>'
    await callback.message.answer(msg, parse_mode="HTML", disable_web_page_preview=True)


@router.callback_query(F.data.startswith("p:full:"))
async def cb_full_text(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    item_id = int(callback.data.split(":")[2])
    await safe_answer(callback)

    async with async_session_factory() as s:
        result = await s.execute(select(ContentItem).where(ContentItem.id == item_id))
        item = result.scalar_one_or_none()

    if not item:
        await callback.message.answer("❌ یافت نشد.")
        return

    full = item.raw_text or "متنی نیست."
    if len(full) > 3500:
        full = full[:3500] + "\n\n[...]"

    btns = []
    if is_persian(full):
        btns.append([InlineKeyboardButton(text="🇬🇧 ترجمه به انگلیسی", callback_data=f"p:tr_en:{item.id}")])
    else:
        btns.append([InlineKeyboardButton(text="🇮🇷 ترجمه به فارسی", callback_data=f"p:tr_fa:{item.id}")])

    await callback.message.answer(
        f"📄 <b>متن کامل:</b>\n\n{h(full)}",
        parse_mode="HTML", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=btns) if btns else None,
    )


# ══════════════ KEYWORDS ══════════════

@router.callback_query(F.data == "p:kw")
async def cb_kw(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    async with async_session_factory() as s:
        kws = (await s.execute(select(Keyword).order_by(Keyword.is_negative, Keyword.id))).scalars().all()
        hts = (await s.execute(select(Hashtag).order_by(Hashtag.id))).scalars().all()
    pos = [k for k in kws if not k.is_negative]
    neg = [k for k in kws if k.is_negative]

    lines = ["🏷️ <b>کلمات و هشتگ‌ها</b>\n"]
    btns = []
    if pos:
        lines.append("\n✅ مثبت:")
        for k in pos:
            lines.append(f"  • <code>{k.word}</code>")
        for k in pos:
            btns.append([InlineKeyboardButton(text=f"🗑️ {k.word}", callback_data=f"p:kwrm:{k.id}")])
    if neg:
        lines.append("\n🚫 منفی:")
        for k in neg:
            lines.append(f"  • <code>{k.word}</code>")
        for k in neg:
            btns.append([InlineKeyboardButton(text=f"🗑️ {k.word}", callback_data=f"p:kwrm:{k.id}")])
    if hts:
        lines.append("\n#️⃣ هشتگ‌ها:")
        for ht in hts:
            lines.append(f"  • #{ht.tag}")
        for ht in hts:
            btns.append([InlineKeyboardButton(text=f"🗑️ #{ht.tag}", callback_data=f"p:htrm:{ht.id}")])
    if not pos and not neg and not hts:
        lines.append("\n⚠️ هنوز چیزی ثبت نشده.")

    btns.append([
        InlineKeyboardButton(text="➕ کلمه مثبت", callback_data="wiz:kw_pos"),
        InlineKeyboardButton(text="➖ کلمه منفی", callback_data="wiz:kw_neg"),
    ])
    btns.append([InlineKeyboardButton(text="➕ هشتگ", callback_data="wiz:ht_add")])
    btns.append([InlineKeyboardButton(text="🔙", callback_data="p:main")])
    await safe_answer(callback)
    await safe_edit(callback.message, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=btns))


@router.callback_query(F.data.startswith("p:kwrm:"))
async def cb_kwrm(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    kid = int(callback.data.split(":")[2])
    async with async_session_factory() as s:
        r = await s.execute(select(Keyword).where(Keyword.id == kid))
        kw = r.scalar_one_or_none()
        if kw:
            w = kw.word
            await s.delete(kw)
            await s.commit()
            await safe_answer(callback, f"🗑️ «{w}» حذف شد")
        else:
            await safe_answer(callback, "❌", True)
    callback.data = "p:kw"
    await cb_kw(callback)


@router.callback_query(F.data.startswith("p:htrm:"))
async def cb_htrm(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    hid = int(callback.data.split(":")[2])
    async with async_session_factory() as s:
        r = await s.execute(select(Hashtag).where(Hashtag.id == hid))
        ht = r.scalar_one_or_none()
        if ht:
            t = ht.tag
            await s.delete(ht)
            await s.commit()
            await safe_answer(callback, f"🗑️ #{t} حذف شد")
        else:
            await safe_answer(callback, "❌", True)
    callback.data = "p:kw"
    await cb_kw(callback)


# ══════════════ CATEGORIES ══════════════

CATS = {
    "tutorial": "📚 آموزشی", "news": "📰 خبر", "tool": "🔧 ابزار",
    "prompt": "💬 پرامپت", "paper": "📄 مقاله", "other": "📌 متفرقه",
}


@router.callback_query(F.data == "p:cats")
async def cb_cats(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    raw = await _setting("enabled_categories")
    enabled = [c.strip() for c in raw.split(",") if c.strip()] if raw else list(CATS.keys())
    btns = []
    for k, lb in CATS.items():
        st = "✅" if k in enabled else "❌"
        btns.append([InlineKeyboardButton(text=f"{st} {lb}", callback_data=f"p:ct:{k}")])
    btns.append([InlineKeyboardButton(text="🔙", callback_data="p:main")])
    await safe_answer(callback)
    await safe_edit(callback.message, "📂 <b>دسته‌بندی‌ها</b>\nبرای روشن/خاموش کلیک کن:", InlineKeyboardMarkup(inline_keyboard=btns))


@router.callback_query(F.data.startswith("p:ct:"))
async def cb_cat_toggle(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    key = callback.data.split(":")[2]
    raw = await _setting("enabled_categories")
    enabled = [c.strip() for c in raw.split(",") if c.strip()] if raw else list(CATS.keys())
    if key in enabled:
        enabled.remove(key)
    else:
        enabled.append(key)
    async with async_session_factory() as s:
        r = await s.execute(select(Setting).where(Setting.key == "enabled_categories"))
        st = r.scalar_one_or_none()
        val = ",".join(enabled)
        if st:
            st.value = val
        else:
            s.add(Setting(key="enabled_categories", value=val))
        await s.commit()
    callback.data = "p:cats"
    await cb_cats(callback)


# ══════════════ RECEIVERS ══════════════

@router.callback_query(F.data == "p:rcv")
async def cb_rcv(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    async with async_session_factory() as s:
        rv = (await s.execute(select(Setting.value).where(Setting.key == "receiver_ids"))).scalar_one_or_none()
        try:
            rids = json.loads(rv) if rv else []
        except:
            rids = []
    lines = [
        "📬 <b>دریافت‌کنندگان</b>\n",
        "💡 Chat ID‌هایی که خلاصه براشون ارسال میشه.",
        "برای پیدا کردن Chat ID: پیام رو به @userinfobot فوروارد کن.\n",
    ]
    if rids:
        lines.append("📋 فعلی:")
        for r in rids:
            lines.append(f"  • <code>{r}</code>")
    else:
        lines.append("⚠️ هیچ دریافت‌کننده‌ای تنظیم نشده!")
    btns = []
    if rids:
        btns.append([InlineKeyboardButton(text="📨 تست ارسال", callback_data="p:test_rc")])
        btns.append([InlineKeyboardButton(text="🗑️ حذف همه", callback_data="p:rc_rm_all")])
    btns.append([InlineKeyboardButton(text="➕ افزودن", callback_data="wiz:rc_add")])
    btns.append([InlineKeyboardButton(text="🔙", callback_data="p:main")])
    await safe_answer(callback)
    await safe_edit(callback.message, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=btns))


@router.callback_query(F.data == "p:test_rc")
async def cb_test_rc(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    await safe_answer(callback, "📨 ...")
    async with async_session_factory() as s:
        rv = (await s.execute(select(Setting.value).where(Setting.key == "receiver_ids"))).scalar_one_or_none()
        try:
            rids = json.loads(rv) if rv else []
        except:
            rids = []
    if not rids:
        await callback.message.answer("❌ دریافت‌کننده نیست.")
        return
    ok = 0
    for cid in rids:
        try:
            await callback.bot.send_message(chat_id=cid, text="✅ تست: ربات کیوریتور AI فعاله!")
            ok += 1
        except Exception as e:
            await callback.message.answer(f"❌ خطا {cid}: {e}")
    await callback.message.answer(f"📨 {ok}/{len(rids)} موفق")


@router.callback_query(F.data == "p:rc_rm_all")
async def cb_rc_rm_all(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    async with async_session_factory() as s:
        r = await s.execute(select(Setting).where(Setting.key == "receiver_ids"))
        st = r.scalar_one_or_none()
        if st:
            st.value = "[]"
        await s.commit()
    await safe_answer(callback, "✅ حذف شد")
    callback.data = "p:rcv"
    await cb_rcv(callback)


# ══════════════ SCHEDULE ══════════════

@router.callback_query(F.data == "p:sched")
async def cb_sched(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    h = await _setting("digest_hour", str(settings.digest_hour))
    m = await _setting("digest_minute", str(settings.digest_minute))
    mx = await _setting("digest_max_items", str(settings.digest_max_items))
    ms = await _setting("min_score", "0")
    txt = (
        f"⏰ <b>زمان‌بندی</b>\n\n"
        f"💡 هر ۲ ساعت جمع‌آوری، ساعت {h}:{int(m):02d} ارسال خلاصه.\n\n"
        f"🕐 ساعت: <b>{h}:{int(m):02d}</b>\n"
        f"📊 حداکثر: <b>{mx}</b>\n"
        f"⭐ حداقل امتیاز: <b>{ms}</b>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕐 تغییر ساعت", callback_data="wiz:time")],
        [InlineKeyboardButton(text="📊 تغییر تعداد", callback_data="wiz:count")],
        [InlineKeyboardButton(text="⭐ تغییر امتیاز", callback_data="wiz:score")],
        [InlineKeyboardButton(text="🔙", callback_data="p:main")],
    ])
    await safe_answer(callback)
    await safe_edit(callback.message, txt, kb)


# ══════════════ ADMINS ══════════════

@router.callback_query(F.data == "p:admins")
async def cb_admins(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    async with async_session_factory() as s:
        admins = (await s.execute(select(User).order_by(User.id))).scalars().all()
    lines = ["👥 <b>مدیران</b>\n"]
    btns = []
    if admins:
        for a in admins:
            b = " 👑" if a.is_super_admin else ""
            u = f"@{a.username}" if a.username else "—"
            lines.append(f"  • {u}{b} | <code>{a.telegram_id}</code>")
            if not a.is_super_admin and callback.from_user.id == settings.super_admin_id:
                btns.append([InlineKeyboardButton(text=f"🗑️ {u} ({a.telegram_id})", callback_data=f"p:admrm:{a.id}")])
    if callback.from_user.id == settings.super_admin_id:
        btns.append([InlineKeyboardButton(text="➕ افزودن", callback_data="wiz:adm_add")])
    btns.append([InlineKeyboardButton(text="🔙", callback_data="p:main")])
    await safe_answer(callback)
    await safe_edit(callback.message, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=btns))


@router.callback_query(F.data.startswith("p:admrm:"))
async def cb_adm_rm(callback: CallbackQuery) -> None:
    if not callback.from_user or callback.from_user.id != settings.super_admin_id:
        return
    aid = int(callback.data.split(":")[2])
    async with async_session_factory() as s:
        r = await s.execute(select(User).where(User.id == aid))
        a = r.scalar_one_or_none()
        if a and not a.is_super_admin:
            await s.delete(a)
            await s.commit()
            await safe_answer(callback, "✅ حذف شد")
        else:
            await safe_answer(callback, "❌", True)
    callback.data = "p:admins"
    await cb_admins(callback)


# ══════════════ SYSTEM ══════════════

@router.callback_query(F.data == "p:sys")
async def cb_sys(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💾 بکاپ", callback_data="p:bak")],
        [InlineKeyboardButton(text="📋 لاگ‌ها", callback_data="p:logs")],
        [InlineKeyboardButton(text="🔄 ری‌استارت شیدولر", callback_data="p:rsch")],
        [InlineKeyboardButton(text="🔙", callback_data="p:main")],
    ])
    await safe_answer(callback)
    await safe_edit(callback.message, "🔧 <b>سیستم</b>", kb)


@router.callback_query(F.data == "p:bak")
async def cb_bak(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    await safe_answer(callback)
    db = BASE_DIR / "data" / "curator.db"
    if not db.exists():
        await callback.message.answer("❌ دیتابیس نیست.")
        return
    try:
        data = db.read_bytes()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        await callback.message.answer_document(BufferedInputFile(data, f"backup_{ts}.db"), caption="💾 بکاپ")
    except Exception as e:
        await callback.message.answer(f"❌ {e}")


@router.callback_query(F.data == "p:logs")
async def cb_logs(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    await safe_answer(callback)
    lp = BASE_DIR / "data" / "logs" / "curator.log"
    if not lp.exists():
        await callback.message.answer("📋 لاگی نیست.")
        return
    try:
        c = lp.read_text("utf-8")
        if len(c) > 3000:
            c = "...\n" + c[-3000:]
        await callback.message.answer(f"<pre>{c[:4000]}</pre>", parse_mode="HTML")
    except Exception as e:
        await callback.message.answer(f"❌ {e}")


@router.callback_query(F.data == "p:rsch")
async def cb_rsch(callback: CallbackQuery) -> None:
    if not callback.from_user or not await is_authorized(callback.from_user.id):
        return
    try:
        from app.services.scheduler import scheduler, setup_scheduler, shutdown_scheduler
        shutdown_scheduler()
        await asyncio.sleep(1)
        setup_scheduler()
        await safe_answer(callback)
        await callback.message.answer("✅ شیدولر ری‌استارت شد.")
    except Exception as e:
        await callback.message.answer(f"❌ {e}")
