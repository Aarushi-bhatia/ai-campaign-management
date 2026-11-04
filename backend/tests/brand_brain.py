"""A fake model for brand reading. It answers every reading step for a small made-up brand.

The answers depend only on what the prompt contains, the way a real model's would.
"""

import json
import re

from app.ai.transport import AiRequest
from tests import agent_brain

GUIDE = """---
owner: Mira Holt
---
# Voice guide

Status: current. This guide replaces the 2023 voice guide.
Updated: January 2026

Acme Widget, formerly called Gizmo, is our product.

## Tone

Write short sentences.
"""

OLD_GUIDE = """# Voice guide 2023

Written in 2023.

## Tone

Be playful.
"""

NOTES = """# Sales notes

INTERNAL. Do not forward to customers.

We say we are certified.
"""

LEGAL = """# Certifications

Owner: Legal

Acme is not certified. Never say Acme is certified.
"""

NEW_GUIDE = """# Voice guide 2026

This guide replaces the voice guide.
Updated: June 2026

## Tone

Write short sentences, and be warm.
"""

BRAND = {
    "acme/guide.md": GUIDE,
    "acme/old/voice-guide-2023-old.md": OLD_GUIDE,
    "acme/internal/sales-notes.md": NOTES,
    "acme/legal/certifications.md": LEGAL,
    "acme/briefs/launch-brief.md": "# Brief\n\nLaunch it.",
}


def _card(kind="rule", status=("unknown", ""), date=("", "", ""), owner=("", ""), safe=("unknown", ""),
          rules_on=(), replaces=(), products=()):
    return {
        "summary": "A document.",
        "kind": kind,
        "claimed_status": {"value": status[0], "evidence": status[1]},
        "date": {"as_written": date[0], "iso": date[1], "evidence": date[2]},
        "owner": {"name": owner[0], "role": "", "evidence": owner[1]},
        "safe_to_quote": {"value": safe[0], "evidence": safe[1]},
        "rules_on": list(rules_on),
        "replaces": [{"document": name, "evidence": evidence} for name, evidence in replaces],
        "claims_about_other_documents": [],
        "mentions": {"products": list(products), "channels": [], "customers": [], "people": []},
    }


def _fact(subject, attribute, value, evidence, kind="must"):
    return {"subject": subject, "attribute": attribute, "value": value, "kind": kind, "scope": "", "evidence": evidence}


def _document(request: AiRequest) -> str:
    return request.prompt.task[-1].content.split("--- DOCUMENT ---\n", 1)[1]


def card(document: str) -> dict:
    if "replaces the 2023 voice guide" in document:
        return _card(status=("current", "Status: current."), date=("January 2026", "2026-01-01", "Updated: January 2026"),
                     replaces=[("2023 voice guide", "This guide replaces the 2023 voice guide.")],
                     products=["Acme Widget", "Gizmo"])
    if "Be playful" in document:
        return _card(date=("2023", "2023-01-01", "Written in 2023."), products=["Acme Widget"])
    if "INTERNAL" in document:
        return _card(kind="internal_note", safe=("no", "INTERNAL. Do not forward to customers."))
    if "Acme is not certified" in document:
        return _card(owner=("Legal", "Owner: Legal"), rules_on=["certifications"])
    if "replaces the voice guide." in document:
        return _card(date=("June 2026", "2026-06-01", "Updated: June 2026"),
                     replaces=[("voice guide", "This guide replaces the voice guide.")])
    return _card()


def facts(document: str) -> list[dict]:
    if "Do not use transparent images in email headers." in document:
        return [
            _fact("email headers", "transparent images", "not allowed", "Do not use transparent images in email headers.",
                  kind="must_not"),
            _fact("images", "banned motif", "hooded hackers", "Never show hooded hackers in any image.", kind="must_not"),
        ]
    if "Write short sentences, and be warm." in document:
        return [_fact("Acme Widget", "tone", "short and warm", "Write short sentences, and be warm.")]
    if "Write short sentences." in document:
        return [_fact("Gizmo", "tone", "short sentences", "Write short sentences.")]
    if "Be playful" in document:
        return [_fact("Acme Widget", "tone", "playful", "Be playful.")]
    if "We say we are certified" in document:
        return [_fact("Acme", "certification", "certified", "We say we are certified.", kind="fact")]
    if "Acme is not certified" in document:
        return [_fact("Acme", "certification", "not certified", "Acme is not certified.", kind="fact")]
    if "Our color is" in document:
        color = re.search(r"Our color is (\w+)", document).group(1)
        return [_fact("brand color", "value", color, f"Our color is {color}.", kind="fact")]
    return []


