from __future__ import annotations

import json
from typing import Any

import httpx
from loguru import logger

from app.config import settings

SYSTEM_PROMPT = """You are an expert AI content curator for a Persian-language Telegram channel.

Analyze the given content and return a JSON object with EXACTLY these fields:
{
  "summary_fa": "A 2-3 sentence summary written in colloquial Persian (خودمانی). Use Persian equivalents for tech terms where they exist naturally (e.g. پرامپت‌نویسی for prompt engineering, مدل زبانی بزرگ for LLM). If no good Persian equivalent exists, keep the English term.",
  "summary_en": "A 2-3 sentence summary in English, concise and engaging",
  "category": "One of: tutorial, news, tool, prompt, paper, other",
  "score": 8.5,
  "hashtags": ["AI", "ChatGPT"]
}

Rules:
- summary_fa: colloquial Persian, NOT formal/bookish
- summary_en: concise English
- score: 0-10, only 8+ for excellent content
- hashtags: 3-5 without #
- Return ONLY valid JSON"""

TRANSLATE_TO_FA = """تو یه مترجم حرفه‌ای فارسی هستی. متن زیر رو به فارسی ترجمه کن.

قوانین مهم:
- فارسی روان و خودمانی بنویس، نه کتابی و رسمی
- اصطلاحات فنی رو با معادل فارسی رایجشون بنویس
- اگه معادل فارسی خوبی ندارن، همون انگلیسی رو بنویس ولی توی پرانتز توضیح بده
- مثال: "پرامپت‌نویسی (prompt engineering)"، "مدل زبانی بزرگ (LLM)"، "یادگیری عمیق (deep learning)"
- لحن طبیعی باشه، مثل متن اصلی فارسی نه ترجمه ماشینی
- فقط ترجمه رو برگردون

متن اصلی:"""

TRANSLATE_TO_EN = """You are a professional translator. Translate the following text to fluent, natural English.

Rules:
- Natural English phrasing, not literal translation
- Technical terms use standard English equivalents
- Keep proper nouns as-is
- Must read like native English content
- Return ONLY the translation

Text to translate:"""


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

    async def _call_openai(self, content: str, system: str = SYSTEM_PROMPT, json_mode: bool = True):
        if not settings.openai_api_key:
            return None
        client = await self._get_client()
        try:
            body = {
                "model": settings.openai_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.3,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json=body,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            if json_mode:
                return json.loads(text)
            return text.strip()
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return None

    async def _call_mimo(self, content: str, system: str = SYSTEM_PROMPT, json_mode: bool = True):
        if not settings.mimo_api_key:
            return None
        client = await self._get_client()
        try:
            resp = await client.post(
                settings.mimo_base_url,
                headers={"Authorization": f"Bearer {settings.mimo_api_key}", "Content-Type": "application/json"},
                json={
                    "model": settings.mimo_model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": content},
                    ],
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0].strip()
            elif "```" in text:
                text = text.split("```")[1].split("```")[0].strip()
            if json_mode:
                return json.loads(text)
            return text.strip()
        except Exception as e:
            logger.error(f"MiMo error: {e}")
            return None

    async def _call_deepseek(self, content: str, system: str = SYSTEM_PROMPT, json_mode: bool = True):
        if not settings.deepseek_api_key:
            return None
        client = await self._get_client()
        try:
            body = {
                "model": settings.deepseek_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": content},
                ],
                "temperature": 0.3,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            resp = await client.post(
                "https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json=body,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            if json_mode:
                return json.loads(text)
            return text.strip()
        except Exception as e:
            logger.error(f"DeepSeek error: {e}")
            return None

    async def _call_any(self, content, system=SYSTEM_PROMPT, json_mode=True):
        for func in [self._call_openai, self._call_mimo, self._call_deepseek]:
            result = await func(content, system=system, json_mode=json_mode)
            if result:
                return result
        return None

    async def analyze_content(self, title: str, text: str, url: str | None = None) -> dict[str, Any]:
        payload = f"Title: {title}\n\nContent:\n{text[:4000]}"
        if url:
            payload += f"\n\nURL: {url}"
        result = await self._call_any(payload)
        if result and isinstance(result, dict):
            return self._normalize(result)
        return {
            "summary_fa": f"مطلب جدید: {title}",
            "summary_en": f"New content: {title}",
            "category": "other", "score": 5.0, "hashtags": ["AI"],
        }

    async def translate_to_farsi(self, text: str) -> str:
        prompt = f"{TRANSLATE_TO_FA}\n\n{text[:3500]}"
        result = await self._call_any(prompt, system="You are a professional Persian translator.", json_mode=False)
        if result and isinstance(result, str):
            return result
        return "[ترجمه ناموفق. دوباره امتحان کن.]"

    async def translate_to_english(self, text: str) -> str:
        prompt = f"{TRANSLATE_TO_EN}\n\n{text[:3500]}"
        result = await self._call_any(prompt, system="You are a professional English translator.", json_mode=False)
        if result and isinstance(result, str):
            return result
        return "[Translation failed. Try again.]"

    @staticmethod
    def _normalize(result: dict[str, Any]) -> dict[str, Any]:
        return {
            "summary_fa": str(result.get("summary_fa", "خلاصه‌ای نیست")),
            "summary_en": str(result.get("summary_en", result.get("summary", ""))),
            "category": str(result.get("category", "other")).lower(),
            "score": max(0.0, min(10.0, float(result.get("score", 5.0)))),
            "hashtags": list(result.get("hashtags", ["AI"]))[:5],
        }


ai_service = AIService()
