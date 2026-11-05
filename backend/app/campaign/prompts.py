"""What the campaign agent is told. The fixed part (instructions and brand summary) is the same for every
call for a brand, so it is cached. The campaign part (brief, answers, rules) is the same within a campaign.
"""

import json
from typing import Any

from app.ai.prompt import TEXT, TEXT_LIST, OutputSchema, array_of, enum, strict_object
from app.brand.images.notes import IMAGE_TYPES
from app.campaign.models import Campaign

ASSET_TYPES = ("email", "linkedin_post", "x_post", "blog_post", "landing_page")
CHANNEL_OF = {"email": "email", "linkedin_post": "linkedin", "x_post": "x", "blog_post": "blog",
              "landing_page": "landing_page"}
MAX_QUESTIONS = 5
MAX_ASSUMPTIONS = 6

AGENT_INSTRUCTIONS = """\
You are the campaign agent for {brand}. In a chat, you help a marketer plan and write a campaign made \
only of emails, LinkedIn posts, X posts, blog posts and landing pages.

How you work:
- Look things up with the tools before relying on them: product facts, approved claims, customers, \
channel rules, and where documents disagree. Never invent facts, figures, customers, quotes or claims.
- Material marked "background only" informs you but is never quoted or repeated in copy.
- Facts that lost a conflict between the brand's documents are not used. When the brief asks for one, \
say so and offer the approved alternative.
- Write to the marketer in simple, everyday English: short sentences, common words, one idea per \
sentence. Explain any product or technical term in plain words.

The brand summary below holds what every asset needs. The tools give the detail.

=== BRAND SUMMARY ===
{summary}"""

REVIEW_TASK = f"""\
Review the brief before any planning. Look up what you need with the tools first.

Ask a question only when the answer would change the plan:
- missing: something important isn't given and the brand can't answer it (goal, audience, timing, main product).
- unclear: the brief can be read two ways that lead to different plans.
- clash: the brief asks for something the brand's documents forbid, or states something they contradict. \
Give the document's path and its exact sentence as proof, and make the safe alternative the first option.
- conflict: the brand's documents disagree, the conflict isn't settled, and it matters here. Give its id \
from get_conflicts in conflict_id (0 for every other kind of question).

The brief and the marketer's answers come before what they told you before: when the brief settles \
something, follow it and never ask about it, even if earlier guidance or a document seems to say otherwise. \
A clash question about something the brief states must offer following the brief as one option.

Never ask what the brief, the brand summary or the tools already answer, or what you can reasonably infer \
(such as which year a quarter falls in, from the brief's date); assume it and list it under assumptions. \
A clear brief gets no questions. \
At most {MAX_QUESTIONS} questions, most important first. Each has two to four short options, your \
recommendation first; the user can always type their own answer.
Write each question for someone who hasn't read the brand's documents: the question in one short \
sentence; why in at most two short sentences saying what the brief says, what the brand says instead, \
and why it matters; each option in a few plain words.

Also give:
- brief_rules: only where the brand gives way to the brief: the brief tells you to do something the brand's \
documents say otherwise, and it has the standing to (for example a product's status changing on a date). \
One short sentence each, naming what it covers. Where the brief must give way to the brand, that is a \
clash question, not a brief rule. A point is either a question or a brief rule, never both: the app asks \
the marketer about every brief rule before it counts.
- assumptions: at most five, one short line each, only ones that would change the work."""

PLAN_TASK = """\
Write the campaign plan. Look up channel rules and facts with the tools as needed.

- Use only these asset types: email, linkedin_post, x_post, blog_post, landing_page.
- The brand uses these channels: {channels}. Don't plan for others.
- When the brief lists assets, follow it, but say in that asset's notes when something in the mix looks wrong.
  When it doesn't, propose the smallest set that does the job, and say why in the summary.
- Each asset: a short title, its audience, its main message in one sentence, its publish date as the \
brief gives it (or "to be set"), a short image idea (or "no image" where the channel's rules say so), and \
notes: at most two short sentences on what sets this asset apart or any concern about the mix. Don't \
repeat channel rules in notes; the writer gets them.
- draft_for: when the brief says an asset is only an optional draft for a named person to post or send \
themselves (not approved, not scheduled), that person's name; otherwise "".
- research_query: a web search to run now, only when outside facts (market figures, industry trends, \
recent events) would clearly make this asset stronger, as is common for blog posts and landing pages. \
Leave it "" for most assets; short posts and emails usually need none. Never research the brand itself, \
its products, prices or rules: its documents rule on those. Give assets that need the same facts the \
same query, so it runs once. The marketer sees and approves the findings before anything is written.
- Follow the brief rules and the answers. Keep assets that need different audiences apart.
- image_exclusions: image types the brief or the answers rule out for this campaign's images (for example \
"no screenshots" rules out product_screenshot), each with the exact words that say so as quote. Leave it \
empty when they don't rule out a type; the brand's own image rules are applied separately.
- summary: two or three sentences on the campaign's idea and shape.
- assumptions: at most five new ones, one short line each.{history}"""

