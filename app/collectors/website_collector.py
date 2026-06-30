from __future__ import annotations

from typing import Any

from bs4 import BeautifulSoup
from loguru import logger

from app.collectors.base import BaseCollector, RawContent


class WebsiteCollector(BaseCollector):
    """Scrapes content from a specific website using CSS selectors."""

    async def collect(self) -> list[RawContent]:
        url = self.config.get("url", "")
        selector = self.config.get("selector", "article")
        title_selector = self.config.get("title_selector", "h1, h2, h3")
        link_selector = self.config.get("link_selector", "a")

        if not url:
            return []

        client = await self._get_client()
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"Website fetch error for {url}: {e}")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        items: list[RawContent] = []

        elements = soup.select(selector)[:20]
        for el in elements:
            title_el = el.select_one(title_selector)
            title = title_el.get_text(strip=True) if title_el else ""
            text = el.get_text(separator=" ", strip=True)

            link_el = el.select_one(link_selector)
            href = link_el.get("href", "") if link_el else ""
            if href and not href.startswith("http"):
                from urllib.parse import urljoin
                href = urljoin(url, href)

            if title or text:
                items.append(
                    RawContent(
                        title=title or text[:100],
                        text=text,
                        url=href or url,
                    )
                )

        logger.info(f"Website [{url[:50]}]: fetched {len(items)} items")
        return items