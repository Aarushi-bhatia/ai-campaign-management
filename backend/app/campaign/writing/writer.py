"""Writing one asset in one AI call, and the prompts that edit or fix it later.

Every prompt has the same start: the agent's fixed part (instructions, brand summary, core memory), then
the approved campaign (brief, answers, brief rules, plan, approved research). Only the last part, this
asset's own task, changes from call to call, so the start is read from the cache.
"""

import json
from typing import Any

from app.ai.prompt import TEXT, TEXT_LIST, OutputSchema, Prompt, Turn, array_of, enum, strict_object
from app.campaign import prompts
from app.campaign.models import Campaign

TYPE_LABELS = {"email": "Email", "linkedin_post": "LinkedIn post", "x_post": "X post", "blog_post": "Blog post",
               "landing_page": "Landing page"}
SECTION_KINDS = ("hero", "features", "how_it_works", "proof", "faq", "cta", "text")

_SOCIAL = {"author": TEXT, "text": TEXT, "hashtags": TEXT_LIST}
FIELDS: dict[str, dict[str, Any]] = {
    "email": {"sender": TEXT, "subject": TEXT, "preview_text": TEXT,
              "sections": array_of(strict_object({"heading": TEXT, "body": TEXT})),
              "button_text": TEXT, "button_link": TEXT},
    "linkedin_post": _SOCIAL,
    "x_post": _SOCIAL,
    "blog_post": {"title": TEXT, "author": TEXT, "date": TEXT, "body": TEXT},
    "landing_page": {"sections": array_of(strict_object({
        "kind": enum(*SECTION_KINDS), "heading": TEXT, "body": TEXT, "items": TEXT_LIST, "button_text": TEXT,
        "button_link": TEXT, "link_text": TEXT, "link_url": TEXT,
    }))},
}
"""The fixed fields of each asset type. Every asset also lists the research sources it used."""

HEADLINE = {"email": "subject", "blog_post": "title"}
"""The field that is the asset's own name, where it has one: the asset is called by it once written."""

GUIDE = {
    "email": "sender is the person or team it comes from, per the brief or the email rules. sections are the "
             "body in order: short, with a heading only where it helps (\"\" otherwise). button_link: a link from "
             "the brief or plan, or \"#\".",
    "linkedin_post": "author is the person or page posting, per the brief or rules. text is the whole post with "
                     "its line breaks. hashtags only if the channel rules allow them, without them in text.",
    "x_post": "author is the account posting. text is the whole post. hashtags only if the channel rules allow "
              "them, without them in text. Keep within the platform's 280 characters, hashtags included.",
    "blog_post": "author and date per the plan and brief; date is \"\" when the plan says \"to be set\". body is "
                 "markdown with ## headings, ready to publish.",
    "landing_page": "sections in reading order, starting with a hero and ending with a cta. items are short "
                    "lines for features, steps, proof points or questions; [] where not needed. button_text and "
                    "button_link are the section's main call to action. link_text and link_url are a quieter "
                    "second link beside it, such as the docs when the brief asks for one. Links come from the "
                    "brief, plan or brand documents, or \"#\" when none is given; every field is \"\" where "
                    "the section has no button or link.",
}

WRITE_TASK = """\
Write asset {number} of the approved plan: {label}, "{title}".

Its plan card:
{card}

How to write it:
- {guide}
- Follow the channel rules and the facts below. They come from the brand's current documents. Use \
only facts from them, the brand summary, the brief or the plan. Never invent figures, customers, quotes, \
dates or claims; leave a point out rather than guess.
- Material marked background only is never quoted or repeated.
- Facts from the web may come only from the approved research for this asset. Put the url of each one \
you use in sources, and cite nothing else. On product facts, prices and guidelines the brand's documents \
always beat the web.
- {image}
- Write for the audience on the card, in the brand's voice.
- Every field is published exactly as written. Never put notes for the team, design or production \
instructions, or explanations of what to do inside the copy. Leave anything the team must still supply \
as a short blank in square brackets, such as [demo page URL].
- When the card has draft_for, this is only an optional draft for that person to post themselves: write it \
in their voice, and never present it as approved, scheduled or coming from the brand's own account.

=== CHANNEL RULES ===
{rules}

=== FACTS FOR THIS ASSET ===
{facts}

=== APPROVED RESEARCH FOR THIS ASSET ===
{research}"""

FIX_TASK = """\
The {label} below failed some checks. Fix only these problems and change nothing else: keep every other \
word, field and line break as it is.

Problems:
{problems}

Current asset:
{content}

A flagged problem may be wrong: if the brief, a campaign rule, the plan, the channel rules or the facts below \
support the copy, leave it as it is and list it in dismissed, in one short line that names what supports it \
(the fact, the rule or the brief's words). Only dismiss what you can point to here; anything else is a real \
problem. Never cut supported facts.

Return the whole asset. In fixed, list each change you made in one short line. In not_fixed, list only \
real problems you couldn't fix without breaking a brand rule.

=== CHANNEL RULES ===
{rules}

=== FACTS FOR THIS ASSET ===
{facts}

=== APPROVED RESEARCH FOR THIS ASSET ===
{research}"""

