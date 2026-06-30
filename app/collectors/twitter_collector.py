from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from loguru import logger

from app.collectors.base import BaseCollector, RawContent
from app.config import settings


class TwitterCollector(BaseCollector):
    """Collects tweets from Twitter/X using Tweepy (API v2)."""

    async def collect(self) -> list[RawContent]:
        username = self.config.get("username", "")
        if not username:
            return []

        if not settings.twitter_bearer_token:
            logger.debug("Twitter API not configured; skipping")
            return []

        try:
            import tweepy

            client = tweepy.Client(bearer_token=settings.twitter_bearer_token)

            # Get user ID by username
            user = client.get_user(username=username)
            if not user.data:
                logger.warning(f"Twitter user @{username} not found")
                return []

            user_id = user.data.id
            tweets = client.get_users_tweets(
                id=user_id,
                max_results=20,
                tweet_fields=["created_at", "text"],
                exclude=["retweets", "replies"],
            )

            items: list[RawContent] = []
            if tweets.data:
                for tweet in tweets.data:
                    pub_at = tweet.created_at
                    if pub_at and not pub_at.tzinfo:
                        pub_at = pub_at.replace(tzinfo=timezone.utc)

                    items.append(
                        RawContent(
                            title=f"@{username}: {tweet.text[:80]}",
                            text=tweet.text,
                            url=f"https://x.com/{username}/status/{tweet.id}",
                            published_at=pub_at,
                        )
                    )

            logger.info(f"Twitter [@{username}]: fetched {len(items)} items")
            return items

        except Exception as e:
            logger.error(f"Twitter collector error for @{username}: {e}")
            return []