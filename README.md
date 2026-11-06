# Campaign agent

A local app where a marketer and an AI agent plan and write a campaign for a brand. Chat is on the left; the plan, the finished assets and the costs are on the right.

1. **Add a brand.** Upload a brand folder, or preload one from settings. The app reads it once: a card per document, single facts, which documents replace which, settled conflicts, image rules and a short brand summary. The Brand page then opens so you can check and correct what it learned.
2. **Paste a brief** into a new chat. The agent looks things up in the brand and asks only what it needs, one question at a time. If the brief contradicts the brand's rules, it pushes back and quotes the source.
3. **Review the plan.** Each asset is a card: emails, LinkedIn and X posts, blog posts, landing pages. Where outside facts help, the agent searches the web while planning and shows each finding with its link and date. Change the plan by chat or on the cards, remove findings you don't want, and check the image types the brief rules out (each can be allowed again), then press **Approve plan**. Nothing is written before that.
4. **Assets are written,** a few at a time, each in its own AI call with an image from the library. Each one is checked: free rule checks first, then an AI check of claims and tone. Anything found is fixed once automatically, and whatever is left shows as a warning. The right panel shows each asset the way it would really look.
5. **Edit** by chat ("shorten the second post"), which rewrites only that asset or field, or type straight into an asset, which costs nothing. Every change is a version, with Undo and Compare.
6. **Memory.** Corrections and preferences you give in chat are remembered for the brand's next campaigns, with an Undo note. The Memory page shows core memory and campaign history.

Every AI call is logged with its tokens, cache use and cost. **View prompt** shows exactly what was sent. The **Costs** tab breaks a campaign down by stage, asset and edit, and lists every call with its share read from the cache.

## Run it

You need Docker and an OpenAI API key.

```bash
cp .env.example .env
```

Fill in `OPENAI_API_KEY` in `.env`. `FIRECRAWL_API_KEY` is optional; without it, plans use brand documents only. Then start everything:

```bash
docker compose up
```

Open http://localhost:5173 and add a brand with **+ Add brand**, choosing the brand folder. Reading the sample brand (84 documents, 133 images) takes about 15 minutes and costs about $1.75. Reading is done once, and later updates re-read only changed files.

To preload a brand on first start instead, set `BRAND_DIR` in `.env` to the folder (relative to `.env`), and `BRAND_EXCLUDE` to any subfolders that aren't brand material, such as `briefs`.

## Settings (`.env`)

| Setting | What it is |
|---|---|
| `OPENAI_API_KEY` | Required for every AI call. |
| `FIRECRAWL_API_KEY` | Optional. Web research while planning. |
| `BRAND_DIR`, `BRAND_NAME`, `BRAND_EXCLUDE` | Optional. A brand folder to read on first start, its name, and paths inside it to skip. |
| `MODEL_SMALL`, `MODEL_MEDIUM`, `MODEL_LARGE`, `MODEL_EMBEDDING` | The models. Every AI job asks for a size, so swapping a model is a one-line change. Prices are in `backend/app/ai/pricing.py`. |

To start from scratch, remove the volumes:

```bash
docker compose down -v
```

## Reproducing the cost numbers

With the app running, this runs briefs end to end with the real key. It answers questions with the agent's suggestion, approves, waits for the assets and makes one typical edit. It saves the chat, assets and costs under `backend/data/runs/`, and prints the table used in [COSTS.md](COSTS.md). A brief that fails is recorded as failed, and the run goes on with the next one.

The sample briefs are in the brand pack's `briefs/` folder. The container sees the brand folder at `/preload-brand` when `BRAND_DIR` is set in `.env`, so set `BRAND_DIR` to the brand pack and `BRAND_EXCLUDE=briefs` (the briefs must not be read as brand documents), then:

```bash
docker compose exec backend uv run python scripts/run_briefs.py /preload-brand/briefs
```

A folder runs every `.md` file in it. Brief files can also be put under `backend/` (it is mounted at `/app`) and named one by one. To paste briefs instead, pass `-` and separate them with a line of `=====`.

## Tests

```bash
docker compose exec backend uv run pytest
```

The tests drive the whole API with a fake AI and a fake web search, against a real Postgres test database. Small test brands are made up inside the tests, so nothing is tuned to the sample brand.

Lint the backend with ruff (settings in `backend/pyproject.toml`):

```bash
docker compose exec backend uv run ruff check app tests scripts
```

The frontend's type check: `cd frontend && npm run typecheck`.

## Where things are

- `backend/app/brand/`: reading a brand folder, conflicts, images, the Brand page.
- `backend/app/campaign/`: the agent, research, writing, checks, edits, costs. The chat runs through `service.py`, which hands each stage to `planning.py`, `asset_chat.py` or `remembering.py`.
- `backend/app/memory/`: core memory and campaign history.
- `backend/app/ai/`: the one path to OpenAI, with logging, prices and cache points.
- `frontend/src/`: the React app.
- `docs/SPEC.md` and `docs/tickets/`: what was built and in what order. [DECISIONS.md](DECISIONS.md) explains why.

The AI call log is also written to `/data/logs/ai_calls.jsonl` in the backend container:

```bash
docker compose exec backend tail -n 1 /data/logs/ai_calls.jsonl
```
