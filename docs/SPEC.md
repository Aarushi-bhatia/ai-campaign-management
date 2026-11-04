# Spec: Brand-aware campaign agent

Status: ready-for-agent

## Problem Statement

A marketer wants to plan and write a campaign (social posts, blogs, landing pages, emails) with an AI agent. The brand's material is far too large to paste into a prompt: guidelines, messaging, product sheets, legal rules, past content, internal notes and an image library. It is also messy:

- Old and new versions of the same document both sit in the folder, and the file named "FINAL" may be the out-of-date one.
- Documents contradict each other. A sales deck may claim a certification that Legal says the company does not hold.
- Some material looks finished but is not approved, like a draft customer story.
- Some material is internal only and must never appear in public copy.
- Images carry free-text restrictions ("retired", "events only", "do not crop"), and some retired images look current.
- A campaign brief can itself be vague, or rest on wrong facts.

Today the marketer has to know all of this by heart. A generic AI tool will happily mix old and new rules, repeat false claims, pick banned images, and regenerate everything when asked to change one sentence. Nothing is remembered between campaigns, and there is no view of what each step cost.

## Solution

A local web app with chat on the left and the campaign on the right.

1. **Add a brand.** The marketer uploads a brand folder, or the app preloads one named in settings. The app reads it once. It writes a short card for each document, pulls out single facts, works out which documents replace which, settles conflicts with clear rules, and builds a short brand summary. The Brand page then opens so the marketer can review and correct what was learned.
2. **Paste a brief.** The agent looks up only the brand facts that matter. It asks questions only when something important is unclear, missing or wrong, one at a time with clickable options and a text box. When the brief contradicts the brand's rules, it pushes back with proof and suggests a fix.
3. **Review the plan.** The agent proposes a set of assets as cards: channel, audience, main message, date, image, research. Where outside research helps, it runs the search now and shows findings with sources. The marketer changes the plan by chat or directly on the cards, then approves it.
4. **Watch the assets get written.** Each asset is written in its own AI call with only what it needs, checked against the brand's rules, fixed once automatically if needed, and shown the way it looks in real life: an inbox email, a LinkedIn post, an X post, a blog page, a landing page.
5. **Edit.** "Shorten the second post" changes only that asset. Typing directly into an asset works too. Every edit is a new version with Undo and Compare.
6. **Start the next campaign.** The agent remembers general corrections, preferences and conflict decisions, and can look up past campaigns. The marketer can see and change all of it on the Memory page.
7. **See the cost.** Every AI call logs tokens, cache use, cost and the exact prompt sent, so the marketer knows what a campaign and an edit cost.

Nothing about any one brand is built in. Everything comes from the uploaded folder.

## User Stories

### Adding and updating a brand

1. As a marketer, I want to upload a brand folder from my computer, so that the agent can use my brand without me copying anything into prompts.
2. As a reviewer, I want the app to preload a brand folder named in the settings file, so that I can run it with one command and start straight away.
3. As a marketer, I want to see progress while the brand is being read, so that I know the app is working and roughly how long it will take.
4. As a marketer, I want the app to accept any folder of text documents and images, so that it works for brands whose folders are laid out differently.
5. As a marketer, I want the app to work even when there is no image info file, so that brands without neat metadata are still supported.
6. As a marketer, I want images with no description to be described automatically, so that they can still be found and chosen.
7. As a marketer, I want campaign briefs never to be read as brand documents, so that one campaign's instructions don't become permanent brand rules.
8. As a marketer, I want to update a brand by uploading new or changed files, so that the agent stays current as the brand changes.
9. As a marketer, I want an update to re-read only new or changed files, so that updates are quick and cheap.
10. As a marketer, I want a new document to be able to change the status of older documents, so that a newly added sheet saying "the old price list is wrong" takes effect without re-reading everything.
11. As a marketer, I want to see what reading the brand cost, kept apart from campaign costs, so that I understand the one-time setup cost.

