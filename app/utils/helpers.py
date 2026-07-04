from __future__ import annotations

import hashlib
import datetime as _dt
import html as html_mod
import json


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def h(text: str) -> str:
    return html_mod.escape(str(text))


def is_persian(text: str) -> bool:
    if not text:
        return False
    persian = sum(1 for c in text if '\u0600' <= c <= '\u06FF' or '\u0750' <= c <= '\u077F')
    return persian > len(text) * 0.15


def format_single_item_html(item) -> str:
    cat_labels = {
        "tutorial": "📚 آموزشی", "news": "📰 خبر", "tool": "🔧 ابزار",
        "prompt": "💬 پرامپت", "paper": "📄 مقاله", "other": "📌 متفرقه",
    }
    cat_emoji = {
        "tutorial": "📚", "news": "📰", "tool": "🔧",
        "prompt": "💬", "paper": "📄", "other": "📌",
    }

    emoji = cat_emoji.get(item.category or "other", "📌")
    cat_label = cat_labels.get(item.category or "other", "📌")
    stars = "⭐" * max(1, int(item.score // 2))

    lines = [
        f"{emoji} <b>{h(item.title)}</b>",
        "",
        f"📁 {cat_label} | {stars} ({item.score}/10)",
        "",
    ]

    if item.summary_en:
        lines.append("🇬🇧 <b>English:</b>")
        lines.append(h(item.summary_en))
        lines.append("")

    if item.summary_fa:
        lines.append("🇮🇷 <b>خلاصه فارسی:</b>")
        lines.append(h(item.summary_fa))
        lines.append("")

    if item.tags_json:
        try:
            tags = json.loads(item.tags_json)
            if tags:
                lines.append(" ".join(f"#{t}" for t in tags[:5]))
                lines.append("")
        except:
            pass

    if item.url:
        lines.append(f'🔗 <a href="{item.url}">مشاهده مطلب اصلی</a>')

    return "\n".join(lines)


def format_content_html(title, summary, url, category, score, hashtags) -> str:
    cat_labels = {
        "tutorial": "📚 آموزشی", "news": "📰 خبر", "tool": "🔧 ابزار",
        "prompt": "💬 پرامپت", "paper": "📄 مقاله", "other": "📌 متفرقه",
    }
    lines = [f"📰 <b>{h(title)}</b>"]
    if category:
        lines.append(f"📁 {cat_labels.get(category, category)}")
    stars = "⭐" * max(1, int(score // 2))
    lines.append(f"{stars} ({score}/10)\n")
    lines.append(h(summary))
    if url:
        lines.append(f'\n🔗 <a href="{url}">مشاهده</a>')
    if hashtags:
        lines.append(" ".join(f"#{t}" for t in hashtags[:5]))
    return "\n".join(lines)


def format_digest_html(items, title="خلاصه روزانه") -> str:
    cat_emoji = {
        "tutorial": "📚", "news": "📰", "tool": "🔧",
        "prompt": "💬", "paper": "📄", "other": "📌",
    }
    lines = [f"📋 <b>{h(title)}</b>", f"📅 {_dt.datetime.now().strftime('%Y-%m-%d')}", "─" * 20, ""]
    for i, item in enumerate(items, 1):
        emoji = cat_emoji.get(item.get("category", "other"), "📌")
        lines.append(f'{emoji} <b>{i}. {h(item.get("title", ""))}</b>')
        if item.get("summary"):
            lines.append(f"  {h(item['summary'][:200])}")
        if item.get("url"):
            lines.append(f'  🔗 <a href="{item["url"]}">لینک</a>')
        lines.append(f"  ⭐ {item.get("score", 0)}/10\n")
    return "\n".join(lines)
