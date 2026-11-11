"""Small parsing helpers shared by the guard and the LLM backends."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json(text: Any) -> Optional[dict]:
    """Best-effort extraction of a JSON object from model output.

    Handles bare JSON, JSON inside a Markdown fence, and JSON surrounded by
    prose. Returns ``None`` when nothing parseable is found.
    """
    if isinstance(text, dict):
        return text
    if not isinstance(text, str):
        return None

    text = text.strip()
    if not text:
        return None

    candidates = [text]
    fenced = _FENCE_RE.search(text)
    if fenced:
        candidates.insert(0, fenced.group(1))

    # Widest balanced-brace span as a last resort.
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
