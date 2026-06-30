from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select, func as sqlfunc
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.models import ContentItem, Source, Keyword
from app.processors.cleaner import clean_content
from app.processors.deduplicator import is_duplicate, compute_hash
from app.services.ai_service import ai_service


async def get_negative_keywords(session: AsyncSession) -> list[str]:
    """Load negative keywords from database."""
    result = await session.execute(
        select(Keyword.word).where(Keyword.is_negative == True)
    )
    return [row[0].lower() for row in result.all()]


async def get_positive_keywords(session: AsyncSession) -> list[str]:
    """Load positive keywords from database."""
    result = await session.execute(
        select(Keyword.word).where(Keyword.is_negative == False)
    )
    return [row[0].lower() for row in result.all()]


def passes_keyword_filter(
    text: str, positive: list[str], negative: list[str]
) -> bool:
    """Check if content passes keyword filters."""
    lower_text = text.lower()

    # Negative keywords: reject if ANY matches
    for kw in negative:
        if kw in lower_text:
            logger.debug(f"Blocked by negative keyword: {kw}")
            return False

    # Positive keywords: if any exist, at least one must match
    if positive:
        if not any(kw in lower_text for kw in positive):
            logger.debug("No positive keyword match")
            return False

    return True


async def process_single_item(
    session: AsyncSession,
    source: Source,
    title: str,
    raw_text: str,
    url: str | None = None,
    html: str | None = None,
    published_at=None,
) -> ContentItem | None:
    """Process a single content item through the full pipeline."""

    # 1. Clean
    clean_title, clean_body = clean_content(title, raw_text, html)
    if not clean_title and not clean_body:
        return None

    # 2. Keyword filter
    neg_kw = await get_negative_keywords(session)
    pos_kw = await get_positive_keywords(session)
    combined_text = f"{clean_title} {clean_body}"
    if not passes_keyword_filter(combined_text, pos_kw, neg_kw):
        return None

    # 3. Deduplicate
    if await is_duplicate(session, url, clean_body):
        return None

    # 4. AI analysis (classify, summarize, score, hashtags)
    analysis = await ai_service.analyze_content(clean_title, clean_body[:3000], url)

    # 5. Compute hash
    c_hash = await compute_hash(url, clean_body)

    # 6. Create ContentItem
    item = ContentItem(
        source_id=source.id,
        title=clean_title,
        raw_text=clean_body[:10000],
        summary=analysis["summary_fa"],
        url=url,
        content_hash=c_hash,
        category=analysis["category"],
        score=analysis["score"],
        tags_json=json.dumps(analysis["hashtags"], ensure_ascii=False),
        published_at=published_at,
        processed=True,
    )
    session.add(item)
    await session.flush()
    logger.info(f"Processed: [{analysis['category']}] {clean_title[:60]} (score={analysis['score']})")
    return item


async def process_unprocessed_items(session: AsyncSession) -> list[ContentItem]:
    """Process any items that were saved without AI analysis (raw saved)."""
    result = await session.execute(
        select(ContentItem).where(ContentItem.processed == False).limit(50)
    )
    items = result.scalars().all()
    processed: list[ContentItem] = []

    for item in items:
        try:
            analysis = await ai_service.analyze_content(item.title, item.raw_text or "", item.url)
            item.summary = analysis["summary_fa"]
            item.category = analysis["category"]
            item.score = analysis["score"]
            item.tags_json = json.dumps(analysis["hashtags"], ensure_ascii=False)
            item.processed = True
            processed.append(item)
            await session.flush()
        except Exception as e:
            logger.error(f"Error processing item {item.id}: {e}")

    return processed