def links(prompt: str) -> list[dict]:
    files = dict(re.findall(r"^\[(\d+)\] (\S+) \|", prompt, re.MULTILINE))
    found = []
    for number, about in re.findall(r'^\[(\d+)\] Said by \[\d+\] \S+, about "([^"]+)"', prompt, re.MULTILINE):
        year = re.search(r"\d{4}", about)
        target = next(
            (int(i) for i, path in files.items() if (year and year.group(0) in path) or (not year and path == "guide.md")),
            0,
        )
        found.append({"statement": int(number), "target_id": target, "effect": "replaces"})
    return found


def conflicts(prompt: str) -> list[dict]:
    """Each fact's value is one side; facts with the same value agree."""
    sides: dict[str, list[int]] = {}
    for fact_id, value in re.findall(r"^\[(\d+)\] doc \d+ \| [^:]+: (.+?) \(", prompt, re.MULTILINE):
        sides.setdefault(value, []).append(int(fact_id))
    owners = [int(i) for i in re.findall(r"^\[(\d+)\] .*sets rules on: [^\n]*certifications", prompt, re.MULTILINE)]
    topic = "certifications" if "certification" in prompt else "tone"
    return [{
        "point": f"They disagree on {topic}.",
        "topic": topic,
        "sides": [{"position": value, "fact_ids": ids} for value, ids in sides.items()],
        "owner_doc_ids": owners,
    }]


def image_notes(request: AiRequest) -> list[dict]:
    """Reads each image's notes the way a model would: retired, expired, a person who left, a banned motif."""
    found = []
    banned = "hooded hackers" in request.prompt.campaign
    for line in request.prompt.task[-1].content.split("\n\n", 1)[1].splitlines():
        image = json.loads(line)
        notes = json.dumps(image["record"]).lower()
        retired, expired, left = "deprecated" in notes, "has passed" in notes, "left the company" in notes
        motif = banned and "hooded" in image["description"].lower()
        reason = ("Retired logo." if retired else "The event has passed." if expired else "The person left." if left
                  else "Banned motif: hooded hackers." if motif else "")
        found.append({
            "id": image["id"], "usable": not reason, "retired": retired, "expired": expired, "no_crop": False,
            "allowed_channels": [], "blocked_channels": [], "rules": [], "reason": reason,
        })
    return found


def channel_rules(prompt: str) -> dict:
    email = {"channel": "email", "block_transparent": "transparent" in prompt, "orientation": "any",
             "allowed_types": [], "blocked_types": [], "min_width": 0, "image_optional": False,
             "notes": ["Keep the focal point in a thin band."]}
    return {"channels": [email], "alt_text_rules": ["Describe what is shown."], "general_rules": []}


def image_choice(request: AiRequest) -> dict:
    """Picks the first cleared image listed."""
    ids = re.findall(r"^\[(\d+)\]", request.prompt.campaign, re.MULTILINE)
    return {"choices": [{"image_id": int(ids[0]), "why": "It fits.", "alt_text": "A photo of the team."}],
            "nothing_fits": False, "suggestion": ""}


def reply(request: AiRequest):
    schema = request.output_schema.name if request.output_schema else None
    if schema in ("brief_review", "campaign_plan", "plan_edit") or schema in agent_brain.WRITING_REPLIES \
            or (schema or "").endswith("_asset"):
        return agent_brain.reply(request)
    prompt = request.prompt.task[-1].content
    if schema == "image_description":
        return json.dumps({"description": "A described picture.", "image_type": "chart", "has_people": False,
                           "has_text": True})
    if schema == "image_notes":
        return json.dumps({"images": image_notes(request)})
    if schema == "channel_image_rules":
        return json.dumps(channel_rules(prompt))
    if schema == "image_choice":
        return json.dumps(image_choice(request))
    if schema == "document_card":
        return json.dumps(card(_document(request)))
    if schema == "names":
        entities = [
            {"name": "Acme Widget", "kind": "product", "short_forms": ["Widget"], "old_names": ["Gizmo"]},
        ] if "Acme Widget" in prompt else []
        return json.dumps({"entities": entities})
    if schema == "document_links":
        return json.dumps({"links": links(prompt)})
    if schema == "facts":
        return json.dumps({"facts": facts(_document(request))})
    if schema == "conflicts":
        return json.dumps({"conflicts": conflicts(prompt)})
    return "# Acme brand summary\n\nWrite short sentences."


def calls_for(requests: list[AiRequest], schema: str | None) -> int:
    return sum(1 for r in requests if (r.output_schema.name if r.output_schema else None) == schema)
