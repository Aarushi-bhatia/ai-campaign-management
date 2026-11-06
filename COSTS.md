# Costs

## Per brief

| Brief | Questions | Assets | AI calls | Tokens in | Read from cache | Cache hit rate | Tokens out | Firecrawl credits | Total cost | Time |
|---|---|---|---|---|---|---|---|---|---|---|
| 1. Leashgate launch (detailed, 11 assets listed) | 0 | 11 | 54 | 722.2k | 297.0k | 41% | 23.8k | ~4 (1 search) | **$0.89** | 5.9 min |
| 2. Awareness push (vague) | 0 | 3 | 25 | 209.4k | 95.6k | 46% | 6.8k | 0 | **$0.26** | 2.2 min |
| 3. Regulated teams (contains false claims) | 2 | 5 | 34 | 355.0k | 169.8k | 48% | 13.9k | 0 | **$0.42** | 3.5 min |

Each run covers the whole brief: questions, plan, writing, checks and one typical edit. Total cost is the OpenAI cost. A web search fetches up to 4 pages, at about 1 Firecrawl credit each.

| Brief | Questions + plan | Research | Writing + images | Checks + fixes |
|---|---|---|---|---|
| 1. Leashgate launch | $0.24 | $0.001 | $0.38 | $0.23 |
| 2. Awareness push | $0.11 | none | $0.09 | $0.04 |
| 3. Regulated teams | $0.16 | none | $0.14 | $0.11 |

## A typical edit

**$0.017–$0.035.** A chat edit is three calls: one finds the asset and field meant, one rewrites only that, and one re-checks it. The edit was "Make the first LinkedIn post shorter, about half the length":

| Brief | Calls | Tokens in | Read from cache | Cache hit rate | Tokens out | Cost |
|---|---|---|---|---|---|---|
| 1. Leashgate launch | 3 | 40.0k | 12.1k | 30% | 494 | **$0.035** |
| 2. Awareness push | 3 | 29.3k | 16.8k | 57% | 562 | **$0.017** |
| 3. Regulated teams | 3 | 31.8k | 17.6k | 55% | 646 | **$0.019** |

An edit the asset already meets costs one call, which replies instead of editing. A hand edit typed into the asset costs **$0**.

## Onboarding a brand

Adding a brand costs more than a brief, but only once. Reading the sample brand (84 documents, 133 images) cost **$1.63** and took about 15 minutes. Every campaign for that brand then reuses what was read, so the cost spreads across all of them: over ten briefs, it adds about $0.16 to each. When the brand's documents change, only the changed files are read again.
