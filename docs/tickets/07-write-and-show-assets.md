# 07: Write and show all asset types

**What to build:** After the plan is approved, each asset is written in its own AI call with only what it needs, and with an image picked from the library. While writing, each card shows its state, the text appears as it's written, and the chat shows short status lines. Finished assets show on the right the way they'd look in real life: an inbox email, a LinkedIn feed post, an X post, a blog page, a landing page. See docs/SPEC.md, "Asset writer".

**Blocked by:** 04, 05

**Status:** done, except live text as it's written: cards show their state and the text arrives whole (the spec's first cut). Live updates are by polling, not an event stream.

- [x] Each asset is written in one AI call that fills a fixed set of fields for its type:
  - Email: sender, subject, preview text, body sections, button text and link, image
  - LinkedIn and X: author, text, image, hashtags
  - Blog: title, author, date, hero image, body
  - Landing page: ordered sections such as top banner, features, proof, call to action
- [x] The writing prompt uses the fixed order: fixed part, then campaign (brief, plan, scoped rules), then this asset's spec, channel rules, relevant facts, approved research and chosen image
- [x] The writer may cite only approved research sources
- [x] An image and alt text are picked per asset, or "nothing fits" is shown with a suggestion
- [x] A few assets are written at once, in plan order
- [x] Each card shows Waiting → Writing → Done
- [ ] Text appears live for the asset being viewed (cut: the text arrives whole)
- [x] The chat shows status lines (what was looked up, which image was picked)
- [x] Realistic previews exist for email, LinkedIn, X, blog and landing page
- [x] The user can switch between assets on the right
- [x] Each asset's exact writing prompt is viewable through "View prompt"
- [x] API test: approving a plan produces every asset with its fixed fields
- [x] Model check: run one sample brief end to end with the configured models, then inspect the plan, brand accuracy (facts, names, claims, voice) and every asset. Confirm or change the allocation in docs/model-trial.md. Don't trade content quality for tokens.
