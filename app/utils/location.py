"""Location string cleanup before MongoDB salon queries."""
from __future__ import annotations

import re

_JSON_JUNK = re.compile(r"[\[\]{}\"\\]+")
_MULTI_SPACE = re.compile(r"\s+")
_LOCATION_STOPWORDS = frozenset({
    "on", "at", "in", "near", "around", "for", "the", "a", "an", "to", "by", "with",
})
_DATE_FRAGMENT = re.compile(r"\bon\d{1,2}/\d{1,2}/\d{4}\b", re.IGNORECASE)


def sanitize_location(raw: str | None) -> str | None:
    """Return a clean city/area token suitable for Mongo regex search."""
    if not raw:
        return None

    text = str(raw).strip()
    if not text:
        return None

    text = _JSON_JUNK.sub("", text)
    text = _MULTI_SPACE.sub(" ", text).strip(" .;:,|")

    if "," in text:
        text = text.split(",")[0].strip()

    text = _DATE_FRAGMENT.sub("", text)
    text = re.split(r"\bon\s*\d{1,2}/", text, maxsplit=1, flags=re.IGNORECASE)[0]
    text = re.split(r"\s+at\s+", text, maxsplit=1, flags=re.IGNORECASE)[0].strip()

    words = re.findall(r"[A-Za-z]+", text)
    while words and words[-1].lower() in _LOCATION_STOPWORDS:
        words.pop()
    while words and words[0].lower() in _LOCATION_STOPWORDS:
        words.pop(0)
    if not words:
        return None

    text = " ".join(words[:4])
    if len(text) < 2:
        return None
    return text