### What the app learns about each document

12. As a marketer, I want each document labelled by type (rule, product facts, past example, template, persona, customer story, press, internal note), so that the agent treats a past blog post as an example and not as a rule.
13. As a marketer, I want each document's status (current, replaced, draft, archived, unknown) worked out, so that old versions are not used as if they were current.
14. As a marketer, I want every status and label backed by the exact sentence that proves it, so that I can trust it or correct it.
15. As a marketer, I want the app to say "unknown" rather than guess when no sentence supports a label, so that wrong guesses don't quietly shape the copy.
16. As a marketer, I want the owner of each document and their role (Legal, Brand, Sales and so on) recorded, so that the right team's word wins on its own topic.
17. As a marketer, I want each document marked safe or not safe to quote in public, so that internal sales notes can inform the agent without ending up in copy.
18. As a marketer, I want the app to learn old and new names for products and the company, so that facts under an old name still count and the old name is never used in new copy.
19. As a marketer, I want hints in file names like "FINAL" or "old" treated as hints only, so that a stale file called "FINAL" doesn't win.
20. As a marketer, I want single facts pulled out of rule and fact documents, each linked to its source sentence, so that conflicts can be spotted fact by fact rather than document by document.

### Conflicts between documents

21. As a marketer, I want contradictions between documents found automatically, so that I don't have to know them all myself.
22. As a marketer, I want conflicts settled in a fixed, clear order (a document that says it replaces another; the owner of the topic; approved over draft; newer over older; live over archive), so that the result is predictable.
23. As a marketer, I want a one-line reason recorded for each decision, so that I can see why one document beat another.
24. As a marketer, I want a one-line note in the chat whenever the agent picks one document over another for the current campaign, so that I know what it relied on.
25. As a marketer, I want conflicts unrelated to the current campaign kept out of the chat, so that the chat stays focused.
26. As a marketer, I want truly unclear conflicts sent to me as a question only when they matter for the campaign, so that I'm not asked about things that don't affect my work.
27. As a marketer, I want my answer to a conflict question saved, so that the agent never asks the same thing again.
28. As a marketer, I want a brief to override documents only on the points it names, so that "the early access label comes off" doesn't also change claims, pricing or anything else.
29. As a marketer, I want the agent to refuse wrong facts in a brief, show the source that disproves them and suggest safe wording, so that a brief claiming a certification we don't hold doesn't produce false copy.
30. As a marketer, I want the agent to catch a brief asking to feature a customer who hasn't approved it, and suggest an approved alternative, so that we don't publish something legal hasn't cleared.

### Brand page

31. As a marketer, I want the Brand page to open automatically after a brand is first read, so that I review what was learned before starting a campaign.
32. As a marketer, I want a Brand entry in the sidebar, so that I can return to the brand details at any time.
33. As a marketer, I want a Documents tab with each document's type, status, owner, safe-to-quote flag and proving sentence, so that I can see how the agent sees my folder.
34. As a marketer, I want a Conflicts tab listing winner, loser and reason, so that I can check the agent's decisions.
35. As a marketer, I want a Brand summary tab showing the exact text sent to the AI, so that I know what the agent always has in mind.
36. As a marketer, I want an Images tab showing which images are blocked and why, so that I understand image choices.
37. As a marketer, I want to correct a document's status or type, so that I can fix the app's mistakes in one click.
38. As a marketer, I want to flip the winner of a conflict, so that my judgment beats the automatic rules when needed.
39. As a marketer, I want to edit the brand summary and image rules, so that I can shape what the agent always uses.
40. As a marketer, I want my Brand page corrections to survive future brand updates, so that I never have to fix the same thing twice.

### Briefs and questions

