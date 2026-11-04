"""A fake campaign agent. It looks things up with a tool first, then answers from what the brief says."""

import json
import re

from app.ai.fake import CallTools
from app.ai.transport import AiRequest


def _question(kind, question, options, source="", quote="", conflict_id=0):
    return {"kind": kind, "question": question, "why": "It changes the plan.", "source_path": source, "quote": quote,
            "options": options, "conflict_id": conflict_id}


def _asset(asset_id, kind, title, audience="Platform leads", research=""):
    return {"id": asset_id, "type": kind, "title": title, "audience": audience, "main_message": f"{title}.",
            "date": "2027-01-26", "image_idea": "A working room", "notes": "", "research_query": research}


def _unsettled_conflict_ids(tool_turns) -> list[int]:
    """The unsettled conflicts a get_conflicts lookup returned, the way the model would read them."""
    ids = []
    for turn in tool_turns:
        if turn.get("type") == "function_call_output" and turn["output"].startswith("["):
            ids += [c["id"] for c in json.loads(turn["output"]) if "settled" in c and not c["settled"]]
    return ids


def review(brief: str, tool_turns=()) -> dict:
    questions = []
    if "is certified" in brief:
        questions.append(_question(
            "clash", "The brief says Acme is certified, but Legal says it isn't. Use the approved line?",
            ["Say Acme is not certified", "Leave certification out"],
            source="legal/certifications.md", quote="Acme is not certified.",
        ))
    if "invented" in brief:
        questions.append(_question("clash", "Drop the claim?", ["Drop it", "Keep it"],
                                   source="legal/certifications.md", quote="Acme is certified by everyone."))
    if "awareness" in brief:
        questions.append(_question("missing", "Who is it for?", ["Platform leads", "Security leaders"]))
        questions.append(_question("missing", "When does it run?", ["Q1", "Q2"]))
    if "color" in brief:
        seen = _unsettled_conflict_ids(tool_turns)
        # "an unknown conflict" makes the fake give an id it was never shown, as a confused model might
        conflict_id = 999_999 if "an unknown conflict" in brief else (seen[0] if seen else 0)
        questions.append(_question("conflict", "Your documents disagree on the color. Which is right?",
                                   ["one", "two"], conflict_id=conflict_id))
    rules = ["The early access label comes off for these assets only."] if "label comes off" in brief else []
    return {"questions": questions, "brief_rules": rules, "assumptions": ["Publish dates follow the brief."]}


def plan(brief: str) -> dict:
    if "every asset type" in brief:
        return {"summary": "One of each asset type.", "assumptions": [], "assets": [
            _asset("a1", "email", "Launch email"), _asset("a2", "linkedin_post", "Launch post"),
            _asset("a3", "x_post", "X launch post"), _asset("a4", "blog_post", "Launch blog"),
            _asset("a5", "landing_page", "Launch page")]}
    research = "widget market size" if "with research" in brief else ""
    three = "three searches" in brief  # one search per asset
    return {
        "summary": "A launch told to platform leads. Acme is not certified, so the copy never says it is.",
        "assets": [_asset("a1", "email", "Launch email", research="email trends" if three else ""),
                   _asset("a2", "linkedin_post", "Launch post", research="widget market size" if three else research),
                   _asset("a3", "x_post", "X launch post", "Platform engineers", research="x trends" if three else "")],
        "assumptions": ["No paid media."],
    }


