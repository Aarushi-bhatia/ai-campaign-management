# 10: Cost panel, run script and write-ups

**What to build:** The user can see what a campaign and an edit cost, including how much came from the cache. A script runs sample briefs against the real AI and produces the cost numbers for COSTS.md. The README explains how to run the app, and DECISIONS.md explains the key choices. See docs/SPEC.md, "Cost reports" and "Prompt caching".

**Blocked by:** 06, 08, 09

**Status:** done. See COSTS.md, DECISIONS.md and README.md.

- [x] A cost panel per campaign shows totals per stage (questions, plan, research, writing per asset, checks, edits)
- [x] The cache hit rate shows per step and per campaign
- [x] The top bar shows the running cost of the current campaign
- [x] The brand reading cost shows separately
- [x] Cache control fits the models in use. On GPT-5.6 and later the default cache point is the end of the latest message, so every call over 1,024 tokens writes its whole prompt at 1.25× input. Set an explicit cache point after the fixed part, avoid cache writes on one-off calls, and weigh the 30-minute (1.25×) against the 12-hour (2.5×) lifetime with real numbers. See docs/model-trial.md.
- [x] Test: the fixed prompt part is exactly the same across calls for one brand
- [x] A run script takes pasted brief texts, runs them end to end with the real key (including one typical edit), and saves assets, cost per step, cache hit rate and edit cost
- [x] COSTS.md: tokens, cost and cache hit rate for each brief, plus the cost of a typical edit
- [x] Final model check: run every sample brief through the configured models, inspect the plan, brand accuracy and assets, and settle the allocation in docs/model-trial.md, with the reasons, for DECISIONS.md
- [x] README.md: how to run with one command and what settings are needed
- [x] DECISIONS.md (1–3 pages): how the brand layer and memory work and why, how conflicts are handled, model choice per task and why, what was left out, where an AI tool led us wrong, what we'd do with two more weeks
