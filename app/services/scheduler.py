from __future__ import annotations

import json
import asyncio
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


async def _get_next_batch() -> int:
    async with async_session_factory() as s:
        r = await s.execute(select(Setting.value).where(Setting.key == "current_batch"))
        st = r.scalar_one_or_none()
        try:
            cur = int(st) if st else 0
        except:
            cur = 0
        nxt = cur + 1
        r2 = await s.execute(select(Setting).where(Setting.key == "current_batch"))
        row = r2.scalar_one_or_none()
        if row:
            row.value = str(nxt)
        else:
            s.add(Setting(key="current_batch", value=str(nxt)))
        await s.commit()
        return nxt


async def _collect_one_source(source, batch: int) -> int:
    try:
        collector_cls = COLLECTOR_MAP.get(source.type)
        if not collector_cls:
            return 0
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
                        url=raw.url, html=raw.html,
                        published_at=raw.published_at, batch=batch,
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
                logger.error(f"Process [{source.name}]: {e}")
        async with async_session_factory() as session:
            await session.execute(
                update(Source).where(Source.id == source.id).values(last_fetch_at=datetime.now(timezone.utc))
            )
            await session.commit()
        logger.info(f"[{source.name}] batch#{batch}: {new_count} new / {len(raw_items)} fetched")
        return new_count
    except Exception as e:
        logger.error(f"Source [{source.name}] error: {e}")
        return 0


async def _run_collectors() -> None:
    logger.info("═══ Collection START ═══")
    try:
        async with async_session_factory() as session:
            result = await session.execute(select(Source).where(Source.is_active == True))
            sources = result.scalars().all()
        if not sources:
            logger.warning("No active sources!")
            return

        batch = await _get_next_batch()
        logger.info(f"Collection batch #{batch}")

        sem = asyncio.Semaphore(5)
        async def limited(src):
            async with sem:
                return await _collect_one_source(src, batch)

        tasks = [limited(s) for s in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total = sum(r for r in results if isinstance(r, int))
        errs = sum(1 for r in results if isinstance(r, Exception))
        logger.info(f"═══ Batch #{batch} done: {total} new, {errs} errors ═══")
    except Exception as e:
        logger.error(f"Collection fatal: {e}")


async def _run_digest() -> None:
    logger.info("═══ Digest START ═══")
    try:
        from app.main import get_bot_instance
        bot = get_bot_instance()
        if not bot:
            logger.error("Bot not available!")
            return
        from app.services.delivery import deliver_digest
        await deliver_digest(bot)
    except Exception as e:
        logger.error(f"Digest error: {e}")


def setup_scheduler() -> None:
    scheduler.add_job(_run_collectors, trigger=IntervalTrigger(hours=2), id="collect_cycle", replace_existing=True, max_instances=1)
    scheduler.add_job(_run_digest, trigger=CronTrigger(hour=settings.digest_hour, minute=settings.digest_minute), id="daily_digest", replace_existing=True, max_instances=1)
    scheduler.start()
    logger.info(f"Scheduler: collect every 2h, digest at {settings.digest_hour:02d}:{settings.digest_minute:02d}")


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
