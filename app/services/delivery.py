from __future__ import annotations

import json
import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.models import ContentItem, DeliveredLog, Setting
from app.database import async_session_factory
from app.config import settings as cfg
from app.utils.helpers import format_single_item_html


async def _get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    r = await session.execute(select(Setting.value).where(Setting.key == key))
    v = r.scalar_one_or_none()
    return v if v is not None else default


async def _get_receiver_ids() -> list[int]:
    async with async_session_factory() as session:
        raw = await _get_setting(session, "receiver_ids", "[]")
        try:
            return json.loads(raw)
        except:
            return []


async def _send_to_one(bot, cid: int, text: str, parse_mode="HTML", disable_preview=True) -> bool:
    try:
        await bot.send_message(chat_id=cid, text=text, parse_mode=parse_mode, disable_web_page_preview=disable_preview)
        return True
    except Exception as e:
        logger.error(f"Send to {cid} failed: {e}")
        return False


async def deliver_urgent(bot, item: ContentItem) -> None:
    rids = await _get_receiver_ids()
    if not rids:
        logger.warning("Urgent: no receivers")
        return
    msg = format_single_item_html(item)
    ok = 0
    for cid in rids:
        if await _send_to_one(bot, cid, msg, disable_preview=False):
            ok += 1
            async with async_session_factory() as s:
                s.add(DeliveredLog(content_id=item.id, chat_id=cid))
                await s.commit()
    async with async_session_factory() as s:
        r = await s.execute(select(ContentItem).where(ContentItem.id == item.id))
        db = r.scalar_one_or_none()
        if db:
            db.delivered = True
            await s.commit()
    logger.info(f"Urgent [{item.title[:40]}]: {ok}/{len(rids)} sent")


async def deliver_digest(bot) -> None:
    rids = await _get_receiver_ids()

    async with async_session_factory() as session:
        max_items = int(await _get_setting(session, "digest_max_items", str(cfg.digest_max_items)))
        min_score = float(await _get_setting(session, "min_score", "0"))

    if not rids:
        logger.warning("Digest: no receivers configured!")
        try:
            await bot.send_message(
                chat_id=cfg.super_admin_id,
                text="⚠️ خلاصه ارسال نشد: دریافت‌کننده تنظیم نشده.\nاز پنل > 📬 دریافت‌کنندگان > ➕ افزودن",
            )
        except:
            pass
        return

    async with async_session_factory() as session:
        result = await session.execute(
            select(ContentItem)
            .where(ContentItem.processed == True, ContentItem.delivered == False, ContentItem.score >= min_score)
            .order_by(ContentItem.score.desc())
            .limit(max_items)
        )
        items = result.scalars().all()

    if not items:
        logger.info("Digest: no undelivered content")
        for cid in rids:
            await _send_to_one(bot, cid, "📭 امروز محتوای جدید آماده ارسال نداریم.")
        return

    logger.info(f"Digest: sending {len(items)} items to {len(rids)} receivers")

    # Send header to all receivers
    header = f"📋 <b>خلاصه روزانه</b>\n📅 {items[0].created_at.strftime('%Y-%m-%d')}\n\n{len(items)} مطلب برتر:\n──────────────"

    sent_ok = 0
    for cid in rids:
        if not await _send_to_one(bot, cid, header):
            continue

        # Send each item as separate message
        item_ok = 0
        for item in items:
            msg = format_single_item_html(item)
            if await _send_to_one(bot, cid, msg, disable_preview=False):
                item_ok += 1
            else:
                # Fallback short message
                short = f"<b>{item.title[:80]}</b>\n⭐ {item.score}/10"
                if item.url:
                    short += f'\n🔗 <a href="{item.url}">لینک</a>'
                await _send_to_one(bot, cid, short)

        logger.info(f"Digest -> {cid}: {item_ok}/{len(items)} items sent")
        sent_ok += 1

    # Mark as delivered
    if sent_ok > 0:
        async with async_session_factory() as s:
            for item in items:
                r = await s.execute(select(ContentItem).where(ContentItem.id == item.id))
                db = r.scalar_one_or_none()
                if db:
                    db.delivered = True
                for cid in rids:
                    s.add(DeliveredLog(content_id=item.id, chat_id=cid))
            await s.commit()

    logger.info(f"Digest complete: {len(items)} items -> {sent_ok}/{len(rids)} receivers")
