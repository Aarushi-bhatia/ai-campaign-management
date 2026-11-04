"""The AI check: claims against the brand's approved facts, and the brand's tone. The medium model does it.

A problem is kept only when the words it points to are really in the asset, so the check can't
flag copy that isn't there.
"""

import json
from typing import Any

from app.ai.prompt import TEXT, OutputSchema, Prompt, Turn, array_of, enum, strict_object
from app.ai.service import AiReply, AiService
from app.brand.evidence import Document
from app.campaign.checks import Problem, plain_text
from app.config import ModelSize

INSTRUCTIONS = """\
You check one piece of marketing copy for {brand} before it goes out. You get the brand summary, the \
approved campaign (brief, answers, campaign rules and plan, all approved by the marketer), and the \
facts, rules and approved web research the writer was given for this piece.

Flag only real problems:
- claim: a statement about the brand, its products, customers, numbers, certifications or results that \
none of the summary, the approved campaign, the facts or the approved research support, or that goes beyond what they say. \
Also any quote or customer story not in them, and anything from background-only material. Copy that \
follows the brief or a campaign rule is supported, even where an older brand document says otherwise.
- tone: a clear break from the brand's voice and word rules in the summary.
- rule: a break of a channel rule the writer had (for example hashtags where the rules forbid them, or a \
competitor named where the rules say never to), or of something the marketer told you before (listed \
below), unless the brief or the approved campaign says otherwise.

For each give the exact words from the copy (quote, copied character for character), the problem in one \
short sentence, and the fix in one short sentence. Don't flag style you merely dislike. No problems is a \
fine answer.

=== BRAND SUMMARY ===
{summary}"""

SCHEMA = OutputSchema(
    name="asset_check",
    schema=strict_object({"problems": array_of(strict_object({
        "check": enum("claim", "tone", "rule"), "quote": TEXT, "problem": TEXT, "fix": TEXT,
    }))}),
)


def memory_text(memory: list[str] | None) -> str:
    """Core memory, as the writer gets it: the check holds the copy to it too."""
    if not memory:
        return ""
    return "\n\n=== WHAT THE MARKETER HAS TOLD YOU BEFORE ===\n" + "\n".join(f"- {line}" for line in memory)


def ai_check(ai: AiService, *, brand_name: str, summary: str | None, campaign: str, asset_label: str,
             content: dict[str, Any], facts: str, step: str, chat_id: int | None,
             brand_id: int, research: str = "(none)", rules: str = "(none)",
             memory: list[str] | None = None) -> tuple[list[Problem], AiReply]:
    """`campaign` is the approved campaign as the writer saw it; it is the same for every check of a campaign.
    The channel's rules get a cached part of their own: they are the same for every check of an asset on that
    channel (and for Check again and re-checks after edits), so only the first check on a channel pays for them
    in full."""
    task = (f"=== FACTS THE WRITER HAD ===\n{facts}"
            f"\n\n=== APPROVED RESEARCH FOR THIS PIECE ===\n{research}"
            f"\n\n=== THE {asset_label.upper()} TO CHECK ===\n{json.dumps(content, ensure_ascii=False)}")
    reply = ai.complete(
        step=step, size=ModelSize.MEDIUM, output_schema=SCHEMA, chat_id=chat_id, brand_id=brand_id,
        prompt=Prompt(fixed=INSTRUCTIONS.format(brand=brand_name, summary=summary or "(none)") + memory_text(memory),
                      campaign=campaign, channel=f"=== CHANNEL RULES THE WRITER HAD ===\n{rules}",
                      task=[Turn(role="user", content=task)], cache=("fixed", "campaign", "channel")),
        cache_key=f"brand-{brand_id}",
    )
    text = Document(plain_text(content))
    problems = [
        Problem(p["check"], f"{p['problem'].strip()} Fix: {p['fix'].strip()}".strip(), p["quote"].strip())
        for p in json.loads(reply.text)["problems"]
        if p["problem"].strip() and text.contains(p["quote"])
    ]
    return problems, reply