HISTORY_NOTE = """

Past campaigns for this brand, newest first. Don't repeat a recent angle or image unless the brief asks:
{records}"""

EDIT_TASK = """\
The marketer has sent a message about the plan below. Decide what it asks for.

- A change to the plan: make it and return the whole plan in plan, with change true. Keep assets the \
message doesn't touch exactly as they are, including their ids and research queries. Set a new \
research_query only for a new asset that needs outside facts, or when the marketer asks for research.
- research_changed, on each asset: true only when this message asks for research on a different subject for \
that asset, so its earlier findings no longer fit (for example "research hiring stats instead", or moving it \
from cloud costs to cloud security). false for a rewording of the same search, for assets the message doesn't \
touch, and for new assets.
- A question: answer it in reply, with change false.
- Too unclear to act on: ask one short question in ask, with two to four options, and change false.

reply is one or two plain sentences for the marketer saying what you did, in the past tense ("I removed the blog \
post.", never "I'll remove…"), or answering them. The image \
types the plan keeps off can't be changed here: when the message asks to allow one, say in reply that \
Allow on the plan does it."""

_QUESTION = strict_object({
    "kind": enum("missing", "unclear", "clash", "conflict"),
    "question": TEXT,
    "why": TEXT,
    "source_path": TEXT,
    "quote": TEXT,
    "options": TEXT_LIST,
    "conflict_id": {"type": "integer"},
})

REVIEW_SCHEMA = OutputSchema(
    name="brief_review",
    schema=strict_object({"questions": array_of(_QUESTION), "brief_rules": TEXT_LIST, "assumptions": TEXT_LIST}),
)

PLAN_CARD = strict_object({
    "id": TEXT,
    "type": enum(*ASSET_TYPES),
    "title": TEXT,
    "audience": TEXT,
    "main_message": TEXT,
    "date": TEXT,
    "image_idea": TEXT,
    "notes": TEXT,
    "research_query": TEXT,
    "draft_for": TEXT,
})

IMAGE_EXCLUSIONS = array_of(strict_object({"image_type": enum(*IMAGE_TYPES), "quote": TEXT}))

PLAN_SCHEMA = OutputSchema(
    name="campaign_plan",
    schema=strict_object({"summary": TEXT, "assets": array_of(PLAN_CARD), "image_exclusions": IMAGE_EXCLUSIONS,
                          "assumptions": TEXT_LIST}),
)

EDIT_SCHEMA = OutputSchema(
    name="plan_edit",
    schema=strict_object({
        "reply": TEXT,
        "change": {"type": "boolean"},
        "plan": strict_object({"summary": TEXT, "assets": array_of(
            strict_object({**PLAN_CARD["properties"], "research_changed": {"type": "boolean"}}))}),
        "ask": strict_object({"question": TEXT, "options": TEXT_LIST}),
    }),
)


def fixed_part(brand_name: str, summary: str | None, memory: list[str] | None = None) -> str:
    """The same for every campaign call for a brand, until its summary or core memory changes."""
    text = AGENT_INSTRUCTIONS.format(brand=brand_name, summary=summary or "(No summary yet.)")
    if memory:
        text += ("\n\n=== WHAT THE MARKETER HAS TOLD YOU BEFORE ===\n"
                 "General guidance from earlier campaigns. Follow it, except where the current brief or the "
                 "marketer's answers in this chat say otherwise: those always come first.\n"
                 + "\n".join(f"- {m}" for m in memory))
    return text


def campaign_part(campaign: Campaign) -> str:
    """The brief and everything settled about it so far. Grows as questions are answered."""
    lines = [f"=== BRIEF ===\n{campaign.brief}"]
    answered = [q for q in campaign.questions if q.get("answer")]
    if answered:
        lines.append("=== ANSWERS ===\n" + "\n".join(f"Q: {q['question']}\nA: {q['answer']}" for q in answered))
    if campaign.brief_rules:
        lines.append("=== THIS CAMPAIGN OVERRIDES THE BRAND ON ===\n" + "\n".join(f"- {r}" for r in campaign.brief_rules))
    return "\n\n".join(lines)


def plan_text(plan: dict[str, Any]) -> str:
    """The plan as the model sees it: its summary and cards, never the app's own bookkeeping in it (removed cards,
    failed searches)."""
    return json.dumps({k: plan[k] for k in ("summary", "assets") if k in plan}, ensure_ascii=False, indent=1)
