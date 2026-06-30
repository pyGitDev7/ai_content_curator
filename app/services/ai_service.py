from __future__ import annotations

import json
from typing import Any

import httpx
from loguru import logger

from app.config import settings

SYSTEM_PROMPT = """You are an expert AI content curator for a Persian-language Telegram channel about:
- Free AI tools and resources
- Prompt engineering
- AI tips and tricks
- Useful Telegram bots and websites

Analyze the given content and return a JSON object with EXACTLY these fields:
{
  "summary_fa": "A 2-3 sentence summary in Persian (Farsi) that is engaging and informative for the channel audience",
  "category": "One of: tutorial, news, tool, prompt, paper, other",
  "score": 8.5,
  "hashtags": ["AI", "ChatGPT", "PromptEngineering"]
}

Rules:
- summary_fa must be in Farsi, attractive and concise (max 3 sentences)
- score is 0-10, be strict: only give 8+ for truly excellent content
- hashtags: 3-5 relevant tags without # symbol
- category: pick the BEST single match
- Return ONLY valid JSON, no explanation"""


class AIService:

    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _call_openai(self, content: str) -> dict[str, Any] | None:
        if not settings.openai_api_key:
            return None
        client = await self._get_client()
        try:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.openai_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": content},
                    ],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return json.loads(text)
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return None

    async def _call_mimo(self, content: str) -> dict[str, Any] | None:
        if not settings.mimo_api_key:
            return None
        client = await self._get_client()
        try:
            resp = await client.post(
                settings.mimo_base_url,
                headers={
                    "Authorization": f"Bearer {settings.mimo_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.mimo_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": content},
                    ],
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            return json.loads(text)
        except Exception as e:
            logger.error(f"MiMo API error: {e}")
            return None

    async def _call_deepseek(self, content: str) -> dict[str, Any] | None:
        if not settings.deepseek_api_key:
            return None
        client = await self._get_client()
        try:
            resp = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json={
                    "model": settings.deepseek_model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": content},
                    ],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return json.loads(text)
        except Exception as e:
            logger.error(f"DeepSeek API error: {e}")
            return None

    async def analyze_content(
        self, title: str, text: str, url: str | None = None
    ) -> dict[str, Any]:
        payload = f"Title: {title}\n\nContent:\n{text[:4000]}"
        if url:
            payload += f"\n\nURL: {url}"

        result = await self._call_openai(payload)
        if result:
            return self._normalize(result)

        result = await self._call_mimo(payload)
        if result:
            return self._normalize(result)

        result = await self._call_deepseek(payload)
        if result:
            return self._normalize(result)

        logger.warning("All AI providers failed; using fallback analysis")
        return {
            "summary_fa": f"مطلب جدید: {title}",
            "category": "other",
            "score": 5.0,
            "hashtags": ["AI"],
        }

    async def translate_to_farsi(self, text: str) -> str:
        prompt = f"Translate the following text to Persian (Farsi). Return ONLY the translation:\n\n{text[:3000]}"
        for provider_func in [self._call_openai, self._call_mimo, self._call_deepseek]:
            try:
                result = await provider_func(prompt)
                if result and isinstance(result, dict):
                    return str(result.get("summary_fa", text))
            except Exception:
                continue
        return text

    @staticmethod
    def _normalize(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary_fa": str(result.get("summary_fa", "خلاصه‌ای موجود نیست")),
            "category": str(result.get("category", "other")).lower(),
            "score": max(0.0, min(10.0, float(result.get("score", 5.0)))),
            "hashtags": list(result.get("hashtags", ["AI"]))[:5],
        }


ai_service = AIService()