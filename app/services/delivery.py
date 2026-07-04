from __future__ import annotations

import json

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


async def deliver_urgent(bot, item: ContentItem) -> None:
    rids = await _get_receiver_ids()
    if not rids:
        logger.warning("Urgent: no receivers")
        return
    msg = format_single_item_html(item)
    for cid in rids:
        try:
            await bot.send_message(chat_id=cid, text=msg, parse_mode="HTML", disable_web_page_preview=False)
            async with async_session_factory() as s:
                s.add(DeliveredLog(content_id=item.id, chat_id=cid))
                await s.commit()
        except Exception as e:
            logger.error(f"Urgent {cid}: {e}")
    async with async_session_factory() as s:
        r = await s.execute(select(ContentItem).where(ContentItem.id == item.id))
        db = r.scalar_one_or_none()
        if db:
            db.delivered = True
            await s.commit()


async def deliver_digest(bot) -> None:
    rids = await _get_receiver_ids()
    async with async_session_factory() as session:
        max_items = int(await _get_setting(session, "digest_max_items", str(cfg.digest_max_items)))
        min_score = float(await _get_setting(session, "min_score", "0"))

    if not rids:
        logger.warning("Digest: no receivers!")
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
        for cid in rids:
            try:
                await bot.send_message(chat_id=cid, text="📭 امروز محتوای جدیدی نداریم.")
            except:
                pass
        return

    header = f"📋 <b>خلاصه روزانه</b>\n📅 {items[0].created_at.strftime('%Y-%m-%d')}\n\n{len(items)} مطلب برتر:\n──────────────"

    sent = 0
    for cid in rids:
        try:
            await bot.send_message(chat_id=cid, text=header, parse_mode="HTML")
            for item in items:
                try:
                    await bot.send_message(
                        chat_id=cid, text=format_single_item_html(item),
                        parse_mode="HTML", disable_web_page_preview=False,
                    )
                except Exception as e:
                    logger.error(f"Item {item.id} -> {cid}: {e}")
            sent += 1
        except Exception as e:
            logger.error(f"Digest header {cid}: {e}")

    if sent > 0:
        async with async_session_factory() as s:
            for item in items:
                r = await s.execute(select(ContentItem).where(ContentItem.id == item.id))
                db = r.scalar_one_or_none()
                if db:
                    db.delivered = True
                for cid in rids:
                    s.add(DeliveredLog(content_id=item.id, chat_id=cid))
            await s.commit()

    logger.info(f"Digest: {len(items)} items -> {sent}/{len(rids)}")
