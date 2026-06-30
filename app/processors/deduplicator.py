from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.models.models import ContentItem
from app.utils.helpers import content_hash


async def is_duplicate(session: AsyncSession, url: str | None, text: str) -> bool:
    """Check if content already exists based on URL hash or content hash."""
    text_hash = content_hash(text[:2000]) if text else None

    # Check URL
    if url:
        url_hash = content_hash(url)
        result = await session.execute(
            select(ContentItem.id).where(ContentItem.content_hash == url_hash).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            logger.debug(f"Dedup: URL duplicate found for {url[:80]}")
            return True

    # Check content hash
    if text_hash:
        result = await session.execute(
            select(ContentItem.id).where(ContentItem.content_hash == text_hash).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            logger.debug("Dedup: Content hash duplicate found")
            return True

    return False


async def compute_hash(url: str | None, text: str) -> str:
    """Compute a content hash for storage."""
    if url:
        return content_hash(url)
    return content_hash(text[:2000])