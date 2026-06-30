from __future__ import annotations

import re
from bs4 import BeautifulSoup


def strip_html(html: str) -> str:
    """Remove HTML tags and return clean text."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    # Remove script and style elements
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return text


def normalize_text(text: str) -> str:
    """Clean and normalize text content."""
    if not text:
        return ""
    # Remove excessive whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Remove zero-width characters
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)
    # Remove control characters (except newlines)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Normalize newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_content(title: str, raw_text: str, html: str | None = None) -> tuple[str, str]:
    """Clean title and body text. Returns (title, body)."""
    clean_title = normalize_text(strip_html(title)) if "<" in title else normalize_text(title)

    if html:
        body = normalize_text(strip_html(html))
    else:
        body = normalize_text(strip_html(raw_text)) if raw_text and "<" in raw_text else normalize_text(raw_text or "")

    return clean_title, body