from __future__ import annotations

import datetime as _dt
import hashlib
from typing import Any


def content_hash(text: str) -> str:
    """Produce a SHA-256 hex digest of *text* for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def now_utc() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def truncate(text: str, length: int = 4000) -> str:
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."


def safe_json_loads(raw: str | None, default: Any = None) -> Any:
    if not raw:
        return default if default is not None else {}
    import json
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return default if default is not None else {}


def escape_md(text: str) -> str:
    """Escape MarkdownV2 special characters."""
    special = r"_*[]()~`>#+-=|{}.!"
    out: list[str] = []
    for ch in text:
        if ch in special:
            out.append(f"\\{ch}")
        else:
            out.append(ch)
    return "".join(out)


def format_content_message(
    title: str,
    summary: str,
    url: str | None,
    category: str | None,
    score: float,
    hashtags: list[str] | None,
) -> str:
    """Format a beautiful MarkdownV2 message for the Telegram channel."""
    lines: list[str] = []

    # Title
    esc_title = escape_md(title)
    lines.append(f"📰 *{esc_title}*")
    lines.append("")

    # Category & Score
    if category:
        cat_label = {
            "tutorial": "📚 آموزشی",
            "news": "📰 خبر",
            "tool": "🔧 ابزار",
            "prompt": "💬 پرامپت",
            "paper": "📄 مقاله علمی",
            "other": "📌 متفرقه",
        }.get(category.lower(), f"📁 {category}")
        lines.append(f"دسته‌بندی: {cat_label}")
    lines.append(f"امتیاز: {'⭐' * int(score // 2)} $${escape_md(str(score))}/10$$")
    lines.append("")

    # Summary
    esc_summary = escape_md(summary)
    lines.append(esc_summary)
    lines.append("")

    # URL
    if url:
        lines.append(f"🔗 [مشاهده مطلب]({url})")
        lines.append("")

    # Hashtags
    if hashtags:
        tags = " ".join(f"#{t}" for t in hashtags[:5])
        lines.append(escape_md(tags))

    return "\n".join(lines)


def format_digest_message(items: list[dict[str, Any]], title: str = "خلاصه روزانه") -> str:
    """Format a digest message containing multiple items."""
    lines: list[str] = []
    lines.append(f"📋 *{escape_md(title)}*")
    lines.append(f"📅 {escape_md(_dt.datetime.now().strftime('%Y-%m-%d'))}")
    lines.append("─" * 20)
    lines.append("")

    for i, item in enumerate(items, 1):
        esc_title = escape_md(item.get("title", ""))
        score = item.get("score", 0)
        category = item.get("category", "other")
        cat_emoji = {
            "tutorial": "📚", "news": "📰", "tool": "🔧",
            "prompt": "💬", "paper": "📄", "other": "📌",
        }.get(category, "📌")

        lines.append(f"{cat_emoji} *{i}\\. {esc_title}*")
        if item.get("summary"):
            esc_sum = escape_md(item["summary"][:200])
            lines.append(f"   {esc_sum}")
        if item.get("url"):
            lines.append(f"   🔗 [لینک]({item['url']})")
        lines.append(f"   ⭐ امتیاز: {escape_md(str(score))}/10")
        lines.append("")

    return "\n".join(lines)