# Campaign agent

A marketer adds a brand folder, pastes a brief, and the agent asks what it needs, plans the campaign, writes it after approval and takes edits by chat. Every AI call can be opened with **View prompt**, and the **Costs** tab shows a campaign's cost by stage, asset and edit.

## Run it

You need Docker, an OpenAI API key and a Firecrawl API key.

```bash
cp .env.example .env
```

Fill in `OPENAI_API_KEY` and `FIRECRAWL_API_KEY` in `.env`. Then start it one of two ways.

**Reading the brand yourself.** Start the app, then add the brand folder in it:

```bash
docker compose up
```

**With the sample brand already read (quickest).** A separate seed step loads Wickhold from `backend/seed/wickhold.tar.gz` before the app starts, so there is nothing to wait for or pay for:

```bash
SEED=1 docker compose up
```

To read it yourself, open http://localhost:5173, click the **Brand** card at the bottom left, then **Add a brand**, and choose the brand folder. Reading the sample brand (84 documents, 133 images) takes about 15 minutes and costs about $1.63. It is read once; later updates re-read only changed files. You can add more brands the same way either way.

Either way, the Brand page opens once so you can see what was read.

The seed only loads into an empty app. To switch from one way to the other, first remove everything (brands, chats and memory):

```bash
docker compose down -v
```

## Tests

```bash
docker compose exec backend uv run pytest
```

The tests drive the whole API with a fake AI and a fake web search, against a real Postgres test database.

## Where things are

- `backend/app/brand/`: reading a brand folder, conflicts, images, the Brand page.
- `backend/app/campaign/`: the agent, research, writing, checks, edits, costs. The chat runs through `service.py`, which hands each stage to `planning.py`, `asset_chat.py` or `remembering.py`.
- `backend/app/memory/`: core memory and campaign history.
- `backend/app/ai/`: the one path to OpenAI, with logging, prices and cache points.
- `frontend/src/`: the React app.
- [DECISIONS.md](DECISIONS.md) explains the design; [COSTS.md](COSTS.md) has the measured costs.