41. As a marketer, I want to start a campaign by pasting a brief into a new chat, so that I can work the way I already do.
42. As a marketer, I want one campaign per chat, so that memory, assets and costs stay clean per campaign.
43. As a marketer, I want the agent to ask nothing when the brief is clear, so that I'm not slowed down.
44. As a marketer, I want the agent to ask when something important (goal, audience, timing, product) is missing, so that a vague brief still produces a good plan.
45. As a marketer, I want the agent to ask when my own message is unclear, for example "make it better", so that it doesn't guess what I meant.
46. As a marketer, I want questions one at a time as a card with 2–4 clickable options and a text box, so that answering is quick but I can still say exactly what I want.
47. As a marketer, I want the suggested answer shown first on each question card, so that I can accept good defaults with one click.
48. As a marketer, I want at most 3–5 questions per round, so that the agent never interrogates me.
49. As a marketer, I want the agent never to ask what the brand folder, memory or brief already answers, so that questions feel worth answering.
50. As a marketer, I want anything the agent still had to guess listed under "Assumptions" in the plan, so that I can correct it before writing starts.

### Planning

51. As a marketer, I want the agent to propose a set of assets using only social posts (LinkedIn and X), blogs, landing pages and emails, so that the plan stays within our owned channels.
52. As a marketer, I want the agent to plan only for social networks the brand actually uses, so that it doesn't suggest channels we don't run.
53. As a marketer, I want the agent to say so when a brief's own asset list looks wrong, so that I get advice and not just obedience.
54. As a marketer, I want each planned asset shown as a card with type, channel, audience, main message, date, image and research points, so that I can review the plan at a glance.
55. As a marketer, I want to change the plan by chat ("drop the X post, add a customer email"), so that big changes are easy to ask for.
56. As a marketer, I want to delete a card, drag cards to reorder them and type into fields like date or audience, so that small changes are instant.
57. As a marketer, I want nothing written until I press "Approve plan", so that no money or time is spent on assets I don't want.
58. As a marketer, I want the agent to check campaign history while planning, so that it doesn't repeat recent angles or images.

### Research

59. As a marketer, I want the agent to decide per asset whether outside research is needed, so that a blog can get fresh data while a short post just uses brand facts.
60. As a marketer, I want needed research run while the plan is made, with findings and sources shown in the plan, so that I approve facts before they're used.
61. As a marketer, I want to remove a research finding or ask for a better source before approving, so that I control what outside facts we publish.
62. As a marketer, I want approved research saved with the campaign and reused by every asset that needs it, so that the agent doesn't search for the same thing twice.
63. As a marketer, I want every outside fact to keep its source link and date, so that each statistic can be traced.
64. As a marketer, I want the writer to cite only approved sources, and the check step to flag any other citation, so that the AI can't invent sources.
65. As a marketer, I want brand documents always to beat websites on product facts, pricing and guidelines, so that the web never overrides what the company has approved.
66. As a marketer, I want edits never to search the web unless I ask, so that changing one sentence stays quick, cheap and predictable.

### Images

67. As a marketer, I want blocked images (retired, events only, internal, person left the company, special rules) removed before any choice is made, so that a banned image is never picked.
68. As a marketer, I want each channel's image rules applied, for example no see-through images in email headers, so that images display properly where they're used.
69. As a marketer, I want the agent to pick the best remaining image for each asset and write alt text, so that assets come complete.
70. As a marketer, I want the asset to say "No suitable image, suggest a photo of X" when nothing fits, so that a weak match is never forced.
71. As a marketer, I want a brief's own image rules (for example "keep these screenshots off every asset") applied on top of the library rules, so that campaign-level image limits are respected.

### Writing and checking