def edit(message: str, current: dict) -> dict:
    empty_ask = {"question": "", "options": []}
    if "drop the x post" in message.lower():
        kept = [a for a in current["assets"] if a["type"] != "x_post"]
        return {"reply": "Dropped the X post.", "change": True, "plan": {"summary": current["summary"], "assets": kept},
                "ask": empty_ask}
    if "research hiring stats instead" in message.lower():
        moved = [{**a, "research_query": "hiring stats", "research_changed": True} if a["research_query"] else a
                 for a in current["assets"]]
        return {"reply": "New topic.", "change": True, "plan": {"summary": current["summary"], "assets": moved},
                "ask": empty_ask}
    if "swap the x post for a blog post" in message.lower():
        # the new card comes without an id, in the dropped card's place, asking a near-identical search
        kept = [a for a in current["assets"] if a["type"] != "x_post"]
        blog = {**kept[0], "id": "", "type": "blog_post", "title": "Launch blog", "research_query": "x trends 2026"}
        return {"reply": "Swapped.", "change": True, "plan": {"summary": current["summary"], "assets": [*kept, blog]},
                "ask": empty_ask}
    if "research market share instead" in message.lower():
        # most words shared, but a different subject: the model says so
        moved = [{**a, "research_query": "widget market share", "research_changed": True} if a["research_query"] else a
                 for a in current["assets"]]
        return {"reply": "New subject.", "change": True, "plan": {"summary": current["summary"], "assets": moved},
                "ask": empty_ask}
    if "ask it as a question" in message.lower():
        # few words shared, but the same subject: the model says it's a rewording
        asked = [{**a, "research_query": "how big is the widget market", "research_changed": False}
                 if a["research_query"] else a for a in current["assets"]]
        return {"reply": "Reworded.", "change": True, "plan": {"summary": current["summary"], "assets": asked},
                "ask": empty_ask}
    if "reword the search" in message.lower():
        reworded = [{**a, "research_query": "Widget market size, 2026"} if a["research_query"] else a
                    for a in current["assets"]]
        return {"reply": "Reworded.", "change": True, "plan": {"summary": current["summary"], "assets": reworded},
                "ask": empty_ask}
    if "better" in message.lower():
        return {"reply": "", "change": False, "plan": {"summary": "", "assets": []},
                "ask": {"question": "Better how?", "options": ["Shorter", "More technical"]}}
    return {"reply": "The email goes to customers first.", "change": False, "plan": {"summary": "", "assets": []},
            "ask": empty_ask}


def reply(request: AiRequest):
    schema = request.output_schema.name
    if schema not in ("brief_review", "campaign_plan", "plan_edit"):
        return writing_reply(request)
    brief = request.prompt.campaign
    if not request.tool_turns:
        lookups = [("get_facts", {"topic": "certification"})]
        if schema == "brief_review" and "color" in brief:
            lookups.append(("get_conflicts", {"topic": "brand color"}))
        return CallTools(lookups)
    if schema == "brief_review":
        return json.dumps(review(brief, request.tool_turns))
    if schema == "campaign_plan":
        return json.dumps(plan(brief))
    task = request.prompt.task[-1].content
    current = json.loads(re.search(r"=== CURRENT PLAN ===\n(.*?)\n\n=== MESSAGE ===", task, re.DOTALL).group(1))
    return json.dumps(edit(task.split("=== MESSAGE ===\n", 1)[1], current))


# Writing, checking and editing assets

def _content(kind: str, text: str) -> dict:
    if kind == "email":
        return {"sender": "Acme team", "subject": "Meet Acme Widget", "preview_text": "It is here.",
                "sections": [{"heading": "", "body": text}], "button_text": "Read more", "button_link": "#"}
    if kind in ("linkedin_post", "x_post"):
        return {"author": "Acme", "text": text, "hashtags": []}
    if kind == "blog_post":
        return {"title": "Acme Widget", "author": "Acme", "date": "2027-01-26", "body": text}
    return {"sections": [{"kind": "hero", "heading": "Acme Widget", "body": text, "items": [], "button_text": "Book a demo",
                          "button_link": "https://acme.example/demo", "link_text": "Read the docs",
                          "link_url": "https://acme.example/docs"}]}


def _kind(request: AiRequest) -> str:
    return request.output_schema.name.removesuffix("_asset")


def write(request: AiRequest) -> dict:
    """Writes each asset from its plan card. The X post uses the retired name Gizmo, so a check catches it."""
    kind = _kind(request)
    task = request.prompt.task[-1].content
    text = "Gizmo is now Acme Widget, for platform leads." if kind == "x_post" else "Acme Widget is here for platform leads."
    sources = re.findall(r"\(source: (\S+)\)", task.split("=== APPROVED RESEARCH FOR THIS ASSET ===")[1])
    if sources:
        text += " The widget market grew 12% in 2026."
    if "Invent a source" in request.prompt.campaign:
        text += " See https://made-up.example/report."
    return {**_content(kind, text), "sources": sources}


def fix(request: AiRequest) -> dict:
    content = json.loads(request.prompt.task[-1].content.split("Current asset:\n", 1)[1].split("\n\n", 1)[0])
    text = json.dumps(content).replace("Gizmo is now ", "")
    return {**json.loads(text), "fixed": ["Removed the retired name Gizmo."], "not_fixed": [], "dismissed": []}


def edit_asset(request: AiRequest) -> dict:
    task = request.prompt.task[-1].content
    content = json.loads(task.split("Current asset:\n", 1)[1].split("\n\n", 1)[0])
    if "Empty it" in task:
        return {**content, "text": "", "changed": "Removed the post."}
    if "version 2" in task:
        return {**content, "changed": "No changes made. Please share version 2."}
    if "text" in content:
        content["text"], content["author"] = "Short.", "Someone the edit should not touch"
    else:
        content = json.loads(json.dumps(content).replace("Acme Widget is here", "Acme Widget, shorter"))
    content["subject"] = "A new subject" if "subject" in content else None
    content = {k: v for k, v in content.items() if v is not None}
    return {**content, "changed": "Made it shorter."}


