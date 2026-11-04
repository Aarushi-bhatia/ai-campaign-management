"""Old and new names: which names refer to the same product, company or customer.

The model groups the names found on the cards. An old name is only kept when some sentence in the
brand's documents mentions it together with the current name, and that sentence is stored as proof.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from app.ai.prompt import TEXT, TEXT_LIST, OutputSchema, Prompt, Turn, array_of, enum, strict_object
from app.brand.evidence import normalize, sentence_with_all, sentences

NAMES_VERSION = 2
MENTION_GROUPS = ("products", "customers", "channels")
MAX_RENAME_SENTENCES = 60

# Words that often sit next to a rename. Only used to pick sentences to show the model; every old name
# it returns is still checked against the documents.
_RENAME_HINT = re.compile(
    r"\b(formerly|renamed|rename|rebrand(?:ed|ing)?|is now|now called|now named|previously|was called|"
    r"were called|used to be|new name|old name|until)\b",
    re.IGNORECASE,
)

INSTRUCTIONS = """\
You get the names found in a company's brand documents, and sentences from those documents that may \
mention renames. Group the names that refer to the same thing.

For each thing:
- name: its current full name, as the newest documents use it.
- kind: company, product, customer, channel or other.
- short_forms: shorter or plural forms of the same name, such as the product name without the company \
name in front.
- old_names: names it had before a rename. Use the sentences to find them: "X (formerly Y)", \
"Y is now X", "called Y until 2026" and the like.

Only list the company, its products, customers, partners, competitors, channels and named programs or \
events. Leave out people and generic things such as documents, decks, reports or talks. Use names from \
the list or the sentences. A name with nothing else in its group is still listed."""

SCHEMA = OutputSchema(
    name="names",
    schema=strict_object(
        {
            "entities": array_of(
                strict_object(
                    {
                        "name": TEXT,
                        "kind": enum("company", "product", "customer", "channel", "other"),
                        "short_forms": TEXT_LIST,
                        "old_names": TEXT_LIST,
                    }
                )
            )
        }
    ),
)


@dataclass
class EntityDraft:
    name: str
    kind: str
    short_forms: list[str] = field(default_factory=list)
    old_names: list[dict[str, str]] = field(default_factory=list)


def collect_names(cards: list[dict[str, Any]]) -> list[str]:
    """Every product, customer and channel name on the cards, most mentioned first."""
    counts: Counter[str] = Counter()
    spelling: dict[str, str] = {}
    for card in cards:
        for group in MENTION_GROUPS:
            for name in card.get("mentions", {}).get(group, []):
                key = normalize(name)
                if key:
                    counts[key] += 1
                    spelling.setdefault(key, name.strip())
    return [spelling[key] for key, _ in counts.most_common()]


def rename_sentences(documents: list[tuple[str, str]], names: list[str]) -> list[str]:
    """Sentences that may describe a rename: they use a rename word and name something from the list."""
    known = [normalize(name) for name in names]
    found: list[str] = []
    seen: set[str] = set()
    for _, text in documents:
        for sentence in sentences(text):
            key = normalize(sentence)
            if key in seen or len(sentence) > 400 or not _RENAME_HINT.search(sentence):
                continue
            if any(name and name in key for name in known):
                seen.add(key)
                found.append(sentence)
    return found[:MAX_RENAME_SENTENCES]


def prompt_for(names: list[str], hints: list[str]) -> Prompt:
    task = "Names:\n" + "\n".join(names) + "\n\nSentences that may mention renames:\n" + "\n".join(
        f"- {sentence}" for sentence in hints
    )
    return Prompt(fixed=INSTRUCTIONS, task=[Turn(role="user", content=task)])


def checked_entities(raw_reply: str, documents: list[tuple[str, str]]) -> list[EntityDraft]:
    """Keeps short forms that are part of the full name, and old names that a sentence links to the new one.

    `documents` is a list of (path, text).
    """
    entities: list[EntityDraft] = []
    for item in json.loads(raw_reply)["entities"]:
        name = item["name"].strip()
        if not name:
            continue
        entity = EntityDraft(name=name, kind=item["kind"])
        for short in item["short_forms"]:
            if _is_part_of(short, name):
                entity.short_forms.append(short.strip())
            else:
                item["old_names"].append(short)
        current_names = [name, *entity.short_forms]
        for old in item["old_names"]:
            proof = _proof(old, current_names, documents)
            if proof:
                entity.old_names.append(proof)
        entities.append(entity)
    return entities


def subject_keys(entities: list[EntityDraft]) -> dict[str, str]:
    """Maps every known spelling, lower case, to the entity's current name, lower case."""
    keys: dict[str, str] = {}
    for entity in entities:
        canonical = normalize(entity.name)
        for spelling in [entity.name, *entity.short_forms, *(old["name"] for old in entity.old_names)]:
            keys.setdefault(normalize(spelling), canonical)
    return keys


def key_for(subject: str, keys: dict[str, str]) -> str:
    normalized = normalize(subject)
    return keys.get(normalized, normalized)


def vocabulary(entities: list[EntityDraft]) -> str:
    """The names list given to the fact step, so facts about one thing share one subject."""
    lines = []
    for entity in entities:
        others = [*entity.short_forms, *(f"{old['name']} (old name)" for old in entity.old_names)]
        lines.append(f"- {entity.name} ({entity.kind})" + (f": also {', '.join(others)}" if others else ""))
    return "\n".join(lines)


def _is_part_of(short: str, name: str) -> bool:
    """True for a shorter form of the name, ignoring plurals: "Evenburn" in "Wickhold Evenburn", "deck" in "decks"."""
    short_words = [_singular(word) for word in normalize(short).split()]
    name_words = [_singular(word) for word in normalize(name).split()]
    return bool(short_words) and all(word in name_words for word in short_words)


def _singular(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _proof(old: str, current_names: list[str], documents: list[tuple[str, str]]) -> dict[str, str] | None:
    for path, text in documents:
        for current in current_names:
            if normalize(old) == normalize(current):
                continue
            sentence = sentence_with_all(text, [old, current])
            if sentence:
                return {"name": old.strip(), "evidence": sentence, "path": path}
    return None