72. As a marketer, I want each asset written in its own AI call with only what it needs, so that quality stays high and one asset can't bleed into another.
73. As a marketer, I want to see each asset's state (Waiting, Writing, Checking, Done), so that I know where things are.
74. As a marketer, I want to see the text appear as it's written for the asset I'm viewing, so that the wait feels shorter.
75. As a marketer, I want short status lines in the chat ("Looked up: email rules, approved claims"), so that I can see how the agent uses the brand.
76. As a marketer, I want every asset checked for banned words, unapproved claims, wrong product names, length limits, image rules and unapproved citations, so that problems are caught before I see them.
77. As a marketer, I want the agent to fix found problems once automatically and note what it fixed, so that I get clean copy and know what changed.
78. As a marketer, I want anything still wrong after the fix shown as a warning, so that problems are never hidden.
79. As a marketer, I want assets written a few at a time in parallel, so that a large campaign finishes quickly.

### Viewing assets

80. As a marketer, I want an email shown like an inbox view (sender, subject, preview text, body, button), so that I judge it as a reader would.
81. As a marketer, I want a LinkedIn post shown like a LinkedIn feed card, so that I see how it really reads.
82. As a marketer, I want an X post shown like an X post, so that length and line breaks look real.
83. As a marketer, I want a blog shown as a blog page (title, author, date, hero image, body), so that I can judge layout and flow.
84. As a marketer, I want a landing page shown as a web page with its sections in order, so that I can see the reader's path to the main action.
85. As a marketer, I want to switch between assets on the right while chatting on the left, so that I can work through them one by one.
86. As a marketer, I want a Copy button on each asset, so that I can move finished copy into the real tools.

### Editing

87. As a marketer, I want to edit an asset by chat ("shorten the second post"), so that changes are fast.
88. As a marketer, I want the agent to work out which asset and which part I mean, and ask if it's unclear, so that the right thing changes.
89. As a marketer, I want an edit to change only that asset, and only the named part when I name one, so that the rest of the campaign stays as approved.
90. As a marketer, I want a change across several assets ("use 'boundary' instead of 'guardrail' everywhere") applied asset by asset, with a list of what changed, so that wide edits stay controlled.
91. As a marketer, I want to type directly into an asset for small fixes, so that I don't need the AI for a typo.
92. As a marketer, I want hand edits checked by the free checks (banned words, lengths, names) and costing nothing, so that quick fixes stay quick and free.
93. As a marketer, I want a "Check again" button that runs the full AI check after hand edits, so that I can confirm bigger hand changes.
94. As a marketer, I want every edit saved as a new version, so that nothing is lost.
95. As a marketer, I want Undo and "Compare with previous" on each asset, so that I can see and reverse changes.
96. As a marketer, I want edited assets re-checked automatically, so that an edit can't introduce a rule break.
97. As a marketer, I want to see the cost of each edit, so that I know what changes cost.

### Memory

98. As a marketer, I want the agent to remember general corrections ("never call it a platform"), so that I don't repeat them every campaign.
99. As a marketer, I want the agent to remember my preferences on asset mix, tone and length, so that new plans start closer to what I want.
100. As a marketer, I want my conflict decisions and Brand page corrections remembered, so that settled questions stay settled.
101. As a marketer, I want campaign-only details, one-off edits and anything already in the brand folder not remembered, so that memory stays useful.
102. As a marketer, I want core memory kept small and near-duplicates merged, so that it stays cheap to load into every request.
103. As a marketer, I want a short record of each past campaign kept separately and looked up only while planning, so that history can grow without slowing normal work.
104. As a marketer, I want new memories saved automatically with a "Remembered: …" note and Undo, so that memory builds without extra clicks and mistakes are easy to reverse.
105. As a marketer, I want the agent to offer "Remember this?" when I keep making the same hand fix, so that repeated habits become rules.
106. As a marketer, I want a Memory page with two tabs (core memory and campaign history), showing each item's source chat, so that I can see what the agent knows and where it came from.
107. As a marketer, I want to edit, delete or pin any memory item, so that I stay in control.
108. As a marketer, I want memory kept per brand, so that two brands never mix.
109. As a marketer, I want a new chat to show which memories it used, so that I can see memory carry over.

### Cost and transparency

