from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import date
from typing import Any

# Zero-width and control characters are removed before comparison so that two
# visually identical excerpts cannot bypass the substring check.
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)
_WHITESPACE = re.compile(r"\s+")
_KOREAN_OR_WORD = re.compile(r"[가-힣]+|[a-z0-9]+", re.IGNORECASE)
_PERCENT = re.compile(r"(?P<num>\d+(?:\.\d+)?)\s*(?:%|퍼센트|프로센트)")
_FRACTION = re.compile(r"100\s*분의\s*(?P<num>\d+(?:\.\d+)?)")


def normalize_nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def normalize_text(value: str) -> str:
    """NFC normalize, strip zero-width characters, collapse whitespace."""
    value = normalize_nfc(value or "").translate(_ZERO_WIDTH)
    value = value.replace("\u00a0", " ")
    return _WHITESPACE.sub(" ", value).strip()


def canonical_json(value: Any) -> str:
    """Canonical JSON used by every hash in the project.

    - NFC normalization for all strings
    - sorted object keys
    - compact separators
    - non-ASCII preserved (Korean is stored as UTF-8, not escaped)
    """

    def _walk(item: Any) -> Any:
        if isinstance(item, str):
            return normalize_nfc(item)
        if isinstance(item, dict):
            return {normalize_nfc(str(key)): _walk(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [_walk(val) for val in item]
        if isinstance(item, float):
            # Avoid 0.55000000000000004 style drift in hashes.
            return round(item, 6)
        return item

    return json.dumps(_walk(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def words(value: str) -> list[str]:
    return [match.group(0).lower() for match in _KOREAN_OR_WORD.finditer(normalize_text(value))]


def korean_bigrams(token: str) -> list[str]:
    if not token:
        return []
    if re.fullmatch(r"[가-힣]+", token):
        if len(token) < 2:
            return []
        return [token[index : index + 2] for index in range(len(token) - 1)]
    return []


def normalize_policy_value(value: str | None) -> str | None:
    """Normalize common Korean numeric expressions for conflict detection.

    Only tagged corpus metadata is compared. This is deliberately not a general
    semantic contradiction detector (documented limitation).
    """
    if value is None:
        return None
    text = normalize_text(value).lower().replace(" ", "")
    if not text:
        return None
    match = _PERCENT.search(text)
    if match:
        return f"percent:{round(float(match.group('num')), 6)}"
    match = _FRACTION.search(text)
    if match:
        return f"percent:{round(float(match.group('num')), 6)}"
    return f"text:{text}"


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def is_https_url(value: str) -> bool:
    return normalize_text(value).startswith("https://")
