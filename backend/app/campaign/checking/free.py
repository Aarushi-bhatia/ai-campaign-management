"""The free checks: plain rules run on an asset's text, with no AI. They run after every write and edit.

- banned words and phrases from the brand's writing rules
- retired product or company names
- length limits, from the brand's rules and the platform's own limits
- the chosen image, against the image rules
- citations: every link and source must be in the approved research
"""

import re
from dataclasses import dataclass, field
from typing import Any

PLATFORM_LIMITS = {"x_post": {"text": 280}, "linkedin_post": {"text": 3000}}
"""Limits set by the platforms themselves, not by any brand."""
CHANNEL_OF = {"email": "email", "linkedin_post": "linkedin", "x_post": "x", "blog_post": "blog",
              "landing_page": "landing_page"}
LINK_FIELDS = {"button_link", "link_url"}
"""Fields that hold the asset's own link, which is not a citation."""
LINK = re.compile(r"https?://[^\s)\]>\"'`]+")
_FORMERLY = re.compile(r"\b(formerly|previously|once called|renamed from|used to be called)\b[^.]{0,40}$",
                       re.IGNORECASE)


@dataclass(frozen=True)
class Problem:
    check: str
    """banned word, old name, length, image, citation, claim or tone."""
    problem: str
    quote: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"check": self.check, "problem": self.problem, "quote": self.quote}


@dataclass(frozen=True)
class CheckRules:
    banned: list[dict[str, str]] = field(default_factory=list)
    old_names: list[dict[str, str]] = field(default_factory=list)
    limits: list[dict[str, Any]] = field(default_factory=list)
    approved_urls: frozenset[str] = frozenset()
    """Approved research, plus links the brief or the brand's own documents give (such as a product page)."""
    image_problem: str | None = None
    """Why the chosen image can't be used, worked out by the image rules."""
    hashtag_max: int | None = None
    """The most hashtags the channel's rules allow (0: none), from the writing rules; None when they don't say."""


def texts_of(content: dict[str, Any]) -> list[tuple[str, str]]:
    """Every piece of text in an asset, as (field, text). Lists and sections are flattened."""
    found: list[tuple[str, str]] = []

    def walk(name: str, value: Any) -> None:
        if isinstance(value, str):
            found.append((name, value))
        elif isinstance(value, list):
            for item in value:
                walk(name, item)
        elif isinstance(value, dict):
            for key in sorted(value):
                walk(key if name in ("", "sections") else f"{name}.{key}", value[key])

    for key in sorted(content):  # the database doesn't keep key order
        if key != "sources":
            walk(key, content[key])
    return found


def plain_text(content: dict[str, Any]) -> str:
    return "\n".join(text for name, text in texts_of(content) if name not in LINK_FIELDS)


FREE_CHECKS = frozenset({"banned word", "old name", "length", "image", "citation", "empty", "hashtags"})
"""The checks that run without AI, so a hand edit can run them again. The AI's own findings (claim, tone) and
"not checked" stay until Check again."""

MAIN_TEXT = {"email": "body", "linkedin_post": "text", "x_post": "text", "blog_post": "body", "landing_page": "body"}
"""The field that holds an asset's actual message. Without it, the asset has nothing to publish."""


def is_empty(asset_type: str, content: dict[str, Any]) -> bool:
    main = MAIN_TEXT[asset_type]
    return not any(text.strip() for name, text in texts_of(content) if name in (main, "heading"))


def free_checks(asset_type: str, content: dict[str, Any], rules: CheckRules) -> list[Problem]:
    texts = [(name, text) for name, text in texts_of(content) if name not in LINK_FIELDS]
    if is_empty(asset_type, content):
        return [Problem("empty", "The asset has no text.")]
    problems = [*_banned(texts, rules.banned), *_old_names(texts, rules.old_names),
                *_lengths(asset_type, content, rules.limits), *_citations(content, rules.approved_urls)]
    if rules.image_problem:
        problems.append(Problem("image", f"The image can't be used here: {rules.image_problem}"))
    if rules.hashtag_max is not None:
        problems += _hashtags(content, rules.hashtag_max)
    return problems


def _banned(texts: list[tuple[str, str]], banned: list[dict[str, str]]) -> list[Problem]:
    problems = []
    for rule in banned:
        exact = _case_matters(rule["term"], rule.get("instead", ""))
        for name, text in texts:
            match = _find(rule["term"], text, exact)
            if match:
                instead = f" Use {rule['instead']} instead." if rule.get("instead") else ""
                problems.append(Problem("banned word", f"Uses “{rule['term']}” in {name}.{instead}", match))
                break
    return problems


def _old_names(texts: list[tuple[str, str]], old_names: list[dict[str, str]]) -> list[Problem]:
    problems = []
    for rule in old_names:
        hit = next(((name, m) for name, text in texts for m in _matches(rule["old"], text)
                    if not _new_name_at(text, m, rule["new"])), None)
        if hit:
            name, match = hit
            problems.append(Problem("old name", f"Uses the retired name “{rule['old']}” in {name}. Use {rule['new']}.",
                                    match.group(0)))
    return problems


