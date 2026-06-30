from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx
from loguru import logger


@dataclass
class RawContent:
    """Represents a single piece of raw content fetched from a source."""
    title: str
    text: str
    url: str | None = None
    html: str | None = None
    published_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class BaseCollector(abc.ABC):
    """Abstract base class for all content collectors."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": "AI-Content-Curator/1.0"},
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @abc.abstractmethod
    async def collect(self) -> list[RawContent]:
        """Fetch and return raw content items from this source."""
        ...

    async def safe_collect(self) -> list[RawContent]:
        """Wrapper that catches all exceptions and logs them."""
        try:
            return await self.collect()
        except Exception as e:
            logger.error(f"Collector {self.__class__.__name__} error: {e}")
            return []
        finally:
            await self.close()