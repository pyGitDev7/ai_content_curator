from __future__ import annotations

import json
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from loguru import logger
from sqlalchemy import select

from app.database import async_session_factory
from app.models.models import Source, Keyword, Hashtag, User, Setting, AdminLog
from app.config import settings

router = Router(name="wizard")


class W(StatesGroup):
    src_type = State()
    src_1 = State()
    src_2 = State()
    src_name = State()
    src_del = State()
    kw_input = State()
    kw_del = State()
    ht_input = State()
    ht_del = State()
    rc_input = State()
    adm_input = State()
    adm_del = State()
    sch_time = State()
    sch_count = State()
    sch_score = State()


async def is_auth(uid):
    if uid == settings.super_admin_id:
        return True
    async with async_session_factory() as s:
        r = await s.execute(select(User).where(User.telegram_id == uid))
        return r.scalar_one_or_none() is not None


async def show_panel(target):
    from app.handlers.panel import main_kb
    kb = main_kb()
    txt = "🤖 <b>پنل مدیریت</b>\n\nاز منوی زیر انتخاب کنید:"
    if isinstance(target, Message):
        await target.answer(txt, reply_markup=kb, parse_mode="HTML")
    elif isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(txt, reply_markup=kb, parse_mode="HTML")
        except:
            await target.message.answer(txt, reply_markup=kb, parse_mode="HTML")


async def _log(uid, act, desc):
    async with async_session_factory() as s:
        s.add(AdminLog(admin_id=uid, action_type=act, description=desc))
        await s.commit()


def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو و بازگشت", callback_data="w:cancel")]
    ])


def done_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به پنل", callback_data="w:panel")]
    ])


# ── UNIVERSAL CANCEL & BACK ──

