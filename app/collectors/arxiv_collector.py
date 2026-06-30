from __future__ import annotations

import re
from typing import Any

from loguru import logger

from app.collectors.base import BaseCollector, RawContent


class ArxivCollector(BaseCollector):
    """Collects papers from arXiv using the Atom API."""

    async def collect(self) -> list[RawContent]:
        query = self.config.get("query", "cat:cs.AI")
        max_results = self.config.get("max_results", 20)
        keywords_str = self.config.get("keywords", "")
        keywords = [k.strip().lower() for k in keywords_str.split(",") if k.strip()] if keywords_str else []

        client = await self._get_client()
        url = "http://export.arxiv.org/api/query"
        params = {
            "search_query": query,
            "start": 0,
            "max_results": max_results * 3,  # fetch more for filtering
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"arXiv API error: {e}")
            return []

        # Parse Atom XML
        try:
            import feedparser
            feed = feedparser.parse(resp.text)
        except Exception as e:
            logger.error(f"arXiv parse error: {e}")
            return []

        items: list[RawContent] = []

        for entry in feed.entries[: max_results * 2]:
            title = re.sub(r"\s+", " ", entry.get("title", "")).strip()
            summary = entry.get("summary", "").strip()
            link = entry.get("link", "")
            arxiv_id = entry.get("id", "")

            # Keyword filter
            if keywords:
                combined = f"{title} {summary}".lower()
                if not any(kw in combined for kw in keywords):
                    continue

            authors = ", ".join(a.get("name", "") for a in entry.get("authors", [])[:3])

            text = f"Authors: {authors}\n\n{summary}"

            # Parse published date
            from datetime import datetime, timezone
            pub_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    pub_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                except Exception:
                    pass

            items.append(
                RawContent(
                    title=f"📄 {title}",
                    text=text,
                    url=link or arxiv_id,
                    published_at=pub_at,
                )
            )

            if len(items) >= max_results:
                break

        logger.info(f"arXiv: fetched {len(items)} items")
        return items