110. As a marketer, I want tokens in, tokens out, cached tokens, cost and time logged for every AI call, so that I know where money goes.
111. As a marketer, I want a cost panel per campaign with totals per stage (questions, plan, research, writing per asset, checks, edits), so that I know what a campaign costs.
112. As a marketer, I want the cache hit rate shown per step and per campaign, so that I can see caching working.
113. As a marketer, I want a running cost for the current campaign in the top bar, so that I always know the spend.
114. As a reviewer, I want a "View prompt" button on every AI call showing the exact text sent and the reply, so that I can see exactly what the model saw.
115. As a reviewer, I want all AI calls also written to a log file, so that I can inspect them outside the app.
116. As a reviewer, I want each asset's exact writing prompt viewable, so that I can see how the brand layer shapes one asset.

### Running the app

117. As a reviewer, I want to start everything with one command, so that I can try the app with no setup beyond Docker and a settings file.
118. As a reviewer, I want an example settings file listing every needed key, so that I know what to fill in.
119. As a developer, I want all model names in one settings place, so that swapping a model is a one-line change.
120. As a reviewer, I want a script that runs sample briefs with the real AI and saves results and costs, so that I can reproduce the cost numbers.

## Implementation Decisions

### Stack and running

- Backend in Python with FastAPI. Frontend in React with Vite. Database is PostgreSQL with the pgvector add-on for meaning-based search.
- Everything runs in Docker: one `docker compose up` starts the database, backend and frontend. Code changes reload automatically during development.
- Settings come from a `.env` file: OpenAI key, Firecrawl key, an optional preload brand folder, and model names. An example settings file is provided.
- Uploaded brand files are stored on a Docker volume next to the database. Deleting the volumes resets everything.

### Models

All model names live in one config place, grouped by size. Chosen models: small = `gpt-6-luna`, medium = `gpt-6.1-terra`, large = `gpt-6.1-sol` (trial results and open checks in docs/model-trial.md). The call log records the model that actually answered.

| Job | Size |
|---|---|
| Document cards, image restriction notes, image descriptions (vision) | Small |
| Single fact extraction, conflict reasons | Medium |
| Chat, questions, planning | Large |
| Writing assets | Large |
| Checking assets (claims) | Medium |
| Edits | Medium |
| Memory extraction, campaign summaries, research note-taking | Small |
| Meaning-based search | Small embedding model |

### Modules

Each is a deep module with a small interface:

1. **AI client.** The only path to OpenAI. It takes a step label, a model size, the prompt parts in fixed order and an optional output shape. It returns the reply and logs every call: step, campaign, model, tokens in/out, cached tokens, cost, time, exact prompt and reply. It sets a per-brand cache key. Tests swap in a fake that returns scripted replies.
2. **Web research client.** The only path to Firecrawl: search and read pages. It returns findings with source URL and date, boiled down to short notes by a small model. It is faked in tests.
3. **Brand reader.** It takes a brand's files and produces the brand knowledge, in four steps:
   1. Basic facts without AI: name, folder, length, headings, any labels at the top of the file, file-name hints.
   2. A document card per file (small model, fixed output shape): type, claimed status, date, owner and role, topics it rules on, safe to quote, documents it says it replaces, any "this beats that" statements, products/channels/customers mentioned. Every field carries its proving sentence or is "unknown".
   3. Sections split by headings, with search vectors. For rule, fact, customer story and press documents, single facts each have: subject, attribute, value, kind (must / must not / may / fact), scope (channel, audience, product), proving sentence and section.
   4. Comparing across documents: an old/new names table; the "replaces" links between documents; final document status; facts grouped by subject and attribute; conflicts settled by the agreed order with a one-line reason; unclear ones marked "needs a human". Then the brand summary (about 3–5 pages: voice, banned words, naming rules, standard company description, product one-liners) is built from the winning facts and the Brand page corrections.

   Results are saved by file content and prompt version, so only changed files are read again. Step 4 always re-runs over all saved cards. Brand page corrections are applied last and always win. Files the user marks as briefs are never read. Briefs only arrive pasted into chat.
