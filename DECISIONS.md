# Decisions

## The brand layer

A brand folder is too big to put in a prompt, and it contradicts itself: old and new versions side by side, a "FINAL" file that is out of date, a sales deck claiming what Legal forbids, drafts that look finished, internal notes that must never be quoted, and images with free-text restrictions. So the app reads the folder once, turns it into structured knowledge, and gives the agent tools to look things up rather than a dump of text.

**Reading, in steps, each saved by a hash of its input** (so an update re-reads only what changed):

1. Basics with no AI (headings, labels at the top, file-name hints), then sections with search vectors.
2. A **card per document** (small model): type, claimed status, date, owner, topics it rules on, safe to quote, what it says it replaces. Every field carries its proving sentence; a quote that isn't in the document is thrown away.
3. **Names** and **links between documents** (medium model), each proved by a sentence; then **document status by plain rules**, so a replaced, draft or archived document stops being used.
4. **Single facts** (medium model): subject, attribute, value, kind (must / must not / may / fact), scope and proving sentence. Facts that disagree become **conflicts**, settled by plain rules (below).
5. **Images**: the info file or a vision description, with free-text restrictions turned into fixed fields (small model), and per-channel image rules.
6. A **brand summary** of 3–5 pages (large model), built only from winning facts.

**Why this shape:** the model is good at reading one document at a time, and bad at keeping 84 of them straight at once. So the model reads, and plain code decides. Which document is current, who wins a conflict and whether an image is blocked are all decided by rules a person can read and correct. The Brand page shows every decision with its reason, and every correction made there wins over the rules, survives updates and is applied last.

**At campaign time** the agent gets the brand summary in every prompt, and tools for the rest: search the brand, get facts on a topic, get a channel's rules, read a document, see where documents disagree. The tools only return current material. Facts that lost a conflict are left out, and internal material comes labelled "background only, never quote".

## Conflicts

When facts disagree, the rules are applied in this order. The first rule that leaves only one side standing decides:

1. **Replaces:** a document that another one replaces loses.
2. **Owner:** the document in charge of the topic wins (Legal on claims, the brand team on voice). Internal notes are never in charge.
3. **Approved:** approved beats draft.
4. **Newer:** a later date wins.
5. **Live:** current beats archived.
6. Otherwise **needs a human**: it is shown on the Brand page, and the agent asks about it only if a brief depends on it. The answer is saved as a brand decision.

Documents on the same side never compete with each other. Each time the agent relies on a settled conflict, the chat says so in one line, for example: "Using approved-claims-2026.md over sales-deck-notes-q3.md on certifications: it is in charge of this." Wrong facts in a brief are not obeyed silently: the agent pushes back with the document and its exact sentence, and offers the safe wording as the first option. Where the brief does have the standing to change something (a launch date that ends a "beta" label), that becomes a rule for this campaign only.

## Memory

There are two stores per brand, kept apart on purpose:

- **Core memory:** general corrections ("never call it a platform"), preferences (asset mix, tone, length) and conflict decisions. It is capped at 50 items, near-duplicates are merged, and it is always in the fixed part of every prompt, so every call follows it.
- **Campaign history:** one short record per finished campaign (name, goal, audience, angle, assets, images, dates). Only the planning step reads it, so plans don't repeat recent angles or images. History can grow without making every call longer and dearer, which would happen if it lived in core memory.

New items are suggested by the small model from the marketer's own messages after plan changes, edits and the end of a campaign. The brief itself is never mined, because it is campaign-only by nature. Items are saved straight away with a "Remembered: …" note and Undo in the chat, since asking first for every item would be tiring. When the marketer makes the same hand fix twice, the app offers "Remember this?". The Memory page shows both stores, with the chat each item came from, and every item can be edited, pinned or deleted.

## Writing, checking and editing

- **One asset, one call,** with only what it needs: the fixed part, the approved campaign, then this asset's channel rules, facts, research and image. Each type has fixed fields, so previews and checks can rely on them.
- **Images:** blocking runs first, on fixed fields only, so a retired or events-only image can never be ranked; the brief's own image rules are added on top. When nothing fits, the asset says so and suggests a photo.
- **Checks in two layers:** free rule checks (banned words, retired names, lengths, the image, citations against approved research), then an AI check of claims and tone that only counts words really in the asset. One automatic fix, then visible warnings. Hand edits run only the free checks, at $0. Chat edits rewrite only the asset and field meant. Every change is a version.
- **Research only while planning,** per asset, shown on the plan with link and date for the marketer to keep or remove. Each search runs once; a finding whose quote isn't on the page is dropped; edits never search unless asked. Brand documents beat the web on product facts, prices and guidelines.

## Models

Three OpenAI models, chosen by job size. Every job asks for a size, so a swap is one line in `.env`. See [docs/model-trial.md](docs/model-trial.md) for the trial.

