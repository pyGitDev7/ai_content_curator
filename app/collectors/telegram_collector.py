from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.collectors.base import BaseCollector, RawContent
from app.config import settings


class TelegramCollector(BaseCollector):
    """Collects messages from Telegram channels using Telethon."""

    async def collect(self) -> list[RawContent]:
        channel = self.config.get("channel", "")
        if not channel:
            return []

        if not settings.telethon_api_id or not settings.telethon_api_hash:
            logger.debug("Telethon not configured; skipping Telegram collector")
            return []

        try:
            from telethon import TelegramClient
            from telethon.tl.types import Message

            client = TelegramClient(
                settings.telethon_session_name,
                int(settings.telethon_api_id),
                settings.telethon_api_hash,
            )
            await client.start()

            items: list[RawContent] = []
            channel_entity = await client.get_entity(channel)

            async for message in client.iter_messages(channel_entity, limit=20):
                if not message.text:
                    continue
                pub_at = message.date
                if pub_at and not pub_at.tzinfo:
                    pub_at = pub_at.replace(tzinfo=timezone.utc)

                items.append(
                    RawContent(
                        title=message.text[:100].split("\n")[0],
                        text=message.text,
                        url=f"https://t.me/{channel}/{message.id}",
                        published_at=pub_at,
                    )
                )

            await client.disconnect()
            logger.info(f"Telegram [{channel}]: fetched {len(items)} items")
            return items

        except Exception as e:
            logger.error(f"Telegram collector error for {channel}: {e}")
            return []