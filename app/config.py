from __future__ import annotations

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    bot_token: str = ""
    super_admin_id: int = 0
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'curator.db'}"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    mimo_api_key: str = ""
    mimo_model: str = "MiMo-7B-RL"
    mimo_base_url: str = "https://api.mimo.xiaomi.com/v1/chat/completions"

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"

    telethon_api_id: str = ""
    telethon_api_hash: str = ""
    telethon_session_name: str = "curator_session"

    twitter_bearer_token: str = ""

    digest_hour: int = 9
    digest_minute: int = 0
    digest_max_items: int = 10

    log_level: str = "INFO"

    model_config = {"env_file": str(BASE_DIR / ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
