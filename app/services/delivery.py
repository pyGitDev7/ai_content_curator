from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.models import ContentItem, DeliveredLog, Setting
from app.database import async_session_factory
from app.utils.helpers import format_content_message, format_digest_message


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    result = await session.execute(select(Setting.value).where(Setting.key == key))
    row = result.scalar_one_or_none()
    return row if row is not None else default


async def get_receiver_ids(session: AsyncSession) -> list[int]:
    raw = await get_setting(session, "receiver_ids", "[]")
    try:
        return json.loads(raw)
    except Exception:
        return []


async def get_max_items(session: AsyncSession) -> int:
    raw = await get_setting(session, "digest_max_items", "10")
    try:
        return int(raw)
    except Exception:
        return 10


async def get_category_filter(session: AsyncSession) -> list[str]:
    """Return enabled categories (empty list means all enabled)."""
    raw = await get_setting(session, "enabled_categories", "")
    if not raw:
        return []  # all enabled
    return [c.strip() for c in raw.split(",") if c.strip()]


async def get_min_score(session: AsyncSession) -> float:
    raw = await get_setting(session, "min_score", "0")
    try:
        return float(raw)
    except Exception:
        return 0.0


async def deliver_urgent(bot, item: ContentItem) -> None:
    """Deliver a single high-score item immediately."""
    async with async_session_factory() as session:
        receiver_ids = await get_receiver_ids(session)

        if not receiver_ids:
            logger.warning("No receivers configured for urgent delivery")
            return

        hashtags = json.loads(item.tags_json) if item.tags_json else []
        message = format_content_message(
            title=item.title,
            summary=item.summary or "",
            url=item.url,
            category=item.category,
            score=item.score,
            hashtags=hashtags,
        )

        for chat_id in receiver_ids:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="MarkdownV2",
                    disable_web_page_preview=False,
                )
                log = DeliveredLog(content_id=item.id, chat_id=chat_id)
                session.add(log)
                logger.info(f"Urgent delivery: item {item.id} -> chat {chat_id}")
            except Exception as e:
                logger.error(f"Urgent delivery error to {chat_id}: {e}")

        item.delivered = True
        await session.commit()


async def deliver_digest(bot) -> None:
    """Deliver a daily digest of top items."""
    async with async_session_factory() as session:
        receiver_ids = await get_receiver_ids(session)
        max_items = await get_max_items(session)
        cat_filter = await get_category_filter(session)
        min_score = await get_min_score(session)

        if not receiver_ids:
            logger.warning("No receivers configured for digest")
            return

        # Build query for undelivered, processed items
        query = (
            select(ContentItem)
            .where(ContentItem.processed == True)
            .where(ContentItem.delivered == False)
            .where(ContentItem.score >= min_score)
            .order_by(ContentItem.score.desc())
            .limit(max_items)
        )

        result = await session.execute(query)
        items = result.scalars().all()

        # Apply category filter
        if cat_filter:
            items = [i for i in items if i.category in cat_filter]

        if not items:
            logger.info("No new items for digest")
            # Send "no content" message
            for chat_id in receiver_ids:
                try:
                    await bot.send_message(
                        chat_id=chat_id,
                        text="📭 امروز محتوای جدیدی برای ارسال وجود ندارد.",
                    )
                except Exception as e:
                    logger.error(f"Empty digest send error to {chat_id}: {e}")
            return

        # Format digest
        digest_items = [
            {
                "title": item.title,
                "summary": item.summary or "",
                "url": item.url,
                "category": item.category or "other",
                "score": item.score,
            }
            for item in items
        ]
        message = format_digest_message(digest_items)

        for chat_id in receiver_ids:
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode="MarkdownV2",
                    disable_web_page_preview=True,
                )
                for item in items:
                    log = DeliveredLog(content_id=item.id, chat_id=chat_id)
                    session.add(log)
                logger.info(f"Digest delivered: {len(items)} items -> chat {chat_id}")
            except Exception as e:
                logger.error(f"Digest delivery error to {chat_id}: {e}")

        # Mark as delivered
        for item in items:
            item.delivered = True

        await session.commit()