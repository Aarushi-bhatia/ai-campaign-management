# Costs

Measured on 2026-11-04 by running the three sample briefs end to end against the real OpenAI and Firecrawl APIs, with the run script. Later changes (asking before the brief changes a brand rule, clearer edit routing, skipping edits a piece already meets) were not re-measured; none adds an AI call, and skipped edits cost less.

```bash
docker compose exec backend uv run python scripts/run_briefs.py /preload-brand/briefs
```

For each brief, the script pastes it into a new chat and answers any questions with the agent's suggested option. It approves the plan, waits for every asset to be written, checked and fixed, then makes one typical chat edit ("Make the first LinkedIn post shorter, about half the length"). Prices are OpenAI's Standard tier, per million tokens:

| Model | Input | Cached input | Cache write | Output |
|---|---|---|---|---|
| `gpt-6.1-sol` (large) | $2.00 | $0.10 | $2.50 | $10.00 |
| `gpt-6.1-terra` (medium) | $1.00 | $0.05 | $1.25 | $5.00 |
| `gpt-6-luna` (small) | $0.10 | $0.01 | $0.125 | $0.50 |
| `text-embedding-3-small` | $0.02 | | | |

## Per brief

| Brief | Questions | Assets | AI calls | Tokens in | Read from cache | Cache hit rate | Tokens out | Total cost | Time |
|---|---|---|---|---|---|---|---|---|---|
| 1. Leashgate launch (detailed, 11 assets listed) | 0 | 11 | 54 | 722.2k | 297.0k | 41% | 23.8k | **$0.89** | 5.9 min |
| 2. Awareness push (vague) | 0 | 3 | 25 | 209.4k | 95.6k | 46% | 6.8k | **$0.26** | 2.2 min |
| 3. Regulated teams (contains false claims) | 2 | 5 | 34 | 355.0k | 169.8k | 48% | 13.9k | **$0.42** | 3.5 min |

The totals include the typical edit. The cache hit rate is the share of input tokens read from the cache. Every asset was written on the first try.

Where each brief's cost went:

| Brief | Questions + plan | Research | Writing + images | Checks + fixes |
|---|---|---|---|---|
| 1. Leashgate launch | $0.24 | $0.001 | $0.38 | $0.23 |
| 2. Awareness push | $0.11 | none | $0.09 | $0.04 |
| 3. Regulated teams | $0.16 | none | $0.14 | $0.11 |

An average asset costs $0.031 to write: about 15.2k tokens in and 650 out. About 4.4k of the input is shared by every asset of a campaign and is read from the cache. The rest is the asset's own channel rules, facts and image, which differ every time. That is why writing caches less than the other steps.

Checks and fixes are a large share on briefs 1 and 3 because of warnings no brief can settle: the postal address and unsubscribe link in emails, and live URLs. The fix tries each one and rightly doesn't invent it, so they stay as warnings for a person to fill in (8, 4 and 8 left).

**By model,** across the three briefs:

| Model | Calls | Cost | Share |
|---|---|---|---|
| Sol | 38 | $1.03 | 66% |
| Terra | 58 | $0.52 | 34% |
| Luna | 7 | $0.002 | |
| Embeddings | 10 | under $0.001 | |

Sol does the work a marketer judges: planning and writing every asset. That was the deliberate choice: see [DECISIONS.md](DECISIONS.md).

## A typical edit

**$0.017–$0.035.** A chat edit is three Terra calls: one finds the asset and field meant, one rewrites only that, and one re-checks it. The edit was "Make the first LinkedIn post shorter, about half the length":

| Brief | Calls | Tokens in | Read from cache | Cache hit rate | Tokens out | Cost |
|---|---|---|---|---|---|---|
| 1. Leashgate launch | 3 | 40.0k | 12.1k | 30% | 494 | **$0.035** |
| 2. Awareness push | 3 | 29.3k | 16.8k | 57% | 562 | **$0.017** |
| 3. Regulated teams | 3 | 31.8k | 17.6k | 55% | 646 | **$0.019** |

Brief 1's edit cost the most because its first two calls read nothing from the cache. An edit whose asset already does what was asked costs one call, which replies instead of editing. The Costs tab shows each edit with exactly the calls it made, the same figure as the chat's "Edit cost" line.

A hand edit typed into the asset costs **$0**, because it runs only the free checks. "Check again" after a hand edit costs about **$0.006**.

## One-off brand costs

Reading the sample brand (84 documents, 133 images, about 3,000 facts) once costs about **$1.63**, measured on 2026-11-05 when the same folder was added again as a second brand (310 calls; fact extraction was $1.08 of it). It is done once per brand and shared by every campaign, and an update re-reads only changed files. The brand's writing rules (banned words, retired names, length and hashtag limits) are worked out at the first campaign for **$0.029**, and again only when the summary or those rules change.

## How caching is set up

- **Cache points are placed by hand,** on the shared start of each prompt only: the fixed part (rules, brand summary, memory), plus the campaign part when several calls share it. A one-off task pays no cache-write premium.
- **Tool loops keep the API's default caching.** Each round resends the previous one plus new tool results, so caching everything so far is right there.
- **The first asset is written alone,** then the rest three at a time, so the others can start with the shared part already cached. It doesn't always work: on a later run, writing read only 11% from the cache. Making this reliable is still to do.
- **The 30-minute cache lifetime is used.** A campaign's calls happen within minutes of each other, so the 12-hour lifetime (2.5× to write) would cost more for no extra hits.

## Not counted above

- Firecrawl credits: one search per research query, with page text, about 1 credit per result.
