from __future__ import annotations

import json
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy import select, update

from app.database import async_session_factory
from app.models.models import Source, Setting
from app.collectors import COLLECTOR_MAP
from app.processors.pipeline import process_single_item
from app.config import settings

scheduler = AsyncIOScheduler(timezone="UTC")


async def _run_collectors() -> None:
    logger.info("═══ Collection cycle START ═══")
    try:
        async with async_session_factory() as session:
            result = await session.execute(select(Source).where(Source.is_active == True))
            sources = result.scalars().all()

        if not sources:
            logger.warning("No active sources!")
            return

        total_new = 0
        for source in sources:
            try:
                collector_cls = COLLECTOR_MAP.get(source.type)
                if not collector_cls:
                    continue
                config = json.loads(source.config_json) if source.config_json else {}
                collector = collector_cls(config)
                raw_items = await collector.safe_collect()

                new_count = 0
                for raw in raw_items:
                    try:
                        async with async_session_factory() as session:
                            item = await process_single_item(
                                session=session, source=source,
                                title=raw.title, raw_text=raw.text,
                                url=raw.url, html=raw.html, published_at=raw.published_at,
                            )
                            if item:
                                new_count += 1
                                if item.score >= 9.0:
                                    from app.main import get_bot_instance
                                    bot = get_bot_instance()
                                    if bot:
                                        from app.services.delivery import deliver_urgent
                                        await deliver_urgent(bot, item)
                            await session.commit()
                    except Exception as e:
                        logger.error(f"Process item error: {e}")

                async with async_session_factory() as session:
                    await session.execute(
                        update(Source).where(Source.id == source.id).values(last_fetch_at=datetime.now(timezone.utc))
                    )
                    await session.commit()

                total_new += new_count
                logger.info(f"[{source.name}]: {new_count} new / {len(raw_items)} fetched")
            except Exception as e:
                logger.error(f"Source [{source.name}] error: {e}")

        logger.info(f"═══ Collection done: {total_new} new items ═══")
    except Exception as e:
        logger.error(f"Collection cycle fatal error: {e}")


async def _run_digest() -> None:
    logger.info("═══ Digest START ═══")
    try:
        from app.main import get_bot_instance
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot instance not available!")
            return

        from app.services.delivery import deliver_digest
        await deliver_digest(bot)
    except Exception as e:
        logger.error(f"Digest error: {e}")


def setup_scheduler() -> None:
    scheduler.add_job(
        _run_collectors,
        trigger=IntervalTrigger(hours=2),
        id="collect_cycle",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.add_job(
        _run_digest,
        trigger=CronTrigger(hour=settings.digest_hour, minute=settings.digest_minute),
        id="daily_digest",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()
    logger.info(f"Scheduler: collect every 2h, digest at {settings.digest_hour:02d}:{settings.digest_minute:02d}")


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