def _new_name_at(text: str, match: re.Match, new: str) -> bool:
    """True when the current name starts at the same place, so the old one is only part of it
    (an old name "Acme" inside the current "Acme Cloud")."""
    text = _straight(text)
    return (bool(new) and len(new) > len(match.group(0))
            and text[match.start():match.start() + len(new)].lower() == new.lower())


X_LINK_LENGTH = 23
"""X counts every link as 23 characters, however long it is."""


def _lengths(asset_type: str, content: dict[str, Any], limits: list[dict[str, Any]]) -> list[Problem]:
    """One limit per field and unit, the strictest of each: a brand's word limit never replaces the platform's
    character limit on the same field; both apply."""
    channel = CHANNEL_OF.get(asset_type)
    wanted: dict[tuple[str, str], int] = {(f, "characters"): n for f, n in PLATFORM_LIMITS.get(asset_type, {}).items()}
    for limit in limits:
        if limit["channel"] == channel:
            key = (limit["field"], limit["unit"])
            wanted[key] = min(limit["max"], wanted.get(key, limit["max"]))
    problems = []
    for (field_name, unit), maximum in wanted.items():
        text = _field_text(asset_type, content, field_name)
        if text is None:
            continue
        if asset_type == "x_post" and unit == "characters":
            text = LINK.sub("x" * X_LINK_LENGTH, text)
        size = len(text.split()) if unit == "words" else len(text)
        if size > maximum:
            problems.append(Problem("length", f"{field_name} is {size} {unit}; the limit is {maximum}."))
    return problems


def _field_text(asset_type: str, content: dict[str, Any], field_name: str) -> str | None:
    """The text a length limit applies to. An X post's hashtags count towards its length."""
    if field_name == "headline":
        sections = content.get("sections") or []
        return sections[0].get("heading") if sections else content.get("title")
    if field_name == "body" and "sections" in content:
        return "\n".join(s.get("body", "") for s in content["sections"])
    value = content.get(field_name)
    if not isinstance(value, str):
        return None
    if asset_type == "x_post" and field_name == "text" and content.get("hashtags"):
        value = f"{value} {' '.join(_hashtag(t) for t in content['hashtags'])}"
    return value


_HASHTAG = re.compile(r"(?<![\w&/])#[A-Za-z]\w*")


def _hashtags(content: dict[str, Any], maximum: int) -> list[Problem]:
    """Tags in the hashtags field and in the text, each counted once."""
    tags = [_hashtag(t.strip()) for t in content.get("hashtags") or [] if t.strip()]
    tags += [m.group(0) for name, text in texts_of(content) if name not in LINK_FIELDS for m in _HASHTAG.finditer(text)]
    seen: dict[str, str] = {}
    for tag in tags:
        seen.setdefault(tag.lower(), tag)
    unique = list(seen.values())
    if len(unique) <= maximum:
        return []
    allowed = "say no hashtags" if maximum == 0 else f"allow at most {maximum}"
    return [Problem("hashtags", f"Uses {len(unique)} hashtag{'s' if len(unique) > 1 else ''} ({', '.join(unique)}); "
                                f"the channel rules {allowed}.", unique[0])]


def _citations(content: dict[str, Any], approved: frozenset[str]) -> list[Problem]:
    cited = {u.rstrip(".,;") for name, text in texts_of(content) if name not in LINK_FIELDS for u in LINK.findall(text)}
    cited |= {s.strip() for s in content.get("sources", []) if s.strip()}
    known = {_bare(u) for u in approved}
    return [Problem("citation", f"Cites a source that isn't in the approved research: {url}", url)
            for url in sorted(cited) if _bare(url) not in known]


def _bare(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.strip().rstrip("/")).lower()


def _hashtag(tag: str) -> str:
    return tag if tag.startswith("#") else f"#{tag}"


def _case_matters(term: str, instead: str) -> bool:
    """A banned spelling like "LeashGate" (use "Leashgate") is about capitals, so it is matched exactly."""
    return term.lower() == instead.lower() or bool(re.search(r"[a-z][A-Z]", term))


def _pattern(term: str, exact: bool = False) -> re.Pattern:
    """A whole-word pattern where spaces and hyphens in the term match either. Case-blind unless `exact`.
    Punctuation around the term is left out: a retired line listed as "Sleep through the night." is still
    found when the copy drops the full stop or quotes it."""
    parts = [re.escape(p) for p in re.split(r"[\s\-]+", _straight(term).strip().strip(".,;:!?\"'")) if p]
    body = r"[\s\-]+".join(parts)
    return re.compile(rf"(?<![\w-]){body}(?![\w-])", 0 if exact else re.IGNORECASE)


def _matches(term: str, text: str) -> list[re.Match]:
    return [m for m in _pattern(term).finditer(_straight(text)) if not _FORMERLY.search(_straight(text)[:m.start()])]


def _find(term: str, text: str, exact: bool = False) -> str:
    match = _pattern(term, exact).search(_straight(text))
    return match.group(0) if match else ""


def _straight(text: str) -> str:
    return text.translate(str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "}))
