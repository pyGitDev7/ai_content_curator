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
        [InlineKeyboardButton(text="❌ لغو و بازگشت به پنل", callback_data="w:cancel")]
    ])


def done_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 بازگشت به پنل", callback_data="w:panel")]
    ])


# ══════════════ CANCEL & BACK ══════════════

@router.callback_query(F.data == "w:cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await cb.answer("لغو شد")
    except: pass
    await show_panel(cb)


@router.callback_query(F.data == "w:panel")
async def cb_back_panel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try: await cb.answer()
    except: pass
    await show_panel(cb)


@router.message(F.text == "/cancel")
async def cmd_cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("❌ لغو شد.")
    await show_panel(msg)


# ══════════════ SOURCE WIZARD ══════════════

SRC_TYPES = {
    "rss": "📰 RSS/Atom", "telegram": "✈️ کانال تلگرام", "twitter": "🐦 توییتر",
    "reddit": "🟠 Reddit", "website": "🌐 وبسایت", "github": "🐙 GitHub",
    "hackernews": "🔶 Hacker News", "arxiv": "📄 arXiv",
}

SRC_PROMPTS = {
    "rss": {"step1": "📝 لینک فید RSS:\n<code>https://openai.com/blog/rss</code>", "key": "url"},
    "telegram": {"step1": "📝 یوزرنیم کانال (بدون @):\n<code>AIinsights</code>", "key": "channel"},
    "twitter": {"step1": "📝 یوزرنیم توییتر (بدون @):\n<code>OpenAI</code>", "key": "username"},
    "reddit": {"step1": "📝 اسم ساب‌ردیت (بدون r/):\n<code>MachineLearning</code>", "key": "subreddit"},
    "website": {"step1": "📝 لینک سایت:\n<code>https://example.com/blog</code>", "step2": "📝 سلکتور CSS:\n<code>article</code>\n\nیا <code>skip</code>", "keys": ["url", "selector"], "defaults": {"selector": "article"}},
    "github": {"step1": "📝 زبان:\n<code>python</code> یا <code>all</code>", "step2": "📝 بازه:\n<code>daily</code> / <code>weekly</code> / <code>monthly</code>\n\nیا <code>skip</code>", "keys": ["language", "since"], "defaults": {"since": "daily"}},
    "hackernews": {"step1": "📝 کلمات کلیدی (با کاما):\n<code>AI, LLM, GPT</code>", "step2": "📝 حداکثر تعداد:\n<code>30</code>\n\nیا <code>skip</code>", "keys": ["keywords", "max_items"], "defaults": {"max_items": "30"}},
    "arxiv": {"step1": "📝 کوئری:\n<code>cat:cs.AI OR cat:cs.CL</code>", "step2": "📝 کلمات فیلتر:\n<code>LLM, prompt, GPT</code>\n\nیا <code>skip</code>", "keys": ["query", "keywords"], "defaults": {"keywords": "LLM,prompt,transformer"}},
}


class WizSrcStates(StatesGroup):
    choosing_type = State()
    step1 = State()
    step2 = State()
    name = State()


@router.callback_query(F.data == "wiz:src")
async def wiz_src_start(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    btns = [[InlineKeyboardButton(text=v, callback_data=f"ws:{k}")] for k, v in SRC_TYPES.items()]
    btns.append([InlineKeyboardButton(text="❌ لغو", callback_data="w:cancel")])
    try: await cb.answer()
    except: pass
    try:
        await cb.message.edit_text("➕ <b>افزودن منبع</b>\n\nنوع:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns), parse_mode="HTML")
    except:
        await cb.message.answer("➕ <b>افزودن منبع</b>\n\nنوع:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns), parse_mode="HTML")
    await state.set_state(WizSrcStates.choosing_type)


@router.callback_query(WizSrcStates.choosing_type, F.data.startswith("ws:"))
async def wiz_src_type(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    stype = cb.data.split(":")[1]
    prompt_info = SRC_PROMPTS.get(stype)
    if not prompt_info:
        return
    await state.update_data(stype=stype, values={})
    try: await cb.answer()
    except: pass
    try:
        await cb.message.edit_text(prompt_info["step1"], reply_markup=cancel_kb(), parse_mode="HTML")
    except:
        await cb.message.answer(prompt_info["step1"], reply_markup=cancel_kb(), parse_mode="HTML")
    await state.set_state(WizSrcStates.step1)


@router.message(WizSrcStates.step1, F.text & ~F.text.startswith("/"))
async def wiz_src_step1(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    val = (msg.text or "").strip()
    if not val:
        await msg.answer("❌ خالیه!", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    stype = data.get("stype", "rss")
    values = data.get("values", {})
    prompt_info = SRC_PROMPTS.get(stype, {})
    if "step2" in prompt_info:
        keys = prompt_info.get("keys", [])
        if keys:
            values[keys[0]] = val
        await state.update_data(values=values)
        step2_text = prompt_info["step2"]
        defaults = prompt_info.get("defaults", {})
        if defaults:
            fk = list(defaults.keys())[0]
            step2_text += f"\n\n💡 پیش‌فرض: <code>{defaults[fk]}</code>"
        await msg.answer(step2_text, reply_markup=cancel_kb(), parse_mode="HTML")
        await state.set_state(WizSrcStates.step2)
    else:
        sk = prompt_info.get("key", "url")
        values[sk] = val
        await state.update_data(values=values)
        await msg.answer("📝 اسم منبع:\n\nمثال: <code>وبلاگ OpenAI</code>", reply_markup=cancel_kb(), parse_mode="HTML")
        await state.set_state(WizSrcStates.name)


@router.message(WizSrcStates.step2, F.text & ~F.text.startswith("/"))
async def wiz_src_step2(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    val = (msg.text or "").strip()
    data = await state.get_data()
    stype = data.get("stype", "rss")
    values = data.get("values", {})
    prompt_info = SRC_PROMPTS.get(stype, {})
    defaults = prompt_info.get("defaults", {})
    keys = prompt_info.get("keys", [])
    if len(keys) >= 2:
        k2 = keys[1]
        if val.lower() == "skip" or not val:
            values[k2] = defaults.get(k2, "")
        else:
            values[k2] = val
    await state.update_data(values=values)
    hints = {
        "website": values.get("url", "").replace("https://", "").replace("http://", "").split("/")[0],
        "github": f"GitHub {values.get('language', 'all')}",
        "hackernews": f"HN: {values.get('keywords', '')[:20]}",
        "arxiv": f"arXiv: {values.get('query', '')[:20]}",
    }
    hint = hints.get(stype, "منبع من")
    await msg.answer(f"📝 اسم منبع:\n\nمثال: <code>{hint}</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    await state.set_state(WizSrcStates.name)


@router.message(WizSrcStates.name, F.text & ~F.text.startswith("/"))
async def wiz_src_name(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    name = (msg.text or "").strip()
    if not name:
        await msg.answer("❌ اسم بفرست.", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    stype = data.get("stype", "rss")
    values = data.get("values", {})
    prompt_info = SRC_PROMPTS.get(stype, {})
    config = {}
    if "keys" in prompt_info:
        for k in prompt_info["keys"]:
            config[k] = values.get(k, prompt_info.get("defaults", {}).get(k, ""))
    else:
        sk = prompt_info.get("key", "url")
        config[sk] = values.get(sk, "")
    if "max_items" in config:
        try: config["max_items"] = int(config["max_items"])
        except: config["max_items"] = 30
    async with async_session_factory() as s:
        s.add(Source(name=name, type=stype, config_json=json.dumps(config, ensure_ascii=False), is_active=True))
        await s.commit()
    await _log(msg.from_user.id, "add_source", f"{name} ({stype})")
    await state.clear()
    em = SRC_TYPES.get(stype, "📁")
    cfg_str = json.dumps(config, ensure_ascii=False, indent=2)
    await msg.answer(
        f"✅ <b>منبع اضافه شد!</b>\n\n📝 {name}\n📡 {em}\n⚙️ <code>{cfg_str}</code>",
        reply_markup=done_kb(), parse_mode="HTML",
    )


# ══════════════ KEYWORDS ══════════════

class WizKWStates(StatesGroup):
    input = State()


@router.callback_query(F.data == "wiz:kw_pos")
async def wiz_kw_pos(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    await state.update_data(neg=False)
    try: await cb.answer()
    except: pass
    try:
        await cb.message.edit_text("➕ کلمات مثبت (با کاما):\n<code>AI, LLM, ChatGPT</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    except:
        await cb.message.answer("➕ کلمات مثبت (با کاما):\n<code>AI, LLM, ChatGPT</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    await state.set_state(WizKWStates.input)


@router.callback_query(F.data == "wiz:kw_neg")
async def wiz_kw_neg(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    await state.update_data(neg=True)
    try: await cb.answer()
    except: pass
    try:
        await cb.message.edit_text("➖ کلمات منفی (با کاما):\n<code>bitcoin, crypto</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    except:
        await cb.message.answer("➖ کلمات منفی (با کاما):\n<code>bitcoin, crypto</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    await state.set_state(WizKWStates.input)


@router.message(WizKWStates.input, F.text & ~F.text.startswith("/"))
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


# ══════════════ HASHTAGS ══════════════

class WizHTStates(StatesGroup):
    input = State()


@router.callback_query(F.data == "wiz:ht_add")
async def wiz_ht_add(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try: await cb.answer()
    except: pass
    try:
        await cb.message.edit_text("➕ هشتگ‌ها (با کاما، بدون #):\n<code>ChatGPT, AItools</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    except:
        await cb.message.answer("➕ هشتگ‌ها (با کاما، بدون #):", reply_markup=cancel_kb())
    await state.set_state(WizHTStates.input)


@router.message(WizHTStates.input, F.text & ~F.text.startswith("/"))
async def wiz_ht_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    tags = [t.strip().lstrip("#") for t in (msg.text or "").split(",") if t.strip()]
    if not tags:
        await msg.answer("❌ حداقل یه هشتگ.", reply_markup=cancel_kb())
        return
    async with async_session_factory() as s:
        added = []
        dupes = []
        for t in tags:
            ex = await s.execute(select(Hashtag).where(Hashtag.tag == t))
            if ex.scalar_one_or_none():
                dupes.append(t)
                continue
            s.add(Hashtag(tag=t))
            added.append(t)
        await s.commit()
    await state.clear()
    lines = []
    if added:
        lines.append("✅ اضافه شد: " + ", ".join(f"#{t}" for t in added))
    if dupes:
        lines.append("⚠️ قبلاً بودن: " + ", ".join(f"#{t}" for t in dupes))
    await msg.answer("\n".join(lines), reply_markup=done_kb())


# ══════════════ RECEIVERS ══════════════

class WizRCStates(StatesGroup):
    input = State()


@router.callback_query(F.data == "wiz:rc_add")
async def wiz_rc_add(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try: await cb.answer()
    except: pass
    try:
        await cb.message.edit_text(
            "➕ <b>افزودن دریافت‌کننده</b>\n\n"
            "Chat ID عددی:\n"
            "<code>123456789, -1001234567890</code>\n\n"
            "💡 به @userinfobot پیام بده تا Chat ID رو ببینی.",
            reply_markup=cancel_kb(), parse_mode="HTML",
        )
    except:
        await cb.message.answer("➕ Chat ID:", reply_markup=cancel_kb())
    await state.set_state(WizRCStates.input)


@router.message(WizRCStates.input, F.text & ~F.text.startswith("/"))
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
    if not ids:
        await msg.answer("❌ حداقل یه Chat ID.", reply_markup=cancel_kb())
        return
    async with async_session_factory() as s:
        rv = (await s.execute(select(Setting.value).where(Setting.key == "receiver_ids"))).scalar_one_or_none()
        try: cur = json.loads(rv) if rv else []
        except: cur = []
        added = []
        for cid in ids:
            if cid not in cur:
                cur.append(cid)
                added.append(cid)
        r = await s.execute(select(Setting).where(Setting.key == "receiver_ids"))
        st = r.scalar_one_or_none()
        if st:
            st.value = json.dumps(cur)
        else:
            s.add(Setting(key="receiver_ids", value=json.dumps(cur)))
        await s.commit()
    await state.clear()
    await msg.answer(f"✅ {len(added)} اضافه شد. کل: {len(cur)}", reply_markup=done_kb())


# ══════════════ ADMINS ══════════════

class WizADMStates(StatesGroup):
    input = State()


@router.callback_query(F.data == "wiz:adm_add")
async def wiz_adm_add(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or cb.from_user.id != settings.super_admin_id:
        return
    try: await cb.answer()
    except: pass
    try:
        await cb.message.edit_text("➕ آیدی عددی مدیر:\n<code>987654321</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    except:
        await cb.message.answer("➕ آیدی عددی مدیر:", reply_markup=cancel_kb())
    await state.set_state(WizADMStates.input)


@router.message(WizADMStates.input, F.text & ~F.text.startswith("/"))
async def wiz_adm_input(msg: Message, state: FSMContext):
    if not msg.from_user or msg.from_user.id != settings.super_admin_id:
        return
    try: tid = int((msg.text or "").strip())
    except:
        await msg.answer("❌ عدد بفرست.", reply_markup=cancel_kb())
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


# ══════════════ SCHEDULE ══════════════

class WizSCHStates(StatesGroup):
    time = State()
    count = State()
    score = State()


async def _set_setting(key, val):
    async with async_session_factory() as s:
        r = await s.execute(select(Setting).where(Setting.key == key))
        st = r.scalar_one_or_none()
        if st: st.value = val
        else: s.add(Setting(key=key, value=val))
        await s.commit()


@router.callback_query(F.data == "wiz:time")
async def wiz_time(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try: await cb.answer()
    except: pass
    try:
        await cb.message.edit_text("🕐 ساعت:\n<code>09:00</code> یا <code>0:00</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    except:
        await cb.message.answer("🕐 ساعت:", reply_markup=cancel_kb())
    await state.set_state(WizSCHStates.time)


@router.message(WizSCHStates.time, F.text & ~F.text.startswith("/"))
async def wiz_time_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    try:
        parts = (msg.text or "").strip().split(":")
        h, m = int(parts[0]), int(parts[1])
        assert 0 <= h <= 23 and 0 <= m <= 59
    except:
        await msg.answer("❌ فرمت: <code>09:00</code>", reply_markup=cancel_kb(), parse_mode="HTML")
        return
    await _set_setting("digest_hour", str(h))
    await _set_setting("digest_minute", str(m))
    from app.services.scheduler import scheduler
    from apscheduler.triggers.cron import CronTrigger
    try: scheduler.reschedule_job("daily_digest", trigger=CronTrigger(hour=h, minute=m))
    except: pass
    await state.clear()
    await msg.answer(f"✅ ساعت: {h}:{m:02d}", reply_markup=done_kb())


@router.callback_query(F.data == "wiz:count")
async def wiz_count(cb: CallbackQuery, state: FSMContext):
    if not cb.from_user or not await is_auth(cb.from_user.id):
        return
    try: await cb.answer()
    except: pass
    try:
        await cb.message.edit_text("📊 حداکثر مطالب (1-50):\n<code>10</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    except:
        await cb.message.answer("📊 تعداد:", reply_markup=cancel_kb())
    await state.set_state(WizSCHStates.count)


@router.message(WizSCHStates.count, F.text & ~F.text.startswith("/"))
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
    try: await cb.answer()
    except: pass
    try:
        await cb.message.edit_text("⭐ حداقل امتیاز (0=همه):\n<code>7</code>", reply_markup=cancel_kb(), parse_mode="HTML")
    except:
        await cb.message.answer("⭐ امتیاز:", reply_markup=cancel_kb())
    await state.set_state(WizSCHStates.score)


@router.message(WizSCHStates.score, F.text & ~F.text.startswith("/"))
async def wiz_score_input(msg: Message, state: FSMContext):
    if not msg.from_user or not await is_auth(msg.from_user.id):
        return
    try: v = float((msg.text or "").strip())
    except:
        await msg.answer("❌ عدد.", reply_markup=cancel_kb())
        return
    await _set_setting("min_score", str(v))
    await state.clear()
    await msg.answer(f"✅ حداقل امتیاز: {v}", reply_markup=done_kb())
