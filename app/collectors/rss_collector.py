from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import feedparser
from loguru import logger

from app.collectors.base import BaseCollector, RawContent


class RSSCollector(BaseCollector):
    """Collects content from RSS/Atom feeds."""

    async def collect(self) -> list[RawContent]:
        url = self.config.get("url", "")
        if not url:
            logger.warning("RSS collector: no URL configured")
            return []

        client = await self._get_client()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"RSS fetch error for {url}: {e}")
            return []

        feed = feedparser.parse(resp.text)
        items: list[RawContent] = []

        for entry in feed.entries[:30]:
            title = entry.get("title", "Untitled")
            link = entry.get("link", "")
            # Get description/content
            text = ""
            if hasattr(entry, "content") and entry.content:
                text = entry.content[0].get("value", "")
            if not text:
                text = entry.get("summary", entry.get("description", ""))

            # Parse published date
            pub_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    pub_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            items.append(
                RawContent(
                    title=title,
                    text=text,
                    url=link,
                    html=text if "<" in text else None,
                    published_at=pub_at,
                )
            )

        logger.info(f"RSS [{url[:50]}]: fetched {len(items)} items")
        return items