EDIT_TASK = """\
The marketer asked for this change to the {label} "{title}":
{instruction}

{scope}

Current asset:
{content}

Keep to the channel rules and facts below and the approved sources, exactly as for the first draft; \
cite nothing new. Return the whole asset. In changed, say what you changed in one short line.

If the {label} already does what was asked (for example it is already shorter than the length asked for), \
return it exactly as it is, with no other change, and say in changed why nothing needed changing.

=== CHANNEL RULES ===
{rules}

=== FACTS FOR THIS ASSET ===
{facts}

=== APPROVED RESEARCH FOR THIS ASSET ===
{research}"""


def schema_for(asset_type: str, extra: dict[str, Any] | None = None) -> OutputSchema:
    return OutputSchema(name=f"{asset_type}_asset", schema=strict_object({**FIELDS[asset_type], "sources": TEXT_LIST,
                                                                          **(extra or {})}))


FIX_EXTRA = {"fixed": TEXT_LIST, "not_fixed": TEXT_LIST, "dismissed": TEXT_LIST}
EDIT_EXTRA = {"changed": TEXT}


def campaign_text(campaign: Campaign) -> str:
    """The approved campaign, the same for every asset of it, so it is cached once. Web research is not in it:
    each asset's task carries only that asset's own approved findings."""
    plan = {"summary": (campaign.plan or {}).get("summary", ""), "assets": [
        {k: v for k, v in a.items() if k != "research_query"} for a in (campaign.plan or {}).get("assets", [])
    ]}
    lines = [prompts.campaign_part(campaign), f"=== APPROVED PLAN ===\n{prompts.plan_text(plan)}"]
    return "\n\n".join(lines)


def research_text(research: list[dict[str, Any]]) -> str:
    """One line per finding; the url stands alone, so it can be copied into sources exactly."""
    return "\n".join(f"[{f['id']}] {f['finding']} (dated {f['date']}) (source: {f['url']})"
                     for f in research) or "(none)"


def prompt(fixed: str, campaign: Campaign, task: str) -> Prompt:
    return Prompt(fixed=fixed, campaign=campaign_text(campaign), task=[Turn(role="user", content=task)],
                  cache=("fixed", "campaign"))


def write_task(number: int, card: dict[str, Any], image: dict[str, Any] | None, rules: str, facts: str,
               research: list[dict[str, Any]]) -> str:
    return WRITE_TASK.format(
        number=number, label=TYPE_LABELS[card["type"]], title=card["title"],
        card=json.dumps({k: v for k, v in card.items() if k != "research_query"}, ensure_ascii=False),
        guide=GUIDE[card["type"]], image=image_line(image), rules=rules, facts=facts,
        research=research_text(research),
    )


def image_line(image: dict[str, Any] | None) -> str:
    if image and image.get("path"):
        return (f"The image chosen for it is {image['path']}: {image.get('alt_text', '')}. "
                "Write around it; don't describe it.")
    return "It has no image."


def fix_task(asset_type: str, content: dict[str, Any], problems: list[dict[str, str]],
             research: list[dict[str, Any]], rules: str, facts: str) -> str:
    """The same channel rules and facts the writer had, so "supported" is judged against the evidence."""
    lines = "\n".join(f"- {p['check']}: {p['problem']}" + (f" (“{p['quote']}”)" if p.get("quote") else "")
                      for p in problems)
    return FIX_TASK.format(label=TYPE_LABELS[asset_type], problems=lines,
                           content=json.dumps(content, ensure_ascii=False),
                           research=research_text(research), rules=rules, facts=facts)


def edit_task(asset_type: str, title: str, content: dict[str, Any], instruction: str, field: str, rules: str,
              facts: str, research: list[dict[str, Any]]) -> str:
    """The channel rules and facts are the same ones the first draft was written with."""
    scope = (f"Change only the {field} field. Every other field must come back exactly as it is." if field
             else "Change only what the request is about.")
    return EDIT_TASK.format(label=TYPE_LABELS[asset_type], title=title, instruction=instruction, scope=scope,
                            content=json.dumps(content, ensure_ascii=False), rules=rules, facts=facts,
                            research=research_text(research))


def content_problem(asset_type: str, content: dict[str, Any]) -> str | None:
    """What is wrong with the shape of typed-in content, or None. Only the fields given are checked: a field left
    out keeps its old value."""
    fields = {**FIELDS[asset_type], "sources": TEXT_LIST}
    for name, value in content.items():
        if name in fields and (problem := _shape(fields[name], value, name)):
            return problem
    return None


def _shape(schema: dict[str, Any], value: Any, where: str) -> str | None:
    if schema["type"] == "string":
        if not isinstance(value, str):
            return f"{where} must be text."
        if "enum" in schema and value not in schema["enum"]:
            return f"{where} must be one of: {', '.join(schema['enum'])}."
    elif schema["type"] == "array":
        if not isinstance(value, list):
            return f"{where} must be a list."
        return next((p for i, item in enumerate(value) if (p := _shape(schema["items"], item, f"{where} {i + 1}"))),
                    None)
    elif schema["type"] == "object":
        if not isinstance(value, dict):
            return f"{where} must have the fields {', '.join(schema['properties'])}."
        return next((p for key, sub in schema["properties"].items()
                     if key in value and (p := _shape(sub, value[key], f"{where} {key}"))), None)
    return None


def content_from(asset_type: str, reply: dict[str, Any]) -> dict[str, Any]:
    """The asset's own fields and sources, without the reply's notes."""
    return {key: reply[key] for key in (*FIELDS[asset_type], "sources")}