4. **Image library.** It reads the optional image info file, or describes images with a vision model. A small model turns free-text restrictions into clear fields: usable, retired, allowed channels, blocked channels, no-crop, people rules, expired, reason. Its interface: given an asset type, channel, campaign image rules and the asset's message, it returns ranked usable images with alt text, or "nothing fits" with a suggestion. Blocking happens before ranking and always uses the fixed fields.
5. **Brand lookup tools.** These are what the agent calls at run time: search the brand, get a channel's rules, get approved claims for a topic, read one section, get conflicts for a topic, find images. Each tool only returns material that is current and allowed for its use. Not-safe-to-quote material is labelled as background.
6. **Campaign agent.** A fixed sequence of stages:

   ```
   brief_received → asking (optional, one question at a time, max 3–5)
     → planning (includes research) → plan_ready (user edits cards / chats)
     → approved → writing (per asset, parallel, small batches) → done
     → editing (per asset or field; loops back to done)
   ```

   A stage can't be skipped. Writing is only possible after approval. The question rules are those in user stories 43–50. Brief overrides are captured as scoped rules that apply to this campaign only. Wrong facts in a brief cause push-back with proof and a suggested fix, not silent compliance.
7. **Asset writer.** It writes one asset in one AI call. It fills a fixed field shape per asset type:
   - Email: sender, subject, preview text, body sections, button text and link, image
   - LinkedIn and X: author, text, image, hashtags
   - Blog: title, author, date, hero image, body
   - Landing page: ordered sections such as top banner, features, proof, call to action

   The prompt order is fixed: instructions and brand summary and core memory, then the campaign brief, plan and scoped rules, then this asset's spec, channel rules, relevant facts, approved research and the chosen image.
8. **Asset checker.** It has two layers:
   - **Free checks**, no AI: banned words, length limits from channel rules, product name rules, image rules, citations against the approved research list.
   - **AI check**: claims against approved claims, brand tone.

   After writing, both run and one automatic fix is tried. A note lists what was fixed, and anything still failing stays as a warning. Hand edits run the free checks only, unless the user presses "Check again".
9. **Asset versions.** Every write, fix, chat edit or hand edit saves a new version. It supports undo and compare with previous. A chat edit names an asset and optionally a field, and only that is rewritten.
10. **Memory.** It has two stores per brand:
    - **Core memory:** capped around 50 items, near-duplicates merged, always loaded into the fixed prompt part.
    - **Campaign history:** one short record per campaign (name, goal, audience, assets, main angle, images used, dates), looked up only by the planning stage.

    Items are suggested by a small model at the end of a chat and when the user corrects the agent, then auto-saved with an Undo note. Each item keeps its source chat and can be pinned, edited or deleted.
11. **Cost reports.** These total the AI call log per campaign, per stage, per asset and per edit, plus a separate brand-reading total and the cache hit rate.

### Prompt caching

- Every request is built in the same order: the fixed part first (instructions, brand summary, core memory, identical across calls for a brand), then the campaign part, then the changing task last. Nothing that changes per call (times, IDs) goes in the fixed part.
- OpenAI caches long matching starts automatically. A per-brand cache key is sent to raise hit rates, and cached tokens are read from every reply.
- A longer cache time is used if the chosen models support it.

### API and live updates

- The HTTP API covers:
  - brands: upload, update, read status, Brand page data, corrections
  - chats and campaigns
  - messages and question answers
  - plan changes and approval
  - assets: read, versions, undo, hand edit, check again
  - memory: list, edit, delete, pin, undo
  - costs
  - AI call log with exact prompts
- Live progress is pushed to the browser as a stream of events: brand reading progress, stage changes, question cards, conflict notes, status lines, asset state changes, text as it's written, "Remembered" notes and cost updates.

### Data stored (Postgres)

