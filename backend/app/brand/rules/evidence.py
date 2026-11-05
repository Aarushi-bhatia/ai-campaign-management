"""Checks that a quote the model gave really appears in the brand's documents."""

import re

_MARKUP = re.compile(r"[*_`>#|]+")
_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")
_WORD = re.compile(r"[a-z0-9]+")


def normalize(text: str) -> str:
    """Ignores case, markdown marks, curly quotes and spacing when matching a quote to a document."""
    text = _MARKUP.sub(" ", text.translate(_QUOTES).lower())
    return " ".join(text.split()).strip(" .")


class Document:
    def __init__(self, text: str) -> None:
        self._normalized = normalize(text)

    def contains(self, quote: str) -> bool:
        return bool(quote.strip()) and normalize(quote) in self._normalized

    def proves(self, quote: str, value: str = "") -> bool:
        """The quote is in the document and says more than one word, and more than the claimed value alone: a
        bare "Maren" is in the document, but doesn't show that Maren owns it ("Owner: Maren" does)."""
        words = set(_WORD.findall(normalize(quote)))
        return len(words) >= 2 and bool(words - set(_WORD.findall(normalize(value)))) and self.contains(quote)


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
