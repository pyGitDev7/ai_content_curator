from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.models import ContentItem, DeliveredLog, Setting
from app.database import async_session_factory
from app.config import settings as cfg
from app.utils.helpers import format_content_html, format_digest_html


async def _get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    r = await session.execute(select(Setting.value).where(Setting.key == key))
    v = r.scalar_one_or_none()
    return v if v is not None else default


async def deliver_urgent(bot, item: ContentItem) -> None:
    async with async_session_factory() as session:
        raw = await _get_setting(session, "receiver_ids", "[]")
        try:
            rids = json.loads(raw)
        except:
            rids = []

    if not rids:
        logger.warning("Urgent delivery skipped: no receivers")
        return

    hashtags = json.loads(item.tags_json) if item.tags_json else []
    msg = format_content_html(
        title=item.title, summary=item.summary or "",
        url=item.url, category=item.category, score=item.score, hashtags=hashtags,
    )
    for cid in rids:
        try:
            await bot.send_message(chat_id=cid, text=msg, parse_mode="HTML")
            async with async_session_factory() as session:
                session.add(DeliveredLog(content_id=item.id, chat_id=cid))
                await session.commit()
            logger.info(f"Urgent: {item.id} -> {cid}")
        except Exception as e:
            logger.error(f"Urgent error {cid}: {e}")

    async with async_session_factory() as session:
        r = await session.execute(select(ContentItem).where(ContentItem.id == item.id))
        db = r.scalar_one_or_none()
        if db:
            db.delivered = True
            await session.commit()


async def deliver_digest(bot) -> None:
    async with async_session_factory() as session:
        raw_rids = await _get_setting(session, "receiver_ids", "[]")
        try:
            rids = json.loads(raw_rids)
        except:
            rids = []
        max_items = int(await _get_setting(session, "digest_max_items", str(cfg.digest_max_items)))
        min_score = float(await _get_setting(session, "min_score", "0"))

    if not rids:
        logger.warning("Digest: no receivers configured!")
        try:
            await bot.send_message(
                chat_id=cfg.super_admin_id,
                text="⚠️ خلاصه ارسال نشد: هیچ دریافت‌کننده‌ای تنظیم نشده.\nاز پنل > دریافت‌کنندگان > افزودن",
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
        logger.info("Digest: no new content")
        for cid in rids:
            try:
                await bot.send_message(chat_id=cid, text="📭 امروز محتوای جدیدی نداریم.")
            except Exception as e:
                logger.error(f"Empty digest error {cid}: {e}")
        return

    digest_items = [
        {"title": i.title, "summary": i.summary or "", "url": i.url,
         "category": i.category or "other", "score": i.score}
        for i in items
    ]
    msg = format_digest_html(digest_items)

    sent = 0
    for cid in rids:
        try:
            await bot.send_message(chat_id=cid, text=msg, parse_mode="HTML", disable_web_page_preview=True)
            sent += 1
        except Exception as e:
            logger.error(f"Digest error {cid}: {e}")

    if sent > 0:
        async with async_session_factory() as session:
            for item in items:
                r = await session.execute(select(ContentItem).where(ContentItem.id == item.id))
                db = r.scalar_one_or_none()
                if db:
                    db.delivered = True
                for cid in rids:
                    session.add(DeliveredLog(content_id=item.id, chat_id=cid))
            await session.commit()

    logger.info(f"Digest sent: {len(items)} items to {sent}/{len(rids)} receivers")
