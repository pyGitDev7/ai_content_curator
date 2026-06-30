from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select, update

from app.database import async_session_factory
from app.models.models import Source, ContentItem, Setting
from app.collectors import COLLECTOR_MAP
from app.processors.pipeline import process_single_item
from app.services.delivery import deliver_digest, deliver_urgent, get_setting
from app.services.ai_service import ai_service
from app.config import settings

scheduler = AsyncIOScheduler(timezone="UTC")


async def _run_collectors() -> None:
    """Fetch content from all active sources."""
    logger.info("=== Starting collection cycle ===")

    async with async_session_factory() as session:
        result = await session.execute(
            select(Source).where(Source.is_active == True)
        )
        sources = result.scalars().all()

    total_new = 0
    for source in sources:
        try:
            collector_cls = COLLECTOR_MAP.get(source.type)
            if not collector_cls:
                logger.warning(f"No collector for type: {source.type}")
                continue

            import json
            config = json.loads(source.config_json) if source.config_json else {}
            collector = collector_cls(config)
            raw_items = await collector.safe_collect()

            new_count = 0
            for raw in raw_items:
                async with async_session_factory() as session:
                    item = await process_single_item(
                        session=session,
                        source=source,
                        title=raw.title,
                        raw_text=raw.text,
                        url=raw.url,
                        html=raw.html,
                        published_at=raw.published_at,
                    )
                    if item:
                        new_count += 1
                        # Check for urgent delivery
                        if item.score >= 9.0:
                            from app.main import get_bot_instance
                            bot = get_bot_instance()
                            if bot:
                                await deliver_urgent(bot, item)
                    await session.commit()

            # Update last fetch time
            async with async_session_factory() as session:
                await session.execute(
                    update(Source)
                    .where(Source.id == source.id)
                    .values(last_fetch_at=datetime.now(timezone.utc))
                )
                await session.commit()

            total_new += new_count
            logger.info(f"Source [{source.name}]: {new_count} new items")

        except Exception as e:
            logger.error(f"Error collecting from source {source.name}: {e}")

    logger.info(f"=== Collection cycle complete: {total_new} new items total ===")


async def _run_digest() -> None:
    """Send the daily digest."""
    logger.info("=== Starting daily digest ===")
    try:
        from app.main import get_bot_instance
        bot = get_bot_instance()
        if bot:
            await deliver_digest(bot)
        else:
            logger.error("Bot instance not available for digest")
    except Exception as e:
        logger.error(f"Digest error: {e}")


def setup_scheduler() -> None:
    """Configure and start all scheduled jobs."""

    # Collect every 2 hours
    scheduler.add_job(
        _run_collectors,
        trigger=IntervalTrigger(hours=2),
        id="collect_cycle",
        name="Content Collection",
        replace_existing=True,
        max_instances=1,
    )

    # Daily digest at configured time
    scheduler.add_job(
        _run_digest,
        trigger=CronTrigger(hour=settings.digest_hour, minute=settings.digest_minute),
        id="daily_digest",
        name="Daily Digest",
        replace_existing=True,
        max_instances=1,
    )

    # Cleanup old content every 24 hours (keep last 30 days)
    async def cleanup_old():
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        async with async_session_factory() as session:
            result = await session.execute(
                select(ContentItem).where(ContentItem.created_at < cutoff).limit(1000)
            )
            old_items = result.scalars().all()
            for item in old_items:
                await session.delete(item)
            await session.commit()
            if old_items:
                logger.info(f"Cleanup: removed {len(old_items)} old items")

    scheduler.add_job(
        cleanup_old,
        trigger=CronTrigger(hour=3, minute=0),
        id="cleanup",
        name="Old Content Cleanup",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(f"Scheduler started. Digest at {settings.digest_hour:02d}:{settings.digest_minute:02d}")


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shut down")