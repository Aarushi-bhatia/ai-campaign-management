# Costs

## Per brief

| Brief | Assets | AI calls | Tokens in | Read from cache | Cache hit rate | Tokens out | Firecrawl credits | Total cost | Time |
|---|---|---|---|---|---|---|---|---|---|
| 1. Leashgate launch (detailed, 11 assets listed) | 11 | 54 | 718.0k | 299.2k | 42% | 27.2k | ~4 (1 search) | **$0.91** | 5.3 min |
| 2. Awareness push (vague) | 3 | 26 | 249.3k | 107.4k | 43% | 8.3k | 0 | **$0.31** | 2.4 min |
| 3. Regulated teams (contains false claims) | 5 | 36 | 351.8k | 164.4k | 47% | 13.9k | 0 | **$0.42** | 3.3 min |

Each run covers the whole brief: questions, plan, writing, checks and one typical edit. Total cost is the OpenAI cost. A web search fetches up to 4 pages, at about 1 Firecrawl credit each.

| Brief | Questions + plan | Research | Writing + images | Checks + fixes |
|---|---|---|---|---|
| 1. Leashgate launch | $0.25 | $0.001 | $0.39 | $0.23 |
| 2. Awareness push | $0.13 | none | $0.10 | $0.07 |
| 3. Regulated teams | $0.16 | none | $0.14 | $0.11 |

## A typical edit

**$0.017–$0.036.** A chat edit is three calls: one finds the asset and field meant, one rewrites only that, and one re-checks it. The edit was "Make the first LinkedIn post shorter, about half the length":

| Brief | Calls | Tokens in | Read from cache | Cache hit rate | Tokens out | Cost |
|---|---|---|---|---|---|---|
| 1. Leashgate launch | 3 | 41.0k | 12.2k | 30% | 405 | **$0.036** |
| 2. Awareness push | 3 | 29.6k | 16.8k | 57% | 497 | **$0.017** |
| 3. Regulated teams | 3 | 32.4k | 17.6k | 54% | 581 | **$0.019** |

An edit the asset already meets costs one call, which replies instead of editing. A hand edit typed into the asset costs **$0**.

## Onboarding a brand

Adding a brand costs more than a brief, but only once. Reading the sample brand (84 documents, 133 images) cost **$1.63** and took about 15 minutes. Every campaign for that brand then reuses what was read, so the cost spreads across all of them: over ten briefs, it adds about $0.16 to each. When the brand's documents change, only the changed files are read again.
