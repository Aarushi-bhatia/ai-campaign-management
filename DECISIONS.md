# Decisions

## The brand layer

A brand folder is too big to put in a prompt, and it contradicts itself: old and new versions side by side, a "FINAL" file that is out of date, a sales deck claiming what Legal forbids, drafts that look finished, internal notes that must never be quoted, and images with free-text restrictions. So the app reads the folder once, turns it into structured knowledge, and gives the agent tools to look things up rather than a dump of text.

**Reading, in steps, each saved by a hash of its input** (so an update re-reads only what changed):

1. Basics with no AI (headings, labels at the top, file-name hints), then sections with search vectors.
2. A **card per document** (small model): type, claimed status, date, owner, topics it rules on, safe to quote, what it says it replaces. Every field carries its proving sentence. A quote that isn't in the document, or is a single word or only the claimed value (a bare "Maren" doesn't prove Maren owns it), is thrown away and listed as unverified.
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
6. Otherwise **needs a human**: it is shown on the Brand page, and the agent asks about it only if a brief depends on it. The answer is saved as a brand decision for that point of disagreement, shown and undone on the Brand page. It is not copied into memory, where it would go stale when the conflict is decided again.

A conflict is judged only on documents that still count for its kind of fact. When one side's document is replaced or changes type, the other side wins as "only side left".

Documents on the same side never compete with each other. Each time the agent relies on a settled conflict, the chat says so in one line, for example: "Using approved-claims-2026.md over sales-deck-notes-q3.md on certifications: it is in charge of this." Wrong facts in a brief are not obeyed silently: the agent pushes back with the document and its exact sentence, and offers the safe wording as the first option. Where the brief does have the standing to change something (a launch date that ends a "beta" label), that becomes a rule for this campaign only.

## Memory

There are two stores per brand, kept apart on purpose:

- **Core memory:** general corrections ("never call it a platform") and preferences (asset mix, tone, length). It is capped at 50 items and is always in the fixed part of every prompt, so every call follows it.
- **Campaign history:** one short record per finished campaign (name, goal, audience, angle, assets, images, dates). Only the planning step reads it, so plans don't repeat recent angles or images. History can grow without making every call longer and dearer, which would happen if it lived in core memory.

New items are suggested by the small model from the marketer's own messages after plan changes, edits and the end of a campaign. The brief itself is never mined, because it is campaign-only by nature. Items are saved straight away with a "Remembered: …" note and Undo in the chat, since asking first for every item would be tiring. Merging is cautious, because a wrong merge loses what the marketer said:

- Only clear equivalents merge on their own: the same words in another order, or only filler changed.
- An item that contradicts an older one, or narrows or widens it, is kept beside it. When the model says it changes the older one, the note offers **Replace it**.
- Campaign-only details ("for this launch only") are not learned for the brand.
- Undo restores what a merge dropped, and refuses if the item was edited since.
- **"Remember this?" from hand edits.** A marketer who keeps fixing the same word by hand is telling us a rule without saying it. Each hand save is compared with the version before, word by word, and every small swap (up to three words for up to three, such as "engineer" → "operator") is counted, across all of the brand's campaigns. The second time the same swap is seen, the chat offers "You've made this change by hand more than once. Remember it? Use “operator” instead of “engineer”." Saying yes saves it to core memory, so every later piece follows it. No AI is involved, so it costs nothing. It isn't offered when memory already says the same thing, the same swap twice in one save counts once, and a change of capitals only is ignored. It asks first, rather than saving straight away like chat memory, because a hand edit doesn't say whether it was meant for this piece only.
- The Memory page shows both stores, with the chat each item came from, and every item can be edited, pinned or deleted.

## Writing, checking and editing