- brands; brand files
- document cards; sections with search vectors; single facts; old/new names; conflicts and their decisions; brand summary; Brand page corrections
- images with their fixed restriction fields
- chats, messages and question cards
- campaigns; plans; plan items; scoped brief rules; approved research findings with source and date
- assets and asset versions with check notes
- core memory items; campaign history records
- AI call log with prompts, replies, tokens and cost

### UI

- **Left sidebar:** chats, New campaign, Memory, Brand, Add brand. A brand dropdown appears when there is more than one brand.
- **Middle:** chat with question cards, conflict notes, status lines and "Remembered" notes.
- **Right:** the plan as cards (delete, drag to reorder, edit fields, Approve plan), then the asset previews with state, versions, Undo, Compare, Copy, Check again and check notes.
- **Top bar:** brand name and running campaign cost.
- The Brand page opens automatically after a brand is first read.

## Testing Decisions

- **What makes a good test:** it checks what a user or caller can see (API responses, saved results, events), never internal details like private functions or prompt wording. Tests should survive a refactor that keeps behaviour the same.
- **Main test entry point: the backend's public API**, with the AI client and web research client swapped for fakes that return scripted replies. Tests are fast, free and repeatable. They drive whole flows:
  - Upload a small sample brand, then check document statuses, conflicts and Brand page data.
  - Upload a new file that replaces an old one, then check the old one becomes "replaced" without being re-read.
  - A Brand page correction survives an update.
  - A clear brief goes straight to a plan, and a vague brief produces question cards.
  - A brief with a false claim produces push-back that cites the source.
  - Writing can't start before approval.
  - Approval writes all assets, each with its fixed fields.
  - A chat edit changes only one asset and saves a version; undo restores it.
  - A hand edit runs free checks and logs no AI cost.
  - Memory items are created, undone and carried into a new chat's fixed prompt part.
  - Campaign history is looked up only during planning.
  - Every AI call is logged with tokens and cost.
  - The fixed prompt part is identical across calls for one brand, so caching works.
- **Second, small entry point: rule logic tested directly**, with many edge cases:
  - the conflict winner order
  - image blocking from restriction fields and channel rules
  - the free checks: banned words, length limits, product names, citations against approved research
- **Test brands are made up inside the tests**, small and deliberately messy. Tests do not depend on the sample brand, so the app isn't tuned to it.
- **Not a test: the real-AI run script.** It runs sample briefs against the real key and saves assets, cost per step, cache hit rate and the cost of a typical edit. It produces COSTS.md and is used to judge quality by eye.
- **Prior art:** none, as the repo is new. Tests use pytest with FastAPI's test client, against a real Postgres test database in Docker.

## Out of Scope

- Creating new images with AI. The library only, plus "nothing fits" suggestions.
- Social networks other than LinkedIn and X: no Instagram, Facebook or others.
- Asset types beyond social posts, blogs, landing pages and emails.
- Publishing or scheduling assets to real platforms. Copy button only.
- Login, user accounts, multiple users, deployment.
- Reading briefs from a folder. Briefs are pasted into chat only.
- Several campaigns in one chat.
- Non-OpenAI models.
- Non-text brand documents such as PDFs, slides and spreadsheets. They can be added later.

**First cuts if time runs short:** compare highlighting, drag-to-reorder, the brand dropdown, live text as it's written. Status lines stay.

## Further Notes

- **Build order:** brand reader → agent flow (cost logging and View prompt from the start) → asset views → edits → memory → polish and write-up (README, DECISIONS.md, COSTS.md, screen recording).
- **Time budget:** 4–7 days.
- The sample brand folder is a stand-in. Nothing about it may be built into the code, prompts or rules. All brand-specific behaviour must come from the uploaded files.
- **Write-ups** must cover how the brand reader and memory work and why, how conflicts are handled, what was left out, where an AI tool led us wrong, and what we'd do with two more weeks.
- **Writing style for the app's chat messages and docs:** plain English, no unnecessary jargon.
