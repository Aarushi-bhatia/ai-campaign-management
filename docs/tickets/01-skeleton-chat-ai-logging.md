# 01: Skeleton: chat that talks to AI, with logging and "View prompt"

**What to build:** One command starts the whole app. A user opens it in the browser, types a message in the chat, and gets a reply from OpenAI. Every AI call is logged with its step label, model, tokens in and out, cached tokens, cost and time. A "View prompt" button on each reply shows the exact text sent and the reply received. This ticket also sets up the single AI client every later ticket uses, and a fake version of it for tests. See docs/SPEC.md.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] `docker compose up` starts Postgres (with pgvector), the backend and the frontend; code changes reload automatically
- [x] An example settings file lists every needed setting (OpenAI key, Firecrawl key, optional preload brand folder, model names)
- [x] All model names are set in one config place, grouped by size (small, medium, large, embedding)
- [x] The screen layout exists: left sidebar, chat in the middle, empty right panel, top bar
- [x] Typing a message returns an AI reply in the chat
- [x] Every AI call goes through one AI client that takes a step label, model size and prompt parts in a fixed order (fixed part, campaign part, task part)
- [x] Every call is saved with step, model, tokens in/out, cached tokens, cost, time, exact prompt and reply, and is also written to a log file
- [x] "View prompt" shows the exact prompt and reply for any call
- [x] A fake AI client with scripted replies can replace the real one in tests
- [x] API tests run against a Postgres test database using the fake AI client
