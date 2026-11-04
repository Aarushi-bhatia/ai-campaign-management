# 06: Research in the plan

**What to build:** While making the plan, the agent decides for each asset whether outside research would help. If it would, it searches the web right then (through Firecrawl) and shows the findings with their source links and dates on the plan cards. The user can remove a finding or ask for a better source before approving. Approved findings are saved with the campaign and reused by every asset that needs them. See docs/SPEC.md, "Web research client".

**Blocked by:** 05

**Status:** done. Tried with the real Firecrawl key on brief 1 (see COSTS.md).

- [x] A single web research client handles search and page reading, with a fake for tests
- [x] Long pages are boiled down to short notes by a small model before use
- [x] Research is decided per asset during planning, not during writing or edits
- [x] Findings show on plan cards with source link and date
- [x] The user can remove a finding, or ask for a better source, before approval
- [x] Approved findings are saved with the campaign and shared by all assets that need them; the same search is not run twice
- [x] Brand documents always beat the web on product facts, pricing and guidelines
- [x] Edits never search the web unless the user asks directly
- [x] Research cost shows as its own stage in the call log
- [x] API test: a plan with research shows findings; removing one keeps it out of the approved set
