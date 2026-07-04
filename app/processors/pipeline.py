from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.models import ContentItem, Source, Keyword
from app.processors.cleaner import clean_content
from app.processors.deduplicator import is_duplicate, compute_hash
from app.services.ai_service import ai_service


async def get_negative_keywords(session: AsyncSession) -> list[str]:
    result = await session.execute(select(Keyword.word).where(Keyword.is_negative == True))
    return [row[0].lower() for row in result.all()]


async def get_positive_keywords(session: AsyncSession) -> list[str]:
    result = await session.execute(select(Keyword.word).where(Keyword.is_negative == False))
    return [row[0].lower() for row in result.all()]


def passes_keyword_filter(text: str, positive: list[str], negative: list[str]) -> bool:
    lower_text = text.lower()
    for kw in negative:
        if kw in lower_text:
            return False
    if positive:
        if not any(kw in lower_text for kw in positive):
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
    clean_title, clean_body = clean_content(title, raw_text, html)
    if not clean_title and not clean_body:
        return None

    neg_kw = await get_negative_keywords(session)
    pos_kw = await get_positive_keywords(session)
    if not passes_keyword_filter(f"{clean_title} {clean_body}", pos_kw, neg_kw):
        return None

    if await is_duplicate(session, url, clean_body):
        return None

    analysis = await ai_service.analyze_content(clean_title, clean_body[:3000], url)
    c_hash = await compute_hash(url, clean_body)

    item = ContentItem(
        source_id=source.id,
        title=clean_title,
        raw_text=clean_body[:10000],
        summary_fa=analysis["summary_fa"],
        summary_en=analysis["summary_en"],
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
