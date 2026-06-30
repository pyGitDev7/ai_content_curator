from app.collectors.base import BaseCollector
from app.collectors.rss_collector import RSSCollector
from app.collectors.telegram_collector import TelegramCollector
from app.collectors.twitter_collector import TwitterCollector
from app.collectors.reddit_collector import RedditCollector
from app.collectors.website_collector import WebsiteCollector
from app.collectors.github_collector import GitHubCollector
from app.collectors.hackernews_collector import HackerNewsCollector
from app.collectors.arxiv_collector import ArxivCollector

COLLECTOR_MAP: dict[str, type[BaseCollector]] = {
    "rss": RSSCollector,
    "telegram": TelegramCollector,
    "twitter": TwitterCollector,
    "reddit": RedditCollector,
    "website": WebsiteCollector,
    "github": GitHubCollector,
    "hackernews": HackerNewsCollector,
    "arxiv": ArxivCollector,
}

__all__ = [
    "BaseCollector",
    "RSSCollector",
    "TelegramCollector",
    "TwitterCollector",
    "RedditCollector",
    "WebsiteCollector",
    "GitHubCollector",
    "HackerNewsCollector",
    "ArxivCollector",
    "COLLECTOR_MAP",
]