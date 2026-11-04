"""Checks that a quote the model gave really appears in the brand's documents."""

import re

_MARKUP = re.compile(r"[*_`>#|]+")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def normalize(text: str) -> str:
    """Ignores case, markdown marks, curly quotes and spacing when matching a quote to a document."""
    text = _MARKUP.sub(" ", text.translate(_QUOTES).lower())
    return " ".join(text.split()).strip(" .")


class Document:
    def __init__(self, text: str) -> None:
        self._normalized = normalize(text)

    def contains(self, quote: str) -> bool:
        return bool(quote.strip()) and normalize(quote) in self._normalized


def sentences(text: str) -> list[str]:
    return [sentence.strip() for sentence in _SENTENCE_END.split(text) if sentence.strip()]


def sentence_with_all(text: str, names: list[str]) -> str | None:
    """The first sentence or line of `text` that names every one of `names`, if there is one."""
    wanted = [normalize(name) for name in names]
    for sentence in sentences(text):
        normalized = normalize(sentence)
        if all(_has_word(normalized, name) for name in wanted):
            return sentence.strip()
    return None


def _has_word(haystack: str, needle: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", haystack) is not None
