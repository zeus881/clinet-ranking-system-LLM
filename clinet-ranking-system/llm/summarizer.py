from __future__ import annotations

import re


def summarize_text(text: str, model: str = "llama3:latest", max_chars: int = 350) -> str:
    """Extract a concise summary from text without any LLM call."""
    if not text:
        return ""

    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+|\n+", text)
        if len(s.strip()) >= 40
    ]

    summary = " ".join(sentences[:3])
    if summary:
        result = summary[:max_chars].rstrip(" ,;:")
        print(f"[SUMMARIZER] Extracted summary ({len(result)} chars)")
        return result

    fallback = text[:max_chars].rsplit(" ", 1)[0].strip()
    print(f"[SUMMARIZER] Fallback summary ({len(fallback)} chars)")
    return fallback
