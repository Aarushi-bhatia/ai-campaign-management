# Costs

Measured on 2026-11-04 (20:20 UTC, after the design-review fixes) by running the three sample briefs end to end against the real OpenAI and Firecrawl keys, with the run script:

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

| Brief | Questions | Assets | Total | Cache hit rate | Questions + plan | Research | Writing + images | Checks + fixes | Typical edit | Time |
|---|---|---|---|---|---|---|---|---|---|---|
| 1. Leashgate launch (detailed, 11 assets listed) | 0 | 11 | **$0.89** | 41% | $0.24 | $0.001 | $0.38 | $0.23 | **$0.035** | 5.9 min |
| 2. Awareness push (vague) | 0 | 3 | **$0.26** | 46% | $0.11 | none | $0.09 | $0.04 | **$0.017** | 2.2 min |
| 3. Regulated teams (contains false claims) | 2 | 5 | **$0.42** | 48% | $0.16 | none | $0.14 | $0.11 | **$0.019** | 3.5 min |

The cache hit rate is the share of input tokens read from the cache. Every asset was written on the first try.

- **Brief 3's false claims were caught before planning.** The agent asked to replace the "FedRAMP Authorized" headline with the approved SOC 2 Type II wording, and to swap a customer story that isn't approved for an approved one.
- **Brief 2 asked nothing this time,** where an earlier run asked two questions. It used three things the marketer had said before, from core memory; the model's own judgement varies between runs too.
- **Brief 1 ran one web search while planning.** Its blog posts cite the approved findings.

**Warnings left: 8, 4 and 8.** Almost all of them are details no brief gives, which a person has to supply before sending: the company's postal address and unsubscribe link in emails, and live URLs for the landing page and how-to posts. The writer leaves a placeholder such as "[Denver postal address]". An earlier run had the same placeholders, but its AI check didn't flag them. This run's check did. The automatic fix then tried each one and, rightly, didn't invent an address or a link. That is why checks and fixes cost more than before ($0.23 against $0.08 on brief 1; 8 fix calls instead of 1).

**By model,** across the three briefs:

| Model | Calls | Cost | Share |
|---|---|---|---|
| Sol | 38 | $1.03 | 66% |
| Terra | 58 | $0.52 | 34% |
| Luna | 7 | $0.002 | |
| Embeddings | 10 | under $0.001 | |

Sol does the work a marketer judges: planning and writing every asset. That was the deliberate choice: see [DECISIONS.md](DECISIONS.md).

## Where the money goes, brief 1

| Stage | Calls | Cost | Cached |
|---|---|---|---|
| Questions (brief review, with brand lookups) | 4 | $0.118 | 56% |
| Plan | 3 | $0.123 | 51% |
| Web research notes | 1 | $0.001 | 0% |
| Image choice | 8 | $0.038 | 41% |
| Writing (one Sol call per asset) | 11 | $0.340 | 29% |
| Checks and fixes | 20 | $0.234 | 46% |
| Edit (the router and the edit itself; its re-check is under checks) | 2 | $0.030 | 0% |
| Memory and the campaign record | 2 | $0.001 | 0% |

An average asset costs $0.031 to write: about 15.2k tokens in and 650 out. About 4.4k of the input is shared by every asset of a campaign and is read from the cache. The rest is the asset's own channel rules, facts and image, which differ every time. That is why writing caches less than the other steps.

## A typical edit

**$0.017–$0.035.** A chat edit is three Terra calls: one finds the asset and field meant, one rewrites only that, and one re-checks it. On brief 1 those were $0.012, $0.018 and $0.005. The Costs tab shows each edit with exactly the calls it made, the same figure as the chat's "Edit cost" line. Earlier figures here took the difference in totals, which also caught the memory call after the edit.

A hand edit typed into the asset costs **$0**, because it runs only the free checks. "Check again" after a hand edit costs about **$0.006**.

## One-off brand costs

Reading the sample brand (84 documents, 133 images, about 3,000 facts) once costs about **$1.75**. It is done once per brand and shared by every campaign, and an update re-reads only changed files. The brand's writing rules (banned words, retired names, length and hashtag limits) are worked out at the first campaign for **$0.029**, and again only when the summary or those rules change.

## What caching changed

- **Cache points are placed by hand.** Left to itself, the API caches up to the end of every prompt, so each one-off task was also written to the cache at 1.25× input. Now only the shared start is marked: the fixed part, plus the campaign part when several calls share it. A one-off call pays no cache-write premium for its task.
- **Tool loops keep the default.** Each round resends the previous round plus new tool results, so caching everything so far is right there. A first version marked tool loops by hand too. One brief review round then read 46k tokens with only 7k cached, at $0.08 a round. Putting tool loops back on the default brought brief 1 from $0.88 to $0.66, together with the two changes below.
- **Smaller lookups.** The channel-rules lookup returned every rule's proving sentence, 15–20k characters per channel. It now returns just the rule and its source.
- **Checks see the campaign.** The AI check first got only the brand facts, not the brief, so it flagged brief-approved facts and the fix deleted them. Brief 1 had 2–8 warnings per asset and about $0.19 of checks and fixes. With the approved campaign in its cached middle part, it had none and $0.08.
- **The first asset is written alone,** then the rest three at a time. The others then start with the shared part already cached, instead of three calls all missing at once. On a re-run of brief 2 this brought the total from $0.28 to $0.24.
- **Lifetime.** The 30-minute lifetime is used. A campaign's calls happen within minutes of each other, so the 12-hour lifetime (2.5× to write) would cost more for no extra hits.

## Not counted above

- Firecrawl credits: one search per research query, with page text, about 1 credit per result.
- Earlier runs while building, tuning and checking fixes: about $6.20 on the current key. That covers agent tuning, two earlier full runs and small real-model checks of changed prompts. The brand was read before that, on an earlier key.
