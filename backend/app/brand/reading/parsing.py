"""Step 1 of reading a brand: facts about each document that need no AI."""

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import yaml

SECTION_MAX_TOKENS = 800
SECTION_MIN_TOKENS = 60
TOP_LINES_SCANNED = 15

_ATX_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_SETEXT_UNDERLINE = re.compile(r"^(=+|-+)\s*$")
_LABEL_LINE = re.compile(r"^\s*\**\s*([A-Za-z][A-Za-z]*(?: [A-Za-z]+){0,2})\s*\**\s*:\s*\**\s*(.{1,120}?)\s*$")
_NAME_HINTS = {
    "final": r"final",
    "old": r"old",
    "draft": r"draft|wip",
    "current": r"current|latest",
    "internal": r"internal|confidential",
    "archive": r"archived?",
    "deprecated": r"deprecated|legacy|retired",
}
_YEAR = re.compile(r"(?<!\d)(19|20)\d{2}(?!\d)")
_VERSION = re.compile(r"(?<![a-z])v\d+(?:\.\d+)?(?![a-z])", re.IGNORECASE)


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def decode(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line: int


@dataclass(frozen=True)
class SectionDraft:
    heading: str
    text: str
    tokens: int


def basics(path: str, text: str) -> dict[str, Any]:
    """Everything step 1 records about a document. These are hints for the AI, never final answers."""
    frontmatter, body = split_frontmatter(text)
    return {
        "folder": str(PurePosixPath(path).parent) if "/" in path else "",
        "tokens": estimate_tokens(text),
        "frontmatter": frontmatter,
        "top_labels": top_labels(body),
        "headings": [{"level": h.level, "text": h.text} for h in headings(body)],
        "name_hints": name_hints(path),
    }


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Reads a YAML block at the very top of the file, if there is one."""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        return {}, text
    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        return {}, text
    if not isinstance(data, dict):
        return {}, text
    return {str(key): str(value) for key, value in data.items()}, text[match.end() :]


def top_labels(body: str) -> dict[str, str]:
    """`Label: value` lines near the top, such as "Owner: Noor" or "**Date:** October 20"."""
    labels: dict[str, str] = {}
    for line in body.splitlines()[:TOP_LINES_SCANNED]:
        match = _LABEL_LINE.match(line)
        if match and not line.lstrip().startswith(("#", "|", "-", ">")):
            labels.setdefault(match.group(1).strip().lower(), match.group(2).strip("* "))
    return labels


def name_hints(path: str) -> list[str]:
    name = PurePosixPath(path).as_posix().lower()
    words = re.split(r"[^a-z0-9]+", name)
    hints = [hint for hint, pattern in _NAME_HINTS.items() if any(re.fullmatch(pattern, word) for word in words)]
    hints += [f"year {match.group(0)}" for match in _YEAR.finditer(name)]
    hints += [f"version {match.group(0).lower()}" for match in _VERSION.finditer(name)]
    return hints


def headings(body: str) -> list[Heading]:
    found: list[Heading] = []
    lines = body.splitlines()
    in_code = False
    for index, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        atx = _ATX_HEADING.match(line)
        if atx:
            found.append(Heading(len(atx.group(1)), atx.group(2).strip(), index))
        elif (
            index > 0
            and _SETEXT_UNDERLINE.match(line)
            and lines[index - 1].strip()
            and not _ATX_HEADING.match(lines[index - 1])
            and (index < 2 or not lines[index - 2].strip())
        ):
            level = 1 if line.lstrip().startswith("=") else 2
            found.append(Heading(level, lines[index - 1].strip(), index - 1))
    return found


def split_sections(text: str) -> list[SectionDraft]:
    """Cuts a document at its headings, then evens out the sizes.

    Very short pieces join the piece after them; long pieces split at blank lines.
    """
    _, body = split_frontmatter(text)
    lines = body.splitlines()
    starts = [(h.line, h) for h in headings(body) if h.level <= 3]
    trail: list[Heading] = []
    blocks: list[tuple[str, str]] = []
    boundaries = [0, *(line for line, _ in starts), len(lines)]
    heading_at = dict(starts)
    for begin, end in zip(boundaries, boundaries[1:]):
        if begin == end:
            continue
        heading = heading_at.get(begin)
        if heading:
            trail = [h for h in trail if h.level < heading.level] + [heading]
        chunk = "\n".join(lines[begin:end]).strip()
        if chunk:
            blocks.append((" > ".join(h.text for h in trail), chunk))

    merged: list[tuple[str, str]] = []
    carry = ""
    for heading, chunk in blocks:
        chunk = f"{carry}\n\n{chunk}".strip() if carry else chunk
        if estimate_tokens(chunk) < SECTION_MIN_TOKENS:
            carry = chunk
            continue
        carry = ""
        merged.append((heading, chunk))
    if carry:
        if merged:
            merged[-1] = (merged[-1][0], f"{merged[-1][1]}\n\n{carry}")
        else:
            merged.append((blocks[-1][0] if blocks else "", carry))

    return [
        SectionDraft(heading, piece, estimate_tokens(piece))
        for heading, chunk in merged
        for piece in _split_long(chunk)
    ]


def _split_long(chunk: str) -> list[str]:
    """Splits at blank lines, and inside very long paragraphs (such as big tables) at line ends."""
    if estimate_tokens(chunk) <= SECTION_MAX_TOKENS:
        return [chunk]
    units: list[tuple[str, str]] = []
    for paragraph in re.split(r"\n\s*\n", chunk):
        if estimate_tokens(paragraph) <= SECTION_MAX_TOKENS:
            units.append((paragraph, "\n\n"))
        else:
            units.extend((line, "\n") for line in paragraph.splitlines())
    pieces: list[str] = []
    current = ""
    for unit, joiner in units:
        candidate = f"{current}{joiner}{unit}" if current else unit
        if current and estimate_tokens(candidate) > SECTION_MAX_TOKENS:
            pieces.append(current)
            current = unit
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces
