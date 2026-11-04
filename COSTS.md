# Costs

Measured on 2026-11-04 by running the three sample briefs end to end against the real OpenAI and Firecrawl keys, with the run script:

```bash
docker compose exec backend uv run python scripts/run_briefs.py data/briefs/*.md
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
| 1. Leashgate launch (detailed, 11 assets listed) | 1 | 11 | **$0.66** | 57% | $0.25 | $0.001 | $0.32 | $0.08 | **$0.018** | 4.0 min |
| 2. Awareness push (vague) | 2 | 4 | **$0.28** | 47% | $0.12 | none | $0.12 | $0.02 | **$0.018** | 1.6 min |
| 3. Regulated teams (contains false claims) | 3 | 5 | **$0.34** | 52% | $0.16 | none | $0.14 | $0.04 | **$0.010** | 2.2 min |

The cache hit rate is the share of input tokens read from the cache. In brief 1, one of the 11 assets (the landing page) failed on the first try. The model wrote a sentence about a clashing image before its JSON, and the app couldn't read the reply. Replies are now read past such a sentence, and the brief's own image rules now reach the image picker (that clash was the cause). **Write again** then produced the page for $0.05, with a cleared image and no warnings. That retry is not in the table. Every other asset came out with no warnings left. The automatic fix changed one asset in brief 1 and two in brief 3 (for example, adding "Wickhold" to a product's first mention, as the naming rules require). Brief 1 ran one web search while planning, and its blog posts cite the approved finding.

**By model,** across the three briefs: Sol $1.06 (41 calls), Terra $0.23 (49 calls), Luna $0.002 (10 calls), embeddings under $0.001. Sol does the work a marketer judges (planning and writing every asset), so it is about 80% of the cost. That was the deliberate choice: see [DECISIONS.md](DECISIONS.md).

## Where the money goes, brief 1

| Stage | Calls | Cost | Cached |
|---|---|---|---|
| Questions (brief review, with brand lookups) | 6 | $0.123 | 73% |
| Plan | 3 | $0.124 | 50% |
| Web research notes | 1 | $0.001 | 0% |
| Image choice | 8 | $0.030 | 73% |
| Writing (one Sol call per asset) | 11 | $0.295 | 40% |
| Checks and one fix | 12 | $0.076 | 59% |
| Edit (router and the edit itself; its re-check is under checks) | 2 | $0.014 | 44% |
| Memory and the campaign record | 3 | $0.001 | 75% |

An average asset costs $0.026 to write: about 13.9k tokens in and 650 out. About 4.7k of the input is shared by every asset of a campaign and is read from the cache. The other ~9k is the asset's own channel rules, facts and image, which differ every time. That is why writing caches less than the other steps.

## A typical edit

**$0.010–$0.018.** A chat edit is three Terra calls: one finds the asset and field meant, one rewrites only that, and one re-checks it. A hand edit typed into the asset costs **$0**: it runs only the free checks. "Check again" after a hand edit costs about **$0.006**.

## One-off brand costs

Reading the sample brand (84 documents, 133 images, about 3,000 facts) once costs about **$1.75**. It is done once per brand and shared by every campaign, and an update re-reads only changed files. The brand's writing rules (banned words, retired names, length limits) are worked out once, at the first campaign, for **$0.025**.

## What caching changed

- **Cache points are placed by hand.** Left to itself, the API caches up to the end of every prompt, so each one-off task was also written to the cache at 1.25× input. Now only the shared start is marked: the fixed part, plus the campaign part when several calls share it. A one-off call pays no cache-write premium for its task.
- **Tool loops keep the default.** Each round resends the previous round plus new tool results, so caching everything so far is right there. A first version marked tool loops by hand too. One brief review round then read 46k tokens with only 7k cached, at $0.08 a round. Putting tool loops back on the default brought brief 1 from $0.88 to $0.66, together with the two changes below.
- **Smaller lookups.** The channel-rules lookup returned every rule's proving sentence, 15–20k characters per channel. It now returns just the rule and its source.
- **Checks see the campaign.** The AI check first got only the brand facts, not the brief, so it flagged brief-approved facts and the fix deleted them. Brief 1 had 2–8 warnings per asset and about $0.19 of checks and fixes. With the approved campaign in its cached middle part, it had none and $0.08.
- **The first asset is written alone,** then the rest three at a time. The others then start with the shared part already cached, instead of three calls all missing at once. On a re-run of brief 2 this brought the total from $0.28 to $0.24.
- **Lifetime.** The 30-minute lifetime is used. A campaign's calls happen within minutes of each other, so the 12-hour lifetime (2.5× to write) would cost more for no extra hits.

## Not counted above

- Firecrawl credits: one search per research query, with page text, about 1 credit per result.
- Earlier runs while building and tuning: about $2.00 on the current key (agent tuning and two earlier brief 1 runs). The brand was read before that, on an earlier key.