| Size | Model | Jobs | Why |
|---|---|---|---|
| Small | `gpt-6-luna` | Document cards, image descriptions and restrictions, research notes, memory, campaign records | In the trial it read dates and owners out of prose better than Terra, at a tenth of the price. These jobs run once per file or per message, so price matters most. |
| Medium | `gpt-6.1-terra` | Facts, names, conflicts, writing rules, image choice, claims and tone check, fixes, edits | As accurate as Sol on the facts that matter, with more even subject names (which helps conflicts group), at about a quarter of the cost. In the full run it caught every planted problem in a finished post. |
| Large | `gpt-6.1-sol` | Brief review, questions, planning, the brand summary, writing every asset | The copy a marketer judges, and the decisions that shape a campaign. It read best in the trial, and across 20 assets in the full run it kept the brand's voice and naming rules. It is about 80% of a campaign's cost ($0.24–$0.66 per brief); quality was not traded for tokens here. |

**Prompt caching.** Every prompt is built in the same order: the fixed part (the same for every call for a brand), then the campaign part, then the task. Left to itself the API caches up to the end of every prompt, paying 1.25× input to store one-off tasks too. So cache points are placed by hand, after the fixed part and after a shared campaign part, while tool loops keep the default because each round resends the last. The 30-minute lifetime is used: a campaign's calls come minutes apart, so the 12-hour one (2.5× to write) would buy nothing. Numbers are in [COSTS.md](COSTS.md).

## What was left out

- **Live text as it's written.** Asset cards show Waiting → Writing → Checking → Done, and the chat shows status lines, but the text arrives whole. This was the spec's first cut if time ran short.
- **Live updates by event stream.** The browser polls every 1.5 seconds while writing, which is simpler and good enough for one user.
- **A brand dropdown** for several brands. New chats use the most recently read brand.
- **Non-text brand documents** (PDF, slides, spreadsheets), publishing, scheduling, logins, and image generation, as agreed in the spec.

## Where the AI tools led us wrong

- **Conflict rules, first draft.** A replaced document could still win on "owner", internal battlecards tied with real policy, and two documents saying the same thing were counted as a conflict. These were found by reading the real results, and fixed by applying "replaces" first, never letting internal notes be in charge, and grouping facts into sides.
- **Noisy notes.** The agent's tools hand it many facts, and the first version noted every conflict it had merely seen: 9 notes on one brief, most about things it never used. A note is now shown only when the winning fact's value appears in what the agent wrote.
- **Brief rules backwards.** The agent first listed cases where the brief gives way to the brand as "overrides". The prompt now says plainly that a brief rule only goes the other way.
- **Stock-photo clichés.** Images were judged only against their own notes, so a hooded-hacker stock image passed even though the brand's rules ban the motif. Notes are now judged against the brand's image rules too.
- **Cache points.** Moving everything to hand-placed cache points also took caching away from tool loops, where each round resends the last round. One brief review read 46k tokens with only 7k from cache, at $0.08 a round. The call log showed it at once, and tool loops went back to the default cache point.
- **Checks too strict.** The first full run gave every asset 2–8 warnings, and the automatic fix deleted real product facts. There were three causes. The AI check never saw the brief, so it called the brief's facts unsupported. A banned capitalisation ("LeashGate") was matched without regard to case, so every correct "Leashgate" was flagged. And the fix model's notes on flags it rejected were shown as warnings. Now the check sees the approved campaign, capital-only bans match exactly, and rejected flags are listed as "kept as written". The next run had no false warnings, and a planted false claim was still caught.
- **Prose before JSON.** Once in 20 assets, the writer put a sentence ("The selected console image conflicts with the brief…") before its JSON, and the asset failed. The sentence was right: the image picker had only been given the brief's overrides, not its own image rules. Replies are now read past such a sentence, and every sentence of the brief about images reaches the picker.
- **Small things:** a markdown "#" in chat titles, database key order breaking the hand-fix counter, and tool searches counted as brand-reading cost. All were caught by tests or by reading the call log.

## With two more weeks

- Stream text as it's written, and push events instead of polling.
- Read PDFs and slides, which most real brand folders are full of.
- Score assets against the brand's own past content, not only its rules, for voice.
- Let the marketer approve or reject each auto-fix, rather than only seeing a note.
- Several brands with a dropdown, and roles (a reviewer who only approves).
- A small evaluation set from real campaigns to compare models and prompts on, rather than judging by eye.

## Implement later

- **Changing an asset's image by chat.** Found in testing: "why don't we have another image instead of this" did nothing. The request was treated as a text edit, but the edit step only sees an asset's text fields. The image picker never ran again, so the same image stayed. The reply then repeated the model's claim that the image was replaced, next to "not changed, so no new version". It cost $0.02 for nothing.
  - **By chat:** a request about the image ("use a different image", "use a photo of the team") should run the image picker again for that asset, leaving out the current image and taking the marketer's words as guidance, within the brand's and the brief's image rules. A new image is saved as a new version with the same text, so it can be undone. When nothing fits, say so plainly.
  - **A "Pick another image" button** under the image in the preview, doing the same without typing (one image-choice call, under a cent).
  - **Honest replies:** when an edit changes nothing, the chat should say only that, not the model's description of a change it couldn't make.
