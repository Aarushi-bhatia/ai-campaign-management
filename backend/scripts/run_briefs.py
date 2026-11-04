"""Runs sample briefs end to end against the running app and its real AI key, and saves what came out.

For each brief: paste it into a new chat, answer any questions with the agent's suggested option,
approve the plan, wait for the assets, then make one typical chat edit. Saves the chat, plan, assets and
cost report per brief, and prints a table for COSTS.md.

    uv run python scripts/run_briefs.py brief-1.md brief-2.md      # brief files
    uv run python scripts/run_briefs.py - < briefs.txt              # pasted briefs, split by a line of =====

The app must be running (docker compose up). APP_URL defaults to http://localhost:8000.
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

APP = os.environ.get("APP_URL", "http://localhost:8000")
OUT = Path(os.environ.get("RUN_DIR", "data/runs")) / datetime.now().strftime("%Y%m%d-%H%M%S")
WAIT_SECONDS = 1800
EDITS = {
    "linkedin_post": "Make the first LinkedIn post shorter, about half the length.",
    "x_post": "Make the first X post punchier.",
    "email": "Rewrite the subject line of the first email to be more specific.",
    "blog_post": "Make the opening paragraph of the blog post shorter.",
    "landing_page": "Make the landing page's hero heading shorter.",
}

client = httpx.Client(base_url=APP, timeout=1800)


def call(method: str, path: str, **kwargs):
    response = client.request(method, path, **kwargs)
    if response.status_code >= 400:
        raise SystemExit(f"{method} {path} failed: {response.status_code} {response.text}")
    return response.json() if response.content else None


def open_question(messages: list[dict]) -> dict | None:
    for message in reversed(messages):
        if message["kind"] == "question":
            return None if message["data"].get("answer") else message["data"]
    return None


def run(name: str, brief: str) -> dict:
    started = time.monotonic()
    chat_id = call("POST", "/api/chats")["id"]
    print(f"\n[{name}] chat {chat_id}: pasting the brief…", flush=True)
    call("POST", f"/api/chats/{chat_id}/messages", json={"content": brief})
    answers = []
    while (chat := call("GET", f"/api/chats/{chat_id}"))["campaign"]["stage"] == "asking":
        question = open_question(chat["messages"])
        option = question["options"][0]["value"]
        answers.append({"question": question["question"], "answer": option})
        print(f"[{name}] Q: {question['question']}\n[{name}] A: {option}", flush=True)
        call("POST", f"/api/chats/{chat_id}/answer", json={"question_id": question["id"], "answer": option})
    plan = chat["campaign"]["plan"]
    print(f"[{name}] plan: {len(plan['assets'])} assets, {len(chat['campaign']['research'])} research findings. Approving…",
          flush=True)
    call("POST", f"/api/chats/{chat_id}/approve")
    deadline = time.monotonic() + WAIT_SECONDS
    while call("GET", f"/api/chats/{chat_id}")["campaign"]["stage"] != "done":
        if time.monotonic() > deadline:
            raise SystemExit(f"[{name}] writing didn't finish in {WAIT_SECONDS}s")
        time.sleep(5)
    assets = call("GET", f"/api/chats/{chat_id}/assets")
    edit = next((EDITS[a["type"]] for a in assets if a["type"] in ("linkedin_post", "x_post")), EDITS[assets[0]["type"]])
    print(f"[{name}] {sum(a['state'] == 'done' for a in assets)} of {len(assets)} assets written. Edit: {edit}", flush=True)
    reply = call("POST", f"/api/chats/{chat_id}/messages", json={"content": edit})
    costs = call("GET", f"/api/chats/{chat_id}/costs")
    # The edit's own calls, as its message lists them: the totals before and after also caught the memory call
    # that runs after the reply.
    edit_cost = sum(m["data"].get("cost_usd", 0) for m in reply if m["kind"] == "edit")
    chat = call("GET", f"/api/chats/{chat_id}")
    folder = OUT / re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "brief.md").write_text(brief)
    for file, data in (("chat.json", chat), ("assets.json", call("GET", f"/api/chats/{chat_id}/assets")), ("costs.json", costs)):
        (folder / file).write_text(json.dumps(data, indent=1, ensure_ascii=False))
    failed = [a["title"] for a in assets if a["state"] != "done"]
    if failed:
        print(f"[{name}] NOT WRITTEN: {', '.join(failed)}", flush=True)
    result = {
        "brief": name, "chat_id": chat_id, "questions": len(answers), "answers": answers, "assets": len(assets),
        "failed": failed,
        "warnings": sum(len(a["warnings"]) for a in call("GET", f"/api/chats/{chat_id}/assets")),
        "auto_fixed": sum(1 for a in assets if a["fixed"]), "cost_usd": costs["total"]["cost_usd"],
        "cache_hit_rate": costs["total"]["cache_hit_rate"], "tokens_in": costs["total"]["tokens_in"],
        "stages": {s["stage"]: s["cost_usd"] for s in costs["stages"]}, "edit": edit,
        "edit_reply": reply[-1]["content"], "edit_cost_usd": edit_cost, "minutes": round((time.monotonic() - started) / 60, 1),
    }
    (folder / "result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
    print(f"[{name}] done in {result['minutes']} min, ${result['cost_usd']:.3f}, saved to {folder}", flush=True)
    return result


def briefs_from(args: list[str]) -> list[tuple[str, str]]:
    if args == ["-"]:
        texts = [t.strip() for t in re.split(r"^={5,}\s*$", sys.stdin.read(), flags=re.MULTILINE) if t.strip()]
        return [(f"brief {i}", t) for i, t in enumerate(texts, start=1)]
    return [(Path(a).stem, Path(a).read_text()) for a in args]


def table(results: list[dict]) -> str:
    rows = ["| Brief | Questions | Assets (written) | Total cost | Cache hit rate | Plan | Research | Writing | Checks | Typical edit |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s = r["stages"]
        rows.append(f"| {r['brief']} | {r['questions']} | {r['assets']} ({r['assets'] - len(r['failed'])}) | ${r['cost_usd']:.3f} | {r['cache_hit_rate']:.0%} | "
                    f"${s.get('Questions', 0) + s.get('Plan', 0):.3f} | ${s.get('Research', 0):.3f} | "
                    f"${s.get('Writing', 0) + s.get('Images', 0):.3f} | ${s.get('Checks', 0):.3f} | ${r['edit_cost_usd']:.4f} |")
    return "\n".join(rows)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    results = [run(name, text) for name, text in briefs_from(sys.argv[1:])]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "table.md").write_text(table(results) + "\n")
    print("\n" + table(results))