def check(request: AiRequest) -> dict:
    return {"problems": []}


def route(request: AiRequest) -> dict:
    message = request.prompt.task[-1].content.rsplit("Message:\n", 1)[1].lower()
    none = {"question": "", "options": []}
    if "shorten one of them" in message:  # no target named: the app asks which
        return {"action": "edit", "targets": [], "instruction": "Shorten it.", "research_query": "", "reply": "",
                "ask": none, "new_assets": []}
    if "shorten asset 3" in message:
        return {"action": "edit", "targets": [{"asset": 3, "field": ""}], "instruction": "Shorten it.",
                "research_query": "", "reply": "Shortened it.", "ask": none, "new_assets": []}
    if "drop the second post" in message or "remove everything" in message:
        numbers = (1, 2, 3) if "everything" in message else (2,)
        return {"action": "remove", "targets": [{"asset": n, "field": ""} for n in numbers], "instruction": "",
                "research_query": "", "reply": "Removed it.", "ask": none, "new_assets": []}
    if "empty the second post" in message:
        return {"action": "edit", "targets": [{"asset": 2, "field": ""}], "instruction": "Empty it.",
                "research_query": "", "reply": "Done.", "ask": none, "new_assets": []}
    if "second post" in message:
        return {"action": "edit", "targets": [{"asset": 2, "field": "text"}], "instruction": "Shorten it.",
                "research_query": "", "reply": "Shortened the LinkedIn post.", "ask": none}
    if "more x posts" in message:
        cards = [{"id": "", "type": "x_post", "title": title, "audience": "Platform leads", "research_query": "",
                  "main_message": "Acme Widget is small and safe.", "date": "January 27", "image_idea": "", "notes": ""}
                 for title in ("Widget teaser", "Widget launch day")]
        return {"action": "add", "targets": [], "instruction": "", "research_query": "", "reply": "Adding two X posts.",
                "ask": none, "new_assets": cards}
    if "version 2" in message:
        return {"action": "edit", "targets": [{"asset": 2, "field": ""}], "instruction": "Go back to version 2.",
                "research_query": "", "reply": "I'll revert the LinkedIn post to version 2.", "ask": none}
    if "everywhere" in message:
        return {"action": "edit", "targets": [{"asset": n, "field": ""} for n in (1, 2, 3)],
                "instruction": "Make it shorter.", "research_query": "", "reply": "Changed all three.", "ask": none}
    if "tweak" in message:
        return {"action": "ask", "targets": [], "instruction": "", "research_query": "", "reply": "",
                "ask": {"question": "Which asset?", "options": ["The email", "The posts"]}}
    return {"action": "answer", "targets": [], "instruction": "", "research_query": "", "reply": "It goes out on the 26th.",
            "ask": none}


def memory(request: AiRequest) -> dict:
    said = request.prompt.task[-1].content.split("=== NEW MESSAGES ===", 1)[1].lower()
    if "never call it a platform" in said:
        return {"items": [{"text": "Never call Acme a platform.", "kind": "correction", "replaces": 0}]}
    return {"items": []}


def research_notes(request: AiRequest) -> dict:
    return {"findings": [
        {"finding": "The widget market grew 12% in 2026.", "quote": "The widget market grew 12% in 2026.", "page": 1,
         "date": "2026"},
        {"finding": "Made up.", "quote": "This sentence is on no page.", "page": 1, "date": ""},
    ]}


WRITING_REPLIES = {
    "asset_check": check,
    "edit_request": route,
    "memory_items": memory,
    "research_notes": research_notes,
    "campaign_record": lambda r: {"name": "Widget launch", "goal": "Launch the widget", "audience": "Platform leads",
                                  "angle": "Small and safe"},
    "writing_rules": lambda r: {"banned": [{"term": "synergy", "instead": "", "quote": "Write short sentences."}],
                                "old_names": [], "limits": []},
}


def writing_reply(request: AiRequest):
    schema = request.output_schema.name
    if schema in WRITING_REPLIES:
        return json.dumps(WRITING_REPLIES[schema](request))
    extra = request.output_schema.schema["properties"]
    if "fixed" in extra:
        return json.dumps(fix(request))
    if "changed" in extra:
        return json.dumps(edit_asset(request))
    return json.dumps(write(request))
