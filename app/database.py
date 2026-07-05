from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings, BASE_DIR

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Base(DeclarativeBase):
    pass


engine: AsyncEngine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    from app.models.models import (
        User, Source, Hashtag, Keyword, ContentItem,
        DeliveredLog, Setting, AdminLog, Bookmark,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Add missing columns for upgrades
        for col_def in [
            "ALTER TABLE content_items ADD COLUMN collection_batch INTEGER DEFAULT 0",
            "ALTER TABLE content_items ADD COLUMN translated_fa TEXT",
        ]:
            try:
                await conn.execute(text(col_def))
            except Exception:
                pass


async def seed_defaults() -> None:
    from app.models.models import User, Source
    from sqlalchemy import select

    async with async_session_factory() as session:
        if settings.super_admin_id:
            existing = await session.execute(select(User).where(User.telegram_id == settings.super_admin_id))
            if not existing.scalar_one_or_none():
                session.add(User(telegram_id=settings.super_admin_id, username="superadmin", is_super_admin=True))

        default_sources = [
            # English RSS
            {"name": "OpenAI Blog", "type": "rss", "config_json": '{"url": "https://openai.com/blog/rss"}'},
            {"name": "DeepMind Blog", "type": "rss", "config_json": '{"url": "https://deepmind.com/blog/feed/basic/"}'},
            {"name": "Google AI Blog", "type": "rss", "config_json": '{"url": "https://blog.google/technology/ai/rss/"}'},
            {"name": "VentureBeat AI", "type": "rss", "config_json": '{"url": "https://venturebeat.com/category/ai/feed/"}'},
            {"name": "TechCrunch AI", "type": "rss", "config_json": '{"url": "https://techcrunch.com/category/artificial-intelligence/feed/"}'},
            {"name": "HuggingFace Blog", "type": "rss", "config_json": '{"url": "https://huggingface.co/blog/feed.xml"}'},
            {"name": "The Verge AI", "type": "rss", "config_json": '{"url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"}'},
            {"name": "Ars Technica", "type": "rss", "config_json": '{"url": "https://feeds.arstechnica.com/arstechnica/technology-lab"}'},
            {"name": "Wired AI", "type": "rss", "config_json": '{"url": "https://www.wired.com/feed/tag/ai/latest/rss"}'},
            {"name": "MIT Tech Review AI", "type": "rss", "config_json": '{"url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"}'},
            {"name": "Towards Data Science", "type": "rss", "config_json": '{"url": "https://towardsdatascience.com/feed"}'},
            {"name": "The Batch (deeplearning.ai)", "type": "rss", "config_json": '{"url": "https://www.deeplearning.ai/the-batch/feed/"}'},
            {"name": "NVIDIA AI Blog", "type": "rss", "config_json": '{"url": "https://blogs.nvidia.com/feed/"}'},

            # Persian RSS
            {"name": "زومیت", "type": "rss", "config_json": '{"url": "https://www.zoomit.ir/feed/"}'},
            {"name": "دیجیاتو", "type": "rss", "config_json": '{"url": "https://digiato.com/feed"}'},
            {"name": "گجت‌نیوز", "type": "rss", "config_json": '{"url": "https://gadgetnews.net/feed/"}'},
            {"name": "شنبه‌پرس", "type": "rss", "config_json": '{"url": "https://shabanepress.com/feed/"}'},
            {"name": "نردبان", "type": "rss", "config_json": '{"url": "https://nerdbaan.ir/feed/"}'},
            {"name": "فرادرس", "type": "rss", "config_json": '{"url": "https://faradars.org/blog/feed"}'},
            {"name": "آی‌تی‌رسان", "type": "rss", "config_json": '{"url": "https://itresan.com/feed"}'},
            {"name": "پیوست", "type": "rss", "config_json": '{"url": "https://peivast.com/feed/"}'},
            {"name": "کوئرا مگ", "type": "rss", "config_json": '{"url": "https://quera.org/blog/feed/"}'},
            {"name": "راکت", "type": "rss", "config_json": '{"url": "https://roocket.ir/feed"}'},
            {"name": "دیجی‌کالا مگ", "type": "rss", "config_json": '{"url": "https://www.digikalamag.com/feed/"}'},
            {"name": "ویرگول", "type": "rss", "config_json": '{"url": "https://virgool.io/feed"}'},
            {"name": "چطور", "type": "rss", "config_json": '{"url": "https://chetor.com/feed/"}'},
            {"name": "کلیک", "type": "rss", "config_json": '{"url": "https://click.ir/feed"}'},
            {"name": "لرن‌فا", "type": "rss", "config_json": '{"url": "https://learnfa.ir/feed"}'},
            {"name": "مکتب‌خونه", "type": "rss", "config_json": '{"url": "https://maktabkhooneh.org/blog/feed"}'},
            {"name": "پونیشا", "type": "rss", "config_json": '{"url": "https://blog.ponisha.ir/feed"}'},
            {"name": "جاب‌ویژن", "type": "rss", "config_json": '{"url": "https://jobvision.ir/blog/feed"}'},
            {"name": "تک‌لایف", "type": "rss", "config_json": '{"url": "https://techlife.ir/feed"}'},

            # Telegram
            {"name": "AIinsights", "type": "telegram", "config_json": '{"channel": "AIinsights"}'},
            {"name": "MachineLearning", "type": "telegram", "config_json": '{"channel": "MachineLearning"}'},
            {"name": "ChatGPT_News", "type": "telegram", "config_json": '{"channel": "ChatGPT_News"}'},
            {"name": "OpenAI", "type": "telegram", "config_json": '{"channel": "OpenAI"}'},

            # Twitter
            {"name": "OpenAI Twitter", "type": "twitter", "config_json": '{"username": "OpenAI"}'},
            {"name": "GoogleAI Twitter", "type": "twitter", "config_json": '{"username": "GoogleAI"}'},
            {"name": "AndrewYNg", "type": "twitter", "config_json": '{"username": "AndrewYNg"}'},
            {"name": "HuggingFace", "type": "twitter", "config_json": '{"username": "huggingface"}'},
            {"name": "AnthropicAI", "type": "twitter", "config_json": '{"username": "AnthropicAI"}'},

            # Reddit
            {"name": "r/MachineLearning", "type": "reddit", "config_json": '{"subreddit": "MachineLearning"}'},
            {"name": "r/LocalLLaMA", "type": "reddit", "config_json": '{"subreddit": "LocalLLaMA"}'},
            {"name": "r/ChatGPT", "type": "reddit", "config_json": '{"subreddit": "ChatGPT"}'},

            # GitHub
            {"name": "GitHub Python Trending", "type": "github", "config_json": '{"language": "python", "since": "daily"}'},

            # Hacker News
            {"name": "Hacker News AI", "type": "hackernews", "config_json": '{"max_items": 30, "keywords": "AI,LLM,GPT,machine learning,OpenAI"}'},

            # arXiv
            {"name": "arXiv AI Papers", "type": "arxiv", "config_json": '{"query": "cat:cs.AI OR cat:cs.CL OR cat:cs.LG", "max_results": 20, "keywords": "LLM,prompt,transformer,GPT"}'},
        ]

        for src_data in default_sources:
            existing = await session.execute(
                select(Source).where(Source.type == src_data["type"], Source.name == src_data["name"])
            )
            if not existing.scalar_one_or_none():
                session.add(Source(**src_data, is_active=True))
        await session.commit()
