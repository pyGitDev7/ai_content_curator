from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from app.collectors.base import BaseCollector, RawContent


class HackerNewsCollector(BaseCollector):
    """Collects top stories from Hacker News API with optional keyword filtering."""

    async def collect(self) -> list[RawContent]:
        max_items = self.config.get("max_items", 30)
        keywords_str = self.config.get("keywords", "")
        keywords = [k.strip().lower() for k in keywords_str.split(",") if k.strip()] if keywords_str else []

        client = await self._get_client()

        # Fetch top story IDs
        try:
            resp = await client.get("https://hacker-news.firebaseio.com/v0/topstories.json")
            resp.raise_for_status()
            story_ids = resp.json()[:100]  # Get more than needed for filtering
        except Exception as e:
            logger.error(f"Hacker News API error: {e}")
            return []

        items: list[RawContent] = []

        # Fetch stories in batches
        for batch_start in range(0, min(len(story_ids), 100), 10):
            batch = story_ids[batch_start : batch_start + 10]
            tasks = []
            for sid in batch:
                tasks.append(
                    client.get(f"https://hacker-news.firebaseio.com/v0/item/{sid}.json")
                )
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if isinstance(res, Exception):
                    continue
                try:
                    story = res.json()
                except Exception:
                    continue

                if not story or story.get("type") != "story":
                    continue

                title = story.get("title", "")
                url = story.get("url", "")
                score = story.get("score", 0)
                text = f"Score: {score} | Comments: {story.get('descendants', 0)}"
                if url:
                    text += f"\nURL: {url}"

                # Keyword filter
                if keywords:
                    lower_title = title.lower()
                    lower_url = url.lower()
                    if not any(kw in lower_title or kw in lower_url for kw in keywords):
                        continue

                items.append(RawContent(title=title, text=text, url=url or f"https://news.ycombinator.com/item?id={story['id']}"))

                if len(items) >= max_items:
                    break

            if len(items) >= max_items:
                break

        logger.info(f"Hacker News: fetched {len(items)} items")
        return items