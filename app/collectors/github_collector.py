from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from loguru import logger

from app.collectors.base import BaseCollector, RawContent


class GitHubCollector(BaseCollector):
    """Scrapes GitHub Trending repositories."""

    async def collect(self) -> list[RawContent]:
        language = self.config.get("language", "")
        since = self.config.get("since", "daily")

        url = "https://github.com/trending"
        if language:
            url += f"/{language}"
        url += f"?since={since}"

        client = await self._get_client()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"GitHub trending fetch error: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items: list[RawContent] = []

        for row in soup.select("article.Box-row")[:25]:
            # Repo name
            h2 = row.select_one("h2 a")
            if not h2:
                continue
            repo_path = h2.get("href", "").strip()
            repo_name = repo_path.strip("/")
            repo_url = f"https://github.com{repo_path}"

            # Description
            desc_el = row.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            # Stars today
            stars_el = row.select_one("span.d-inline-block.float-sm-right")
            stars_today = stars_el.get_text(strip=True) if stars_el else ""

            # Language
            lang_el = row.select_one("span[itemprop='programmingLanguage']")
            lang = lang_el.get_text(strip=True) if lang_el else ""

            title = f"🔥 {repo_name}"
            text = description
            if lang:
                text += f"\nLanguage: {lang}"
            if stars_today:
                text += f"\nStars today: {stars_today}"

            items.append(
                RawContent(
                    title=title,
                    text=text,
                    url=repo_url,
                )
            )

        logger.info(f"GitHub Trending [{language or 'all'}]: fetched {len(items)} items")
        return items