- **One asset, one call,** with only what it needs: the fixed part, the approved campaign, then this asset's channel rules, facts, research and image. Each type has fixed fields, so previews and checks can rely on them.
- **Images:** blocking runs first, on fixed fields only, so a retired or events-only image can never be ranked. An image whose rights haven't been checked is blocked too. Image types the brief rules out ("no screenshots") are a hard block as well; the plan lists them with the brief's words and an **Allow** button, in case the model misread the brief. When nothing fits, the asset says so and suggests a photo.
- **Checks in two layers:** free rule checks (banned words, retired names, lengths, hashtag limits, the image, citations against approved research), then an AI check of claims and tone that only counts words really in the asset. One automatic fix, then visible warnings. Hand edits run only the free checks, at $0. Chat edits rewrite only the asset and field meant. Every change is a version.
- **Plain words to the marketer.** Fixed chat text says things simply ("Tagline: four brand documents disagree. I used why-we-renamed-the-company.md, because it is newer." rather than listing every losing file; "Your brief goes against a brand rule" as a question's label). The AI is told to use short sentences and everyday words, to explain product terms, and to write each question as: what the brief says, what the brand says instead, and why it matters.
- **Removing a piece hides it, never deletes it.** "Remove the blog post" marks it removed: it leaves the tabs and moves to a "removed" list on the plan, but its text, versions, warnings and costs stay. Undo on the chat note brings it back exactly as it was, in its old place, at no cost. A real delete would lose work for good, and writing it again would cost money and come out different. At least one piece must stay.
- **The Brand page explains a test pick.** "Try picking images" lists every image it blocked before ranking, each with its reason ("email uses only photography", "It features a person who left the company in June 2026"), behind a "Show the N blocked images and why" link, not only a count. An open image's details have a ✕ and close with Esc; before, the only way to close them was to click the same image again.
- **An edit that's already done changes nothing.** "Keep the LinkedIn post under 100 words" on a 43-word post used to add an unasked-for phrase, save a new version and cost $0.04, because the edit prompt always expected a change. The editor is now told to return the piece exactly as it is when it already does what was asked, and to say why; the app then saves no version and runs no checks, and the reply says "not changed, so no new version". The one call that reads the piece is still paid for.
- **View prompt shows exactly what was sent.** Each call's log is the same payload the API was sent, apart from an image, which is shown as a label; a test now compares the two for every call in a campaign. A piece's View prompt opens the call that wrote its current text (the latest write, edit or fix, never a check), not only the first draft. When the text was edited by hand after that, the button says "View prompt (before your hand edit)"; a piece only ever typed by hand says "Hand edit, no AI call". The viewer also labels the model's encrypted reasoning from earlier tool rounds instead of an empty box, shows which tool call each result answers, shows an image's detail setting, and wraps the request options.
- **Replies say what was done.** The note after a chat change speaks of one piece as "it" and of several as "they", and the AI is told to write its reply in the past tense ("I removed the blog post."), since the change is already made when the reply is shown.
- **Quotes shown clean, kept exact.** A brand sentence shown as proof drops the markdown it was written in (a list dash, bold stars, backticks) on screen only. The saved quote stays character for character, because it is what proves the sentence is really in the document.
- **Copy is only copy.** Every field the writer returns is published as written, so the writer is told never to put notes for the team, design instructions or explanations inside it. Anything still missing is a short blank such as "[demo page URL]".
- **Research only while planning,** per asset, shown on the plan with link and date for the marketer to keep or remove. Each search runs once; a finding whose quote isn't on the page is dropped; edits never search unless asked. Brand documents beat the web on product facts, prices and guidelines.

## Keeping saves consistent

Several things can change a campaign at once: a chat message, a card edit, the writing job, Check again. So:

- An AI call is logged in its own short transaction, and no database lock is held while the model works. Each step saves once at the end, so a failed step leaves nothing half-saved.
- **Optimistic locking with version numbers.** The plan and each piece have a version number that goes up on every change. Plan saves, approval, answers, hand edits, chat edits, Undo, restoring a version and Check again each send the version they saw. If it changed meanwhile (another tab, a chat edit), nothing is saved and the latest state is shown. Two tabs can both edit freely; only the later, out-of-date save is refused. Locking a piece while someone edits it (pessimistic locking) was not used: a tab left open would block everyone.
- At the moment of saving, the row is locked for a split second (`SELECT … FOR UPDATE`) while the version is read, compared and the new one written. Without it, two saves arriving at the same instant could both see the old version, both pass and both save.
- A question asked while planning expires once the plan is approved.
- A save refused because the plan changed says so plainly: "Someone changed the plan (in another tab or in the chat), so your change wasn't saved. You're now seeing the latest plan. Make your change again." A piece's save refused the same way names it and its version: "Someone changed “Launch email” (in another tab or in the chat), so your change wasn't saved. It's now at version 3. Look at the latest version and make your change again."
- **An AI request that hangs is retried after 2 minutes** (twice at most). OpenAI sometimes never answers a request that would take seconds; the same request then works at once on a retry. It used to wait 5 minutes per try, so a one-line plan change once took 10 minutes. The slowest real replies take about 80 seconds (brand facts), so 1 minute would cut off real work.
- Every check that needs understanding (does the brand use X? are hashtags allowed? does the brief ban screenshots?) is answered by a structured field from the model, each with its quote, never by matching words in free text.

## Code layout

The backend's `brand` and `campaign` folders had grown to 22 and 15 files, with names that sounded alike (`writer.py` and `writing.py`, `checks.py` and `checker.py`, `settle.py` and `status.py`). They are grouped by job, with files only moved and renamed, so behaviour is unchanged:

- `brand/reading/`: the steps of reading a brand folder (`reader`, `parsing`, `cards`, `facts`, `names`, `links`, `writing_rules`, `summary`).
- `brand/rules/`: the plain-rule decisions, no AI (`settle`, `status`, `conflicts`, `evidence`).
- `brand/images/`: as before. Models, routes, the service and the Brand page's views stay at the top.
- `campaign/checking/`: `free.py` (the free rule checks, was `checks.py`) and `ai.py` (the AI check, was `checker.py`).
- `campaign/writing/`: `writer.py` (the prompts for one asset), `queue.py` (writes a plan's assets in the background, was `writing.py`) and `assets.py` (work on one asset).
- The agent, chat service, editing, research, costs and stages stay at the top of `campaign/`.

## Models

Three OpenAI models, chosen by job size. Every job asks for a size, so a swap is one line in `.env`. See [docs/model-trial.md](docs/model-trial.md) for the trial.

| Size | Model | Jobs | Why |
|---|---|---|---|
| Small | `gpt-6-luna` | Document cards, image descriptions and restrictions, research notes, memory, campaign records | Read dates and owners out of prose better than Terra in the trial, at a tenth of the price. These jobs run per file or per message. |
| Medium | `gpt-6.1-terra` | Facts, names, conflicts, writing rules, image choice, claims and tone check, fixes, edits | As accurate as Sol on the facts that matter, with more even subject names, at a quarter of the cost. It caught every planted problem in the full run. |
| Large | `gpt-6.1-sol` | Brief review, questions, planning, the brand summary, writing every asset | The copy a marketer judges and the decisions that shape a campaign. It read best in the trial and kept the brand's voice across 20 assets. About 80% of a campaign's cost; quality was not traded for tokens here. |

**Prompt caching.** Every prompt is built in the same order: the fixed part (the same for every call for a brand), then the campaign part, then the task. Cache points are placed by hand after the fixed part and a shared campaign part, so one-off tasks don't pay 1.25× to be stored; tool loops keep the default, because each round resends the last. The 30-minute lifetime is used: a campaign's calls come minutes apart, so the 12-hour one (2.5× to write) would buy nothing. A channel's rules are still part of each asset's own task, not of a cached part shared by that channel's assets. Moving them would change every writing prompt, for a saving of cents per campaign, so it was left. Numbers are in [COSTS.md](COSTS.md).

## What was left out

- **Live text as it's written.** Asset cards show Waiting → Writing → Checking → Done, and the chat shows status lines, but the text arrives whole. This was the spec's first cut if time ran short.
- **Live updates by event stream.** The browser polls every 1.5 seconds while writing, which is simpler and good enough for one user.
- **Brand roles and switching inside a chat.** A new chat uses the brand chosen in the sidebar (or the most recently read one), and keeps it.
- **Non-text brand documents** (PDF, slides, spreadsheets), publishing, scheduling, logins, and image generation, as agreed in the spec.

## Where the AI tools led us wrong

- **Conflict rules, first draft.** A replaced document could still win on "owner", internal battlecards tied with real policy, and two documents agreeing counted as a conflict. Fixed by applying "replaces" first, never letting internal notes be in charge, and grouping facts into sides.
- **Noisy notes.** The agent's tools hand it many facts, and the first version noted every conflict it had merely seen: 9 notes on one brief, most about things it never used. A note is now shown only when the winning fact's value appears in what the agent wrote.
- **Brief rules backwards.** The agent first listed cases where the brief gives way to the brand as "overrides". The prompt now says plainly that a brief rule only goes the other way.
- **Stock-photo clichés.** Images were judged only against their own notes, so a hooded-hacker stock image passed even though the brand's rules ban the motif. Notes are now judged against the brand's image rules too.
- **Cache points.** Hand-placed cache points first took caching away from tool loops too: one brief review round read 46k tokens with 7k cached, at $0.08. The call log showed it, and tool loops went back to the default.
- **Checks too strict.** The first full run gave every asset 2–8 warnings, and the fix deleted real product facts. The AI check never saw the brief; a banned capitalisation ("LeashGate") flagged every correct "Leashgate"; and flags the fix rejected were shown as warnings. Now the check sees the approved campaign, capital-only bans match exactly, and rejected flags read "kept as written". The next run had no false warnings, and a planted false claim was still caught.
- **Prose before JSON.** Once in 20 assets, the writer put a sentence before its JSON ("The selected console image conflicts with the brief…"), and the asset failed. The sentence was right: the picker hadn't been given the brief's image rules. Replies are now read past such a sentence, and the brief's image rules reach the picker.
- **Word patterns for decisions.** Whether hashtags are allowed was decided by a regex, patched twice, and it still fired on "up to two at the end are fine". Same for "x" inside a file name meaning the X channel. These are now structured answers from the model, each with its quote.
- **A schema that stalled the model.** Asking a chat edit of the plan to also return the image exclusions made most real replies time out (8 of 12), while the same edit without that field replied in seconds. Exclusions are now changed only with Allow on the plan.
- **A check that couldn't see the image.** The AI check was given the copy but not the chosen image, so it reported "no image is specified" on a post that had one, and the fix "added" one by describing a photo in words while nothing changed. The check is now shown the image and told images are judged by the free checks.
- **A production note in the page.** With nowhere else to put it, the writer added a landing-page section titled "Production note — not page copy" (where the photo goes, which form fields to add). It would have been published. The writer is now told that every field is published as written.
- **A full stop that hid a banned line.** The brand's dropped taglines are listed with their full stop ("Sleep through the night."), and the free check matched them exactly, so the line typed without it got no warning. Punctuation around a banned phrase is now ignored.
- **Small things:** a markdown "#" in chat titles, database key order breaking the hand-fix counter, and tool searches counted as brand-reading cost. All were caught by tests or by reading the call log.

## With two more weeks

- Stream text as it's written, and push events instead of polling.
- Read PDFs and slides, which most real brand folders are full of.
- Score assets against the brand's own past content, not only its rules, for voice.
- Let the marketer approve or reject each auto-fix, rather than only seeing a note.
- Several brands with a dropdown, and roles (a reviewer who only approves).
- A small evaluation set from real campaigns to compare models and prompts on, rather than judging by eye.
- **A brief that overrides the brand without asking.** Once, the brief review decided on its own that the brief's author could lift the brand's "no hashtags on X" decision, because he had been at the meeting that made it. That became a campaign rule with no question and no way to undo it. The next run asked properly, but nothing enforces it. Every point where the brief would override a brand rule should be asked as a question, with the brand's rule as the first option, and a campaign rule should be removable from the plan.
- **Changing an asset's image by chat.** "Use another image" is treated as a text edit today, so nothing changes, while the reply repeats the model's claim that it did. A request about the image should run the image picker again for that asset, without the current image and within the brand's and brief's rules, saved as a new version. A "Pick another image" button could do the same. And when an edit changes nothing, the reply should say only that. Kept on hold for now: in a test, "Use a different image for the landing page" left the image as it was, rewrote a line of page text to ask for a new photo, and cost $0.04.