@router.callback_query(F.data == "w:cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.answer("لغو شد")
    except:
        pass
    await show_panel(cb)


@router.callback_query(F.data == "w:panel")
async def cb_back(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.answer()
    except:
        pass
    await show_panel(cb)


@router.message(F.text == "/cancel")
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ لغو شد.")
    await show_panel(msg)


# ══════════════════════════════════════════
# SOURCE ADDITION WIZARD
# ══════════════════════════════════════════

SRC_TYPES = {
    "rss": "📰 RSS/Atom",
    "telegram": "✈️ کانال تلگرام",
    "twitter": "🐦 توییتر",
    "reddit": "🟠 Reddit",
    "website": "🌐 وبسایت",
    "github": "🐙 GitHub",
    "hackernews": "🔶 Hacker News",
    "arxiv": "📄 arXiv",
}

SRC_PROMPTS = {
    "rss": ("لینک فید RSS رو بفرست:\nمثال: https://openai.com/blog/rss", None),
    "telegram": ("یوزرنیم کانال رو بفرست (بدون @):\nمثال: AIinsights", None),
    "twitter": ("یوزرنیم توییتر رو بفرست (بدون @):\nمثال: OpenAI", None),
    "reddit": ("اسم ساب‌ردیت رو بفرست:\nمثال: MachineLearning", None),
    "website": ("لینک سایت رو بفرست:\nمثال: https://example.com", "سلکتور CSS رو بفرست:\nمثال: article"),
    "github": ("زبان رو بفرست (یا all):\nمثال: python", "بازه زمانی (daily/weekly/monthly):"),
    "hackernews": ("کلمات کلیدی (با کاما):\nمثال: AI, LLM, GPT", "حداکثر تعداد (مثلاً 30):"),
    "arxiv": ("کوئری جستجو:\nمثال: cat:cs.AI OR cat:cs.CL", "کلمات کلیدی (با کاما):\nمثال: LLM, prompt"),
}

SRC_DEFAULTS = {
    "website": ("article",),
    "github": ("daily",),
    "hackernews": ("30",),
    "arxiv": ("LLM,prompt,transformer", "20"),
}


@router.callback_query(F.data == "wiz:src")
async def wiz_src_start(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    btns = [[InlineKeyboardButton(text=v, callback_data=f"ws:{k}")] for k, v in SRC_TYPES.items()]
    btns.append([InlineKeyboardButton(text="❌ لغو", callback_data="w:cancel")])
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("📡 <b>نوع منبع جدید:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns), parse_mode="HTML")
    except:
        await cb.message.answer("📡 <b>نوع منبع جدید:</b>", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns), parse_mode="HTML")
    await state.set_state(W.src_type)


@router.callback_query(W.src_type, F.data.startswith("ws:"))
async def wiz_src_type(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    stype = cb.data.split(":")[1]
    await state.update_data(stype=stype, step=1, s1="", s2="")
    prompt, _ = SRC_PROMPTS.get(stype, ("اطلاعات رو بفرست:", None))
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text(f"📝 {prompt}", reply_markup=cancel_kb())
    except:
        await cb.message.answer(f"📝 {prompt}", reply_markup=cancel_kb())
    await state.set_state(W.src_1)


@router.message(W.src_1, F.text & ~F.text.startswith("/"))
async def wiz_src_1(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    val = (msg.text or "").strip()
    if not val:
        await msg.answer("❌ خالیه!", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    stype = data.get("stype", "rss")
    await state.update_data(s1=val)

    _, prompt2 = SRC_PROMPTS.get(stype, (None, None))
    if prompt2:
        defaults = SRC_DEFAULTS.get(stype, ())
        hint = f"\n(پیش‌فرض: {defaults[0]})" if defaults else ""
        await msg.answer(f"📝 {prompt2}{hint}", reply_markup=cancel_kb())
        await state.set_state(W.src_2)
    else:
        await msg.answer("📝 اسم این منبع رو بفرست:", reply_markup=cancel_kb())
        await state.set_state(W.src_name)


@router.message(W.src_2, F.text & ~F.text.startswith("/"))
async def wiz_src_2(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    val = (msg.text or "").strip()
    if not val:
        data = await state.get_data()
        stype = data.get("stype", "rss")
        defaults = SRC_DEFAULTS.get(stype, ())
        val = defaults[0] if defaults else ""
    await state.update_data(s2=val)
    await msg.answer("📝 اسم این منبع رو بفرست:", reply_markup=cancel_kb())
    await state.set_state(W.src_name)


@router.message(W.src_name, F.text & ~F.text.startswith("/"))
async def wiz_src_name(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    name = (msg.text or "").strip()
    if not name:
        await msg.answer("❌ اسم بفرست.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    stype = data.get("stype", "rss")
    s1 = data.get("s1", "")
    s2 = data.get("s2", "")

    config = {}
    if stype == "rss":
        config = {"url": s1}
    elif stype == "telegram":
        config = {"channel": s1}
    elif stype == "twitter":
        config = {"username": s1}
    elif stype == "reddit":
        config = {"subreddit": s1}
    elif stype == "website":
        config = {"url": s1, "selector": s2 or "article"}
    elif stype == "github":
        config = {"language": s1, "since": s2 or "daily"}
    elif stype == "hackernews":
        mx = int(s2) if s2 and s2.isdigit() else 30
        config = {"keywords": s1, "max_items": mx}
    elif stype == "arxiv":
        config = {"query": s1, "keywords": s2 or "LLM,prompt", "max_results": 20}

    async with async_session_factory() as s:
        s.add(Source(name=name, type=stype, config_json=json.dumps(config, ensure_ascii=False), is_active=True))
        await s.commit()

    await _log(msg.from_user.id, "add_source", f"{name} ({stype})")
    await state.clear()
    em = SRC_TYPES.get(stype, "📁")
    await msg.answer(
        f"✅ منبع اضافه شد!\n\n📝 {name}\n📡 {em}\n⚙️ <code>{json.dumps(config, ensure_ascii=False)}</code>",
        reply_markup=done_kb(), parse_mode="HTML",
    )


# ── SOURCE DELETE ──

@router.callback_query(F.data == "wiz:src_del")
async def wiz_src_del(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("🗑️ شناسه (ID) منبع:", reply_markup=cancel_kb())
    except:
        await cb.message.answer("🗑️ شناسه (ID) منبع:", reply_markup=cancel_kb())
    await state.set_state(W.src_del)


@router.message(W.src_del, F.text & ~F.text.startswith("/"))
async def wiz_src_del_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    try:
        sid = int((msg.text or "").strip())
    except:
        await msg.answer("❌ عدد بفرست.", reply_markup=cancel_kb())
        return
    async with async_session_factory() as s:
        r = await s.execute(select(Source).where(Source.id == sid))
        src = r.scalar_one_or_none()
        if not src:
            await msg.answer(f"❌ منبع {sid} نیست.", reply_markup=done_kb())
            await state.clear()
            return
        n = src.name
        await s.delete(src)
        await s.commit()
    await _log(msg.from_user.id, "delete_source", f"{n} ({sid})")
    await state.clear()
    await msg.answer(f"✅ «{n}» حذف شد.", reply_markup=done_kb())


# ══════════════════════════════════════════
# KEYWORDS
# ══════════════════════════════════════════

@router.callback_query(F.data == "wiz:kw_pos")
async def wiz_kw_pos(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    await state.update_data(neg=False)
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("➕ کلمات مثبت (با کاما):\nمثال: AI, LLM, ChatGPT", reply_markup=cancel_kb())
    except:
        await cb.message.answer("➕ کلمات مثبت (با کاما):\nمثال: AI, LLM, ChatGPT", reply_markup=cancel_kb())
    await state.set_state(W.kw_input)


@router.callback_query(F.data == "wiz:kw_neg")
async def wiz_kw_neg(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    await state.update_data(neg=True)
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("➖ کلمات منفی/مسدود (با کاما):\nمثال: bitcoin, crypto", reply_markup=cancel_kb())
    except:
        await cb.message.answer("➖ کلمات منفی/مسدود (با کاما):\nمثال: bitcoin, crypto", reply_markup=cancel_kb())
    await state.set_state(W.kw_input)


@router.message(W.kw_input, F.text & ~F.text.startswith("/"))
async def wiz_kw_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    data = await state.get_data()
    neg = data.get("neg", False)
    words = [w.strip() for w in (msg.text or "").split(",") if w.strip()]
    if not words:
        await msg.answer("❌ حداقل یه کلمه.", reply_markup=cancel_kb())
        return
    async with async_session_factory() as s:
        for w in words:
            s.add(Keyword(word=w, is_negative=neg))
        await s.commit()
    await _log(msg.from_user.id, "add_keyword", f"{'neg' if neg else 'pos'}: {', '.join(words)}")
    await state.clear()
    kind = "منفی 🚫" if neg else "مثبت ✅"
    await msg.answer(f"✅ کلمات {kind}:\n" + "\n".join(f"• {w}" for w in words), reply_markup=done_kb())


@router.callback_query(F.data == "wiz:kw_del")
async def wiz_kw_del(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("🗑️ ID کلمه:", reply_markup=cancel_kb())
    except:
        await cb.message.answer("🗑️ ID کلمه:", reply_markup=cancel_kb())
    await state.set_state(W.kw_del)


@router.message(W.kw_del, F.text & ~F.text.startswith("/"))
async def wiz_kw_del_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    try:
        kid = int((msg.text or "").strip())
    except:
        await msg.answer("❌ عدد.", reply_markup=cancel_kb())
        return
    async with async_session_factory() as s:
        r = await s.execute(select(Keyword).where(Keyword.id == kid))
        kw = r.scalar_one_or_none()
        if not kw:
            await msg.answer(f"❌ ID {kid} نیست.", reply_markup=done_kb())
            await state.clear()
            return
        w = kw.word
        await s.delete(kw)
        await s.commit()
    await state.clear()
    await msg.answer(f"✅ «{w}» حذف شد.", reply_markup=done_kb())


# ══════════════════════════════════════════
# HASHTAGS
# ══════════════════════════════════════════

@router.callback_query(F.data == "wiz:ht_add")
async def wiz_ht_add(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("➕ هشتگ‌ها (با کاما، بدون #):\nمثال: ChatGPT, AItools, PromptEngineering", reply_markup=cancel_kb())
    except:
        await cb.message.answer("➕ هشتگ‌ها (با کاما، بدون #):\nمثال: ChatGPT, AItools, PromptEngineering", reply_markup=cancel_kb())
    await state.set_state(W.ht_input)


@router.message(W.ht_input, F.text & ~F.text.startswith("/"))
async def wiz_ht_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    tags = [t.strip().lstrip("#") for t in (msg.text or "").split(",") if t.strip()]
    if not tags:
        await msg.answer("❌ حداقل یه هشتگ.", reply_markup=cancel_kb())
        return
    async with async_session_factory() as s:
        added = []
        for t in tags:
            ex = await s.execute(select(Hashtag).where(Hashtag.tag == t))
            if ex.scalar_one_or_none():
                continue
            s.add(Hashtag(tag=t))
            added.append(t)
        await s.commit()
    await state.clear()
    if added:
        await msg.answer("✅ اضافه شد:\n" + "\n".join(f"#{t}" for t in added), reply_markup=done_kb())
    else:
        await msg.answer("⚠️ همه قبلاً بودن.", reply_markup=done_kb())


@router.callback_query(F.data == "wiz:ht_del")
async def wiz_ht_del(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("🗑️ ID هشتگ:", reply_markup=cancel_kb())
    except:
        await cb.message.answer("🗑️ ID هشتگ:", reply_markup=cancel_kb())
    await state.set_state(W.ht_del)


@router.message(W.ht_del, F.text & ~F.text.startswith("/"))
async def wiz_ht_del_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    try:
        hid = int((msg.text or "").strip())
    except:
        await msg.answer("❌ عدد.", reply_markup=cancel_kb())
        return
    async with async_session_factory() as s:
        r = await s.execute(select(Hashtag).where(Hashtag.id == hid))
        ht = r.scalar_one_or_none()
        if not ht:
            await msg.answer(f"❌ ID {hid} نیست.", reply_markup=done_kb())
            await state.clear()
            return
        t = ht.tag
        await s.delete(ht)
        await s.commit()
    await state.clear()
    await msg.answer(f"✅ #{t} حذف شد.", reply_markup=done_kb())


# ══════════════════════════════════════════
# RECEIVERS
# ══════════════════════════════════════════

@router.callback_query(F.data == "wiz:rc_add")
async def wiz_rc_add(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text(
            "➕ Chat ID (با کاما):\n<code>123456789, -1001234567890</code>\n\n💡 برای کانال: پیام رو به @userinfobot فوروارد کن.",
            reply_markup=cancel_kb(), parse_mode="HTML",
        )
    except:
        await cb.message.answer(
            "➕ Chat ID (با کاما):\n<code>123456789, -1001234567890</code>",
            reply_markup=cancel_kb(), parse_mode="HTML",
        )
    await state.set_state(W.rc_input)


@router.message(W.rc_input, F.text & ~F.text.startswith("/"))
async def wiz_rc_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    ids = []
    for p in (msg.text or "").split(","):
        try:
            ids.append(int(p.strip()))
        except:
            await msg.answer(f"❌ «{p.strip()}» عدد نیست.", reply_markup=cancel_kb())
            return
    async with async_session_factory() as s:
        rv = (await s.execute(select(Setting.value).where(Setting.key == "receiver_ids"))).scalar_one_or_none()
        try:
            cur = json.loads(rv) if rv else []
        except:
            cur = []
        for cid in ids:
            if cid not in cur:
                cur.append(cid)
        r = await s.execute(select(Setting).where(Setting.key == "receiver_ids"))
        st = r.scalar_one_or_none()
        if st:
            st.value = json.dumps(cur)
        else:
            s.add(Setting(key="receiver_ids", value=json.dumps(cur)))
        await s.commit()
    await state.clear()
    await msg.answer(f"✅ {len(ids)} اضافه شد. کل: {len(cur)}", reply_markup=done_kb())


# ══════════════════════════════════════════
# ADMINS
# ══════════════════════════════════════════

@router.callback_query(F.data == "wiz:adm_add")
async def wiz_adm_add(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or cb.from_user.id != settings.super_admin_id:
        return
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("➕ آیدی عددی مدیر:", reply_markup=cancel_kb())
    except:
        await cb.message.answer("➕ آیدی عددی مدیر:", reply_markup=cancel_kb())
    await state.set_state(W.adm_input)


@router.message(W.adm_input, F.text & ~F.text.startswith("/"))
async def wiz_adm_input(msg: Message, state: FSMContext):
    if not msg.from_user or msg.from_user.id != settings.super_admin_id:
        return
    try:
        tid = int((msg.text or "").strip())
    except:
        await msg.answer("❌ عدد.", reply_markup=cancel_kb())
        return
    async with async_session_factory() as s:
        ex = await s.execute(select(User).where(User.telegram_id == tid))
        if ex.scalar_one_or_none():
            await msg.answer("⚠️ قبلاً مدیره.", reply_markup=done_kb())
            await state.clear()
            return
        s.add(User(telegram_id=tid, is_super_admin=False))
        await s.commit()
    await state.clear()
    await msg.answer(f"✅ مدیر: <code>{tid}</code>", reply_markup=done_kb(), parse_mode="HTML")


@router.callback_query(F.data == "wiz:adm_del")
async def wiz_adm_del(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or cb.from_user.id != settings.super_admin_id:
        return
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("🗑️ شناسه (DB ID) مدیر:", reply_markup=cancel_kb())
    except:
        await cb.message.answer("🗑️ شناسه (DB ID) مدیر:", reply_markup=cancel_kb())
    await state.set_state(W.adm_del)


@router.message(W.adm_del, F.text & ~F.text.startswith("/"))
async def wiz_adm_del_input(msg: Message, state: FSMContext):
    if not msg.from_user or msg.from_user.id != settings.super_admin_id:
        return
    try:
        aid = int((msg.text or "").strip())
    except:
        await msg.answer("❌ عدد.", reply_markup=cancel_kb())
        return
    async with async_session_factory() as s:
        r = await s.execute(select(User).where(User.id == aid))
        a = r.scalar_one_or_none()
        if not a:
            await msg.answer(f"❌ ID {aid} نیست.", reply_markup=done_kb())
            await state.clear()
            return
        if a.is_super_admin:
            await msg.answer("⛔ سوپرادمین!", reply_markup=done_kb())
            await state.clear()
            return
        await s.delete(a)
        await s.commit()
    await state.clear()
    await msg.answer("✅ مدیر حذف شد.", reply_markup=done_kb())


# ══════════════════════════════════════════
# SCHEDULE
# ══════════════════════════════════════════

async def _set_setting(key, val):
    async with async_session_factory() as s:
        r = await s.execute(select(Setting).where(Setting.key == key))
        st = r.scalar_one_or_none()
        if st:
            st.value = val
        else:
            s.add(Setting(key=key, value=val))
        await s.commit()


@router.callback_query(F.data == "wiz:time")
async def wiz_time(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("🕐 ساعت:\nمثال: <code>09:00</code> یا <code>0:00</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    except:
        await cb.message.answer("🕐 ساعت:\nمثال: <code>09:00</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    await state.set_state(W.sch_time)


@router.message(W.sch_time, F.text & ~F.text.startswith("/"))
async def wiz_time_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    try:
        parts = (msg.text or "").strip().split(":")
        h, m = int(parts[0]), int(parts[1])
        assert 0 <= h <= 23 and 0 <= m <= 59
    except:
        await msg.answer("❌ فرمت: 09:00", reply_markup=cancel_kb())
        return
    await _set_setting("digest_hour", str(h))
    await _set_setting("digest_minute", str(m))
    from app.services.scheduler import scheduler
    from apscheduler.triggers.cron import CronTrigger
    try:
        scheduler.reschedule_job("daily_digest", trigger=CronTrigger(hour=h, minute=m))
    except:
        pass
    await state.clear()
    await msg.answer(f"✅ ساعت ارسال: {h}:{m:02d}", reply_markup=done_kb())


@router.callback_query(F.data == "wiz:count")
async def wiz_count(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("📊 حداکثر مطالب:\nمثال: <code>15</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    except:
        await cb.message.answer("📊 حداکثر مطالب:\nمثال: <code>15</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    await state.set_state(W.sch_count)


@router.message(W.sch_count, F.text & ~F.text.startswith("/"))
async def wiz_count_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    try:
        n = int((msg.text or "").strip())
        assert 1 <= n <= 50
    except:
        await msg.answer("❌ عدد 1-50.", reply_markup=cancel_kb())
        return
    await _set_setting("digest_max_items", str(n))
    await state.clear()
    await msg.answer(f"✅ حداکثر: {n}", reply_markup=done_kb())


@router.callback_query(F.data == "wiz:score")
async def wiz_score(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try:
        await cb.answer()
    except:
        pass
    try:
        await cb.message.edit_text("⭐ حداقل امتیاز (0=غیرفعال):\nمثال: <code>7</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    except:
        await cb.message.answer("⭐ حداقل امتیاز (0=غیرفعال):\nمثال: <code>7</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    await state.set_state(W.sch_score)


@router.message(W.sch_score, F.text & ~F.text.startswith("/"))
async def wiz_score_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    try:
        v = float((msg.text or "").strip())
    except:
        await msg.answer("❌ عدد.", reply_markup=cancel_kb())
        return
    await _set_setting("min_score", str(v))
    await state.clear()
    await msg.answer(f"✅ حداقل امتیاز: {v}", reply_markup=done_kb())
