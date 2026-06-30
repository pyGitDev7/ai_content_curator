from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.collectors.base import BaseCollector, RawContent


class RedditCollector(BaseCollector):
    """Collects hot posts from subreddits using the public JSON API."""

    async def collect(self) -> list[RawContent]:
        subreddit = self.config.get("subreddit", "")
        if not subreddit:
            return []

        client = await self._get_client()
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit=20"
        headers = {"User-Agent": "AI-Content-Curator/1.0 (Educational Bot)"}

        try:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.error(f"Reddit fetch error for r/{subreddit}: {e}")
            return []

        items: list[RawContent] = []
        for child in data.get("data", {}).get("children", []):
            post = child.get("data", {})
            title = post.get("title", "")
            selftext = post.get("selftext", "")
            link = f"https://www.reddit.com{post.get('permalink', '')}"
            created = post.get("created_utc")

            pub_at = None
            if created:
                pub_at = datetime.fromtimestamp(created, tz=timezone.utc)

            # Combine title and selftext
            full_text = title
            if selftext:
                full_text += f"\n\n{selftext}"

            items.append(
                RawContent(
                    title=title,
                    text=full_text,
                    url=link,
                    published_at=pub_at,
                )
            )

        logger.info(f"Reddit [r/{subreddit}]: fetched {len(items)} items")
        return items