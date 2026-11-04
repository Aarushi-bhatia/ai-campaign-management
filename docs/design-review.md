# Design review of the 43 audit findings

This review groups the 43 findings by root cause and proposes one fix per group. No code or data was changed.

The finding numbers are the ones in the merged audit list: bugs 1–15, weaker spots 16–29 and small issues 30–43.

**How sure each root cause is:**
- **Confirmed:** I read the code path, or a reviewer's probe showed it. I re-ran four of the small ones (#14, #15, #36 and #7's matching) against the live code today, and all four are still open.
- **Hypothesis:** this follows from reading the code, but no test has shown it yet.

**Already fixed:** #25 (the "same topic" rule). The plan-edit model's `research_changed` flag replaced it. No more work is needed.

---

## The groups at a glance

| Group | Root cause | Findings | Size |
|---|---|---|---|
| 1 | Logging an AI call commits the caller's unfinished work | 9, 39, 34, part of 10, part of 12 | Structural |
| 2 | Long steps check the campaign once, then save on top of whatever changed | 10, 19, 26, 33 | Medium |
| 3 | Undo, restore and re-recording don't keep the full earlier state | 11, 12, 13 (+1 new) | Small to medium |
| 4 | Things are identified by names, paths or fuzzy text | 1, 21, 5, 15, 23 | Medium |
| 5 | Derived data is deleted, or used after it has gone stale | 4, 6, 39, 3, 18 | Medium |
| 6 | Inputs and stage changes are checked in the UI or the AI path, not at the API | 8, 20, 31, 32, 34, 35, 36, 37, 40, 41 | Many small fixes |
| 7 | Keyword matching decides things that need a structured answer | 7, 14, 16, 24 | Medium (needs model runs) |
| 8 | "Current documents only" and "internal is never in charge" are enforced in some places only | 2, 17 | Small |
| 9 | Costs are added up by guessing, not from the calls an action made | 27, 38, 43, 28 | Small |
| 10 | Uploaded SVGs run as pages on the app's own address | 22 | Small |
| 11 | Docs, scripts and the prompt cache have drifted | 29, 30, 42 | Small |

---

## Group 1: logging an AI call commits the caller's unfinished work

**Findings:**
- **Confirmed:** #9 (the image lock is released early), #39 (sections are deleted before the new ones are ready), and #10 in part (with a single search, the plan can be approved before its findings land).
- **Hypothesis:** #34 (a failed brief review leaves the brief saved) and #12 in part (a wide edit stops partway, with some assets saved).

**Root cause (confirmed):** `AiService._finish` (`app/ai/service.py:158`) logs each call by running `session.add(call); session.commit()` on the caller's session. So every AI call commits whatever the caller has half-done, and it releases any row lock the caller holds.

On top of that, `CampaignService._post` commits after every chat message, and `AssetWork._set_state` commits as well. The result is that a "step" is never all-or-nothing.

**What goes wrong today:**
- **The image lock (#9).** `_pick_image` locks the campaign row, then `library.pick` makes an AI call. That call commits, which drops the lock before `asset.image` is saved, so two assets can pick the same image.
- **Embedding (#39).** `_index_sections` deletes the old sections, and the first embedding call commits that delete. If a later batch fails, those documents are left with no sections.
- **Planning (#10).** `_plan` sets `stage = plan_ready`, and the next `_post` commits it. That happens before the research has finished.

**Proposed design:**
1. **Log on a separate session.** `AiService` gets a session factory and writes the `AiCall` row in its own short transaction. The caller's session is never committed by the AI layer, and the caller decides when its own work is saved. A failed call is still logged, even when the caller rolls back.
2. **Never hold a database lock across an AI call.** Image choice becomes "pick, then reserve":
   - Pick with no lock. `pick` already returns a ranked list.
   - Then lock the campaign row briefly, re-read the images in use, and take the first ranked choice nobody has taken. Save it and commit.
   - If every ranked choice is taken, keep the top one and note that it repeats.

   This also stops image ranking running one asset at a time.
3. **Show progress on purpose, not by accident.** Keep explicit commits only where progress is meant to be visible (an asset moving to "writing" or "checking", and chat notes during long jobs). Elsewhere, `_post` only flushes, and the service method commits once at the end.
4. **Swap sections in one go.** Build all the new vectors first, then delete the old sections and insert the new ones in one transaction.

**What changes:**
- **Files:**
  - `app/ai/service.py`: `__init__` and `_finish`
  - `app/ai/deps.py` and `app/campaign/runtime.py`: pass the session factory
  - every `AiService(session, …)` call in `app/brand/reader.py` and `app/brand/images/reading.py`
  - `app/campaign/assets.py`: `_pick_image` and `write`
  - `app/campaign/service.py`: `_post`, and the end of each step
  - `app/brand/reader.py`: `_index_sections`
- **Tables:** none. The `ai_calls` rows are written by another connection.
- **Migration:** no.

**Risks:**
- **Unsaved parent rows.** The logging session can't see rows the caller hasn't committed. An AI call that names a chat or brand created in the same unfinished transaction would fail its foreign-key check. Every caller needs checking. Today, brands and chats are committed before their first AI call, but that has to be confirmed path by path.
- **Connections.** Each request now uses two database connections. The writing workers, research threads and brand reads add up, so the pool size needs a look.
- **Tests.** Tests that read the `AiCall` row through the caller's session still work, because the row is committed. The existing image race test patches out the AI call, so it has to be rewritten to make a real fake-AI call.
- **The writing screen.** If commits are moved carelessly, the UI could stop showing progress.

**Regression tests:**
- Two assets written at once, with a `pick` that makes a real (fake-transport) AI call, get different images. This is the reviewer's probe.
- An embedding batch that fails partway leaves the old sections in place.
- A failed brief review leaves no half-saved state.
- An AI call that fails while the caller rolls back is still logged.

**Size:** structural. The change is central to one file, but it touches every place that builds an `AiService`.

---

## Group 2: long steps check the campaign once, then save on top of whatever changed

**Findings:**
- **Confirmed:** #10 (research changes after approval), #19 (a card edit deletes a card that chat added), #26 (Check again attaches old warnings to newer text).
- **Hypothesis:** #33 (one question answered twice), and a chat plan edit that runs during approval. That second case is unconfirmed, because the reviewer's probe hung.

**Root cause (confirmed):**
- **The campaign has no "has it changed?" check.** The stage is checked at the start. Then an AI call or web search runs, for seconds or up to 90 seconds, and the result is written whatever happened meanwhile. `Campaign.plan_version` exists but is never compared.
- **Assets are only half covered.** Assets already have this check (`_save(expected=…)`), but Check again doesn't use it.

**What goes wrong today:**
- **Better source and Try again** (`service.py:183-201`) rewrite `campaign.research` after the plan was approved, and after the writers had already read it.
- **Saving the plan cards.** `update_plan` replaces the whole card list with the client's copy.
- **Answering questions.** `answer` is a plain read-then-write.
- **Check again** writes `asset.warnings` with no version check.

**Proposed design:**
- **One guarded save for campaigns.** This is the same idea as `_claim_stage` and the asset version check:
  - When a step starts, it records `(stage, plan_version)`.
  - It saves with `UPDATE campaigns … WHERE id = :id AND stage = :stage AND plan_version = :v`, and bumps `plan_version`.
  - If no row matches, nothing is saved. The chat says "The plan changed while I was working, so I didn't change it," along with what the attempt cost.
- **`plan_version` covers research too.** Every change to the plan **or** its research bumps it. Approving the plan is then a promise about both.
- **The client sends the version it saw.** The plan card save and Approve take the client's `plan_version` as `base`, like asset edits already do. Approving a plan you haven't seen is refused.
- **An answer claims its question first.** `answer` locks the campaign row for its short check-and-write, commits, and only then makes the AI call.
- **Check again** passes `expected=asset.version`, and its warnings only land if the asset hasn't moved on.

**What changes:**
- **Files:**
  - `app/campaign/service.py`: `_plan`, `_edit`, `update_plan`, `approve`, `answer`, `better_source`, `retry_research`, `remove_finding`, `bring_back_finding`
  - `app/campaign/research.py`: one bump per step, not per search
  - `app/campaign/assets.py`: `check_again`
  - `app/chat/routes.py` and `schemas.py`: `base` on plan PUT and approve
  - frontend `PlanPanel.tsx`, `client.ts`, `AssetView.tsx`
- **Tables:** `campaigns` (existing columns only).
- **Migration:** no.

**Risks:**
- **Refusals the user doesn't expect.** With two tabs open, or a panel that hasn't refreshed, the user gets refused when they didn't expect it. The message has to say "refresh", and react-query must refetch the plan after every chat reply.
- **Research is paid for, then thrown away** when it is refused. That is the honest choice, but the chat must show the cost.
- **Planning would refuse itself.** `_plan` runs research inside the same step. If research bumps the version partway through, the step would refuse its own save. The bump has to happen once, at the end.

**Regression tests:**
- Approve during Better source: Better source is refused, the old finding is unchanged, and the asset's sources are still in the approved research.
- A card save with an old `base` after a chat edit that added a card is refused (409), and the chat card is kept.
- Two answers at once give one plan and one set of cards.
- Check again with a hand edit saved mid-check: the warnings are not attached to the new text.

**Size:** medium. It's one pattern, applied in about ten places, plus a small frontend change.

---

## Group 3: undo, restore and re-recording don't keep the full earlier state

**Findings:**
- **Confirmed:** #11 (undo after Check again loses its warnings), #12 (a chat edit whose check fails is thrown away after being paid for), #13 (undo after "memory was full" loses the dropped item).
- **New, confirmed by reading:** `Memory.record` deletes the campaign's history record and inserts a fresh one. It runs again after every Write again or added asset, so any correction the marketer made to that record on the Memory page is silently overwritten.

**Root cause (confirmed):**
- **Some changes skip the version.** A version only stores part of the state, and some actions change the state outside any version:
  - Check again writes `asset.warnings`, but not the current version's warnings.
  - `_keep_small` hard-deletes memory items.
  - `record()` rebuilds a record from scratch.
- **Edits and writing handle failed checks differently.** The writing path keeps a draft whose checks failed. The edit path doesn't.

**Proposed design:**
- **Keep the asset and its version together.** One rule: an asset's warnings, image and content change only through code that updates both the asset and its current version.
  - Check again updates the current version's warnings. It's the same text, now with known problems, so it doesn't need a new version.
- **Keep edits whose checks fail.** A chat edit whose checks fail is saved as a new version with a "not checked" warning, the same as writing does. The reply lists every asset that was saved, so a wide edit that stops partway still reports what it did.
- **Memory undo brings back what was dropped:**
  - The "Remembered" note's `data` stores each dropped item in full: text, kind, pinned and source chat.
  - Undo deletes the new item and re-inserts the dropped ones.
  - If memory has since filled up again, Undo says so and changes nothing.
- **History records keep the marketer's corrections.** `change_record` saves the names of the fields the marketer changed in the record's existing `extra` column. `record()` then updates the record in place and skips those fields.

**What changes:**
- **Files:**
  - `app/campaign/assets.py`: `check_again`, `edit`
  - `app/campaign/service.py`: `_edit_assets`
  - `app/memory/service.py`: `_keep_small`, `undo_remembered`, `record`
  - `app/campaign/writing.py`: `remembered_note`
  - `app/memory/routes.py`: `change_record`, and Undo through `delete_memory`
- **Tables:** `asset_versions`, `memory_items`, `campaign_records`, `messages.data`. All are existing columns.
- **Migration:** no.

**Risks:**
- **Undo meets newer checks.** `_rechecked` keeps an AI warning while its quote is still there. Once versions hold their latest warnings, undoing to a version re-shows its latest known problems. That is the intent, but older tests may expect the stale list.
- **Undo after memory has changed.** If the user has added items since, re-inserting the dropped ones could go over the limit. That is why the "refuse when full" rule above is needed.
- **Edits saved as "not checked".** A failed check now leaves a saved version the marketer must check again. That is the intended trade.

**Regression tests:**
- Check again finds a warning. A hand edit and then Undo still show it.
- Check again clears "not checked", and Undo doesn't bring it back.
- An edit whose AI check fails is kept as a new version marked "not checked", with its cost shown.
- Fill memory to 50, add one, then Undo: 50 items, and the dropped one is back.
- Edit a record's goal on the Memory page, then Write again: the edited goal survives.

**Size:** small to medium, all local.

---

## Group 4: things are identified by names, paths or fuzzy text

**Findings:**
- **Confirmed:** #1 (one conflict choice changes several conflicts), #21 (a choice is lost when a new document joins), #15 (near-duplicate merging: "Use British spelling" is still narrowed to "… in emails"; I re-ran it today).
- **Confirmed by reading:** #5 (preloading a different folder is skipped), #23 (excluded folders aren't remembered; removed files stay in the brand).

**Root cause:**
- **Conflict choices (confirmed).** A saved winner is keyed by `subject | sorted document paths` (`settle.py:15`). Several conflicts can share that key, so one choice applies to all of them. The key also changes when any document joins.
- **Preload (confirmed).** The preload source is the folder's path inside the container, which is always `/preload-brand`.
- **Memory (confirmed).** `near_duplicate` decides that two items are "the same" from overlapping words. When one wording just adds words, that narrows a general rule.

**Proposed design:**
- **Conflicts.** Key a choice by subject **plus the point the facts disagree on**, using `Fact.attribute`, which is already stored for every fact. Store which document won, and stop requiring the exact set of documents. A saved choice applies while its winning document is still on one side.
  - When a new document joins a conflict that already has a saved choice, the choice still applies. The Conflicts tab shows "a new document joined since you chose", and nothing is dropped silently.
  - Old-format saved choices are still read, so the user's existing choices aren't lost. No data rewrite is needed.
  - **Hypothesis to check first:** that the facts in one conflict share one attribute. If they don't, the key needs the sorted set of attributes instead.
- **Preload.** Identify the preloaded brand by its name plus a hash of its file list, not by the folder's path inside the container.
- **Folder exclusions and removed files.**
  - Store the excluded folders as rows in the existing `brand_decisions` table (a new kind, "exclude"), so Update brand applies them again.
  - When a re-upload is missing a file, mark that document "removed". Don't delete it; see Group 5.
- **Memory.**
  - Merge two memory items automatically only when they hold the same words once filler and plural endings are dropped (a reordering, or a filler change).
  - In every other case, a merge happens only when the model's `replaces` names the item's id.
  - Adding words never merges.

**What changes:**
- **Files:**
  - `app/brand/settle.py`: `conflict_target`, `_judge`
  - `app/campaign/agent.py`: `_conflict_options`
  - `app/brand/service.py`: `save_correction`, upload and update
  - `app/brand/startup.py`: `_preload`
  - `app/memory/service.py`: `near_duplicate`, `add`
  - frontend `AddBrandPage.tsx` and the Conflicts tab
- **Tables:** `brand_decisions`, `conflicts` (read only), `brand_files.status`.
- **Migration:** no schema change. Old decision keys are read as they are.

**Risks:**
- **Memory rewordings.** The earlier wish that "Keep emails short" and "Emails should be short" become one item now rests on the model's `replaces`. This rule has already swung back and forth twice (ticket 9, and its second review), so the trade-off should be agreed once and written down.
- **Old conflict choices.** If old-format choices aren't handled, every saved choice the user has made goes back to the rules' verdict.
- **Removed files.** Marking files "removed" changes document statuses, so the conflict winners shift.

**Regression tests:**
- Two conflicts on one subject between the same two documents: choosing B on price leaves status alone.
- A third document joins a conflict with a saved choice: the choice still holds, and the notice is shown.
- An old-format saved choice still applies.
- Preloading a second, different folder creates a second brand.
- Update brand with `briefs/` excluded before doesn't read briefs.
- The memory pairs: British spelling vs. "… in emails" stays separate; the reordering case merges.

**Size:** medium.

---

## Group 5: derived data is deleted, or used after it has gone stale

**Findings:**
- **Confirmed:** #4 (facts are lost after a type change and back), #6 (a banned image stays usable when the notes step fails), #3 (setting a document back to "current" doesn't stop it losing conflicts).
- **Confirmed by reading:** #39 (sections; also Group 1), #18 (`no_crop` is stored but never used, and a "usable: yes" override skips channel limits).

**Root cause (confirmed):** derived rows (facts, image notes, sections, the "replaces" links) each record what they were built from. But:
- **Facts.** A metadata change deletes the data and leaves the "already done" marker in place. Facts are deleted while `facts_sha256` stays set, so they are never pulled out again.
- **Image notes.** When an image's record changes, the old "usable" notes are kept. If refreshing them fails, the old verdict still counts.
- **Replaces links.** `replaces` is built from the raw AI links (`settle.py:49`), so the user's status correction never reaches the conflict rules.

**Proposed design:** three rules.
1. **Don't delete derived data because metadata changed; filter it when it's read.** Facts stay when a document's type changes. Everything that reads facts (`usable_facts`, conflict detection and the lookup tools) only counts documents whose type carries facts. Changing a type to a fact type with no facts yet starts a background read of that one document, so "corrections apply at once" holds.
2. **Stale is unknown, not valid.** An image whose notes were built from older inputs (`notes_hash` doesn't match) counts as "restrictions not checked yet" and is blocked. The brand shows "Ready, but N images couldn't be checked: Read again". The brand still becomes ready, but with a visible problem.
3. **Corrections flow into everything derived from them:**
   - Build `replaces` after statuses are decided, and drop any link whose target the user marked current.
   - A "usable: yes" override only overrides the AI's usable verdict, never the channel limits.
   - `no_crop` reaches the ranking text.

**What changes:**
- **Files:**
  - `app/brand/reader.py`: `_extract_facts`, `_needs_facts`, `_index_sections`
  - `app/brand/settle.py`: `settle`, `usable_facts`
  - `app/brand/conflicts.py`: fact selection
  - `app/campaign/brand_tools.py`: facts
  - `app/brand/images/reading.py`: notes
  - `app/brand/images/picking.py`: `blocked_reason`, `library_text`
  - `app/brand/service.py`: brand status
- **Tables:** `facts`, `image_info`, `brand_files`, `brands`.
- **Migration:** no.

**Risks:**
- **Keeping facts is only safe if every reader filters them.** If one reader misses the filter, facts from an "example" document reach the writing. That is worse than losing them, so the fix needs a grep of every `select(Fact)` and a test for each reader.
- **Stale notes can block every image.** A failed notes step now leaves those images unusable, so assets get "no image" with a suggestion. That is safer, but the user will notice it.

**Regression tests:**
- Type rule → example → rule: the facts come back without a new read.
- A changed image record plus a failed notes step: the image is blocked, and the brand shows the problem.
- A document wrongly linked as "replaced" and then set back to current by the user stops losing conflicts with the rule "replaces".
- A "usable: yes" override still respects a channel limit.

**Size:** medium.

---

## Group 6: inputs and stage changes are checked in the UI or the AI path, not at the API

**Findings:**
- **Confirmed:** #8 (duplicate card ids and unused channels), #20 (an empty plan can be approved), #36 (a question card with one option; re-run today), #40 (bad field shapes in a hand edit cause a 500), #37 (a file and folder with the same name cause a 500 and leave files on disk).
- **Confirmed by reading:** #31 (research with no target is never used), #32 (dates are cut to 10 characters), #34 (retry becomes the new brief), #35 (an old question is answered after approval and treated as an asset edit), #41 (one swap counted twice in one save).

**Root cause (confirmed):**
- **Checks only on the AI path.** The AI path validates (`_checked_plan`), and the hand path doesn't: `update_plan` and approve skip it.
- **Checks only in the UI.** The UI disables buttons, and the API doesn't check.
- **Questions have no lifecycle.** The stage machine checks the stage, but questions don't know which stage they were asked at.

**Proposed design:**
- **One plan validator for every path.** It is used by `_checked_plan`, `update_plan`, `_add_assets` and `approve`. It checks for unique ids, allowed types, only channels the brand uses, at least one card, and string fields.
- **Typed content models.** Each asset type gets a Pydantic content model, built from `writer.FIELDS`, and the hand-edit route uses it. A wrong shape gives a 422 with the field's name, not a 500.
- **Questions remember their stage.** Each question records the stage it was asked at. When the stage moves on, open questions are marked expired, and the card shows "no longer needed". Answering one returns 409.
- **At least two options.** `_options` always returns two or more, adding "Leave it as it is" next to "You decide".
- **A failed brief review keeps the brief.** It shows a Try again button that runs the review on the stored brief again, and the note says "or paste a new brief". Typing "try again" no longer silently becomes the brief.
- **Research must name a target.** Chat research with no target asset is refused with a clear line, or tied to every asset the edit targets. It is never saved unused.
- **Dates.** They are parsed into a real date, or kept whole when they can't be parsed. They are never cut short.
- **Uploads.**
  - Check the whole path list before anything is written; a file that is also a folder gives a 400.
  - Write into a temporary folder and move it into place only when everything succeeds.
- **Hand fixes.** Count each wording swap at most once per save.

**What changes:**
- **Files:**
  - `app/campaign/agent.py`: `_checked_plan`, `_options`
  - `app/campaign/service.py`: `update_plan`, `approve`, `answer`, `_review`, `_edit_assets`
  - `app/chat/schemas.py` and `routes.py`
  - `app/campaign/research.py`: `on_request`
  - `app/research/client.py`: `_date`
  - `app/brand/service.py`: upload
  - `app/campaign/assets.py`: `_repeated_fix`
  - frontend question card and Try again button
- **Tables:** none new. Question data lives in `campaigns.questions` (JSONB).
- **Migration:** no.

**Risks:**
- **Stricter models break old payloads.** Strict content models could reject payloads the frontend sends today. For example, if the frontend sends `sources` as null, the model must accept that or the frontend must change.
- **Expiring questions changes old chats.** Open cards in existing chats flip to "no longer needed".

**Regression tests:** one per bullet above, through the API, which is the seam that was missing.

**Size:** many small local changes.

---

## Group 7: keyword matching decides things that need a structured answer

**Findings:**
- **Confirmed:** #7 (any "x" in a path counts as the X channel), #14 (the hashtag check fires on rules that allow hashtags; re-run today, both examples still fire).
- **Confirmed by reading:** #16 (the brief's image rules are only a hint to the ranking model), #24 (a one-word quote passes as proof).
- #15 is the same kind of mistake, and is covered in Group 4.

**Root cause (confirmed):** decisions that need understanding are made with a regex or a substring on free text:
- Does the brand use X?
- Are hashtags allowed?
- Does the brief ban screenshots?

Each fix widens or narrows the pattern, and it breaks the other way. The hashtag regex has already been patched twice.

**Proposed design:**
- **Channels (free, no model call).** Match whole words from the structured card fields (`rules_on`, `mentions.channels`) against a closed list, drop the bare "x", and stop matching file paths.
- **Hashtags (one small model call per brand).** `writing_rules.ensure` already makes one AI call per brand to pull out banned words and limits. Its schema also returns, per channel, `hashtags: {allowed, max}`, and the free check uses that number instead of the regex.
- **Brief image rules.** The brief review's schema returns structured `image_exclusions` (image types or tags to keep off). These become a hard block in `blocked_reason`, so ranking and the check step both obey them.
- **Proof quotes.** A quote must be at least a few words long (for example, 4 words or more) to count as proof. The ticket text should say which card fields have no proof.

**What changes:**
- **Files:**
  - `app/campaign/agent.py`: `channels_in_use`
  - `app/campaign/brand_tools.py`: `CHANNEL_WORDS`
  - `app/brand/writing_rules.py`: schema and version
  - `app/campaign/checks.py`: `forbids_hashtags`, replaced
  - `app/campaign/prompts.py`: `REVIEW_SCHEMA`
  - `app/campaign/assets.py`: `_spec`
  - `app/brand/images/picking.py`
  - `app/brand/evidence.py` or `cards.py`: minimum quote length
- **Tables:** `brands.writing_rules` (JSONB), `campaigns.brief_rules` or a new JSONB key inside `questions`/`plan`.
- **Migration:** no.

**Risks:**
- **Real-model runs are needed.** The writing-rules and brief-review changes alter prompts, so they need real-model checks. The OpenAI key is at $5.75, already past the $5 cap, so I need your approval for that spend.
- **A wrong hard block hides images.** If the model reads a brief's image rule wrongly, a hard block hides images that should be allowed. The block should be shown on the plan, so the marketer can see it and remove it.
- **Old briefs.** Campaigns reviewed before the change have no structured image exclusions, so they keep today's behaviour.

**Regression tests:**
- A brand with only email and LinkedIn playbooks plus a `context.md` plans no X post.
- Rules that allow two hashtags give no hashtag warning, while a "no hashtags" rule still warns. These are fake-model tests of the structured value.
- A brief saying "no screenshots" blocks a screenshot, even when the ranking model returns it.

**Size:** medium. The channel and quote parts are small and free; the other two need model runs.

---

## Group 8: "current documents only" and "internal is never in charge" are enforced in some places only

**Findings:** #2 (an internal document wins as "owner"; confirmed by probe), #17 (the read-document tool returns replaced and archived documents; confirmed by probe).

**Root cause (confirmed):**
- **No single filter for current documents.** Each reader filters documents its own way. `brand_tools._documents` and `agent._document` don't filter by status.
- **The owner rule falls back to internal documents.** `owner_step` (`conflicts.py`) falls back to internal documents when every owner is internal.

**Proposed design:**
- **One filter.** A single `current_documents(session, brand_id)` is used by every lookup tool and by `agent._document`. A replaced document can still be read, but only labelled "background only: replaced by X".
- **Internal never counts as in charge.** In `owner_step`, an internal document never counts as in charge. If only internal documents own the topic, the owner rule is skipped and the next rule decides.

**What changes:**
- **Files:** `app/campaign/brand_tools.py`, `app/campaign/agent.py`, `app/brand/conflicts.py`.
- **Migration:** no.

**Risks:**
- **Conflict winners can change.** This affects existing brands on the next settle, which runs after any correction or read. The Conflicts tab will show new winners.

**Regression tests:**
- Internal-only owner against a public guide: the public guide wins with a later rule.
- `read("old/…-old.md")` returns the background label, or is refused.
- A push-back quote from a replaced document isn't accepted as proof.

**Size:** small.

---

## Group 9: costs are added up by guessing, not from the calls an action made

**Findings:** #27 (edit costs don't match), #38 (image picks from the Brand page count as reading cost), #43 (the script's edit cost includes the memory call), and #28 (cache hit rate per step isn't shown). All are confirmed by reading.

**Root cause (confirmed):** costs come from summing `ai_calls` by their nullable `chat_id` and `brand_id`, or from totals taken before and after. They don't come from the list of calls an action actually made.
- Versions already store `call_ids`, but the router call isn't in them.
- Brand-page picks have no chat, so they look like reading.

**Proposed design:**
- **Every action keeps its own call list.**
  - The edit message's `data` stores every call id, including the router's.
  - The cost panel and the run script sum those ids.
  - Restores are listed.
- **Brand-page image picks** get their own step name (for example "Image choice (Brand page)"), which the reading cost leaves out.
- **The cost panel** shows the per-step cache hit rate that the API already returns.

**What changes:**
- **Files:** `app/campaign/service.py` (`_edit_assets`), `app/campaign/costs.py`, `app/brand/service.py` (cost), `app/brand/routes.py` (pick), `scripts/run_briefs.py`, frontend `CostPanel.tsx`.
- **Migration:** no.

**Risks:** cost numbers in the docs change once this lands.

**Regression tests:**
- A chat edit's panel cost equals the chat's "Edit cost".
- A Brand-page pick isn't in the reading cost.

**Size:** small.

---

## Group 10: uploaded SVGs run as pages on the app's own address

**Finding:** #22 (confirmed).

**Proposed design:**
- Serve brand images with `X-Content-Type-Options: nosniff`.
- For SVGs, also send `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`, so scripts never run when an image link is opened directly.
- `<img>` tags keep working.

**What changes:**
- **File:** `app/brand/routes.py`, where files are served.
- **Migration:** no.

**Risks:** none known.

**Test:** an SVG response carries the headers.

**Size:** small. It is independent of the other groups and could go first.

---

## Group 11: docs, scripts and the prompt cache have drifted

**Findings:** #29 (COSTS.md and DECISIONS.md are out of date, and DECISIONS.md is too long), #42 (the run-script commands don't work on a fresh copy), #30 (the writer, fix and edit prompts don't use the per-channel cached part).

**Not a design problem.**

**What to do:**
- Fix the brief file names and the location of `data/briefs`, which is ignored by git today. Make the script handle "planning failed" without crashing.
- Rewrite COSTS.md and DECISIONS.md **last**, after the batches below have changed the behaviour.
- #30 is only about speed and cost. Moving the channel rules into the cached part changes every prompt, so it should come after the real-model checks, if at all.

**Size:** small.

---

## Findings that are symptoms of the same problem

- **Group 1, one line of code:** #9, #39, part of #10 and #34 all come from `AiService._finish` committing the caller's session. Fixing that one line, plus the "no lock across AI calls" rule, removes all four.
- **Group 2, no campaign version check:** #10, #19, #26 and #33 are the same missing check. One guarded-save helper fixes all four.
- **Conflict key:** #1 and #21 are both caused by the conflict key.
- **Incomplete history:** #11, #12 and #13 all come from history that doesn't hold the whole state.
- **Delete-or-trust-stale:** #4, #6 and #39 are the same pattern.
- **Keyword matching:** #7, #14, #15 and #16 are the same habit. Each earlier fix moved a pattern, and broke a different case.

## Where fixing one thing could break another

1. **Group 1 vs. foreign keys.** Logging on a separate session fails for any AI call that names a chat or brand the caller hasn't committed yet. Every caller has to be checked first.
2. **Group 1 vs. the progress UI.** Removing commits in the wrong place makes the writing screen look frozen.
3. **Group 2 vs. planning.** If research bumps `plan_version` partway through `_plan`, planning refuses its own save.
4. **Group 4 vs. existing data.** A new conflict-key format that doesn't also read the old one drops every choice the user has already made.
5. **Group 4, memory merging.** The rule has swung twice already. Whichever way it goes, one of the earlier review's examples changes behaviour, so the expected pairs should be agreed and written as tests first.
6. **Group 5, keeping facts.** Kept facts are only safe if every reader filters by type. If one reader is missed, it leaks facts into the writing.
7. **Groups 5 and 7, blocking images.** Stricter image blocking (stale notes, brief exclusions) can leave assets with no image at all.
8. **Group 3 vs. old tests.** Undo now shows a version's latest warnings, which changes what older undo tests expect.

---

## Proposed order: independently testable batches

Each batch ends with the full fake-AI test suite passing, plus that batch's new tests. None of them needs a database migration.

| Batch | What | Groups | Needs real-model spend? |
|---|---|---|---|
| **0** | SVG headers | 10 | No |
| **1** | Transaction boundaries: log on its own session, no lock across AI calls, image "pick then reserve", sections swapped in one go, brief failure leaves nothing half-saved | 1 | No |
| **2** | Campaign guarded save: `plan_version` checked on plan, research, approve and answer; Check again version check; frontend sends `base` | 2 | No |
| **3** | Complete history: Check again warnings on the version, failed-check edits kept, memory undo restores dropped items, history records keep the marketer's edits | 3 | No |
| **4** | API validation: one plan validator, typed hand-edit content, question expiry, two options, Try again for the brief, research targets, dates, safe uploads, hand-fix count, whole-word channel matching | 6, channel part of 7 | No |
| **5** | Brand data: facts kept and filtered, stale image notes count as unchecked, `replaces` follows corrections, override limits, current-documents filter, internal never in charge | 5, 8 | No |
| **6** | Identity: conflict key by point (reading old keys too), preload identity, stored exclusions, removed files, the agreed memory-merge rule | 4 | No |
| **7** | Structured rules: hashtag allowance from the writing-rules step, brief image exclusions, minimum quote length | 7 | **Yes**, small; needs your OK because the key is past $5 |
| **8** | Costs, then docs and scripts last | 9, 11 | No |

**Why this order:**
- **Batch 1 comes first** because batches 2, 3 and 5 depend on a save being all-or-nothing.
- **Batch 2 before Batch 3,** because both touch Check again.
- **Batches 5 and 6 are both brand-side.** They are kept apart so that a change to conflict winners can be traced to one of them.
- **Batch 7 is the only one that changes prompts,** so it goes last among the code changes, and it is the only one that costs money to verify.

**Decisions I need from you before starting:**
1. **Memory merging (Group 4):** should only reorderings and filler changes merge automatically, with every other merge left to the model's `replaces`?
2. **Stale image notes (Group 5):** is it OK that they block the image, rather than keep the old verdict?
3. **Batch 7:** do you approve the small real-model spend to verify it, now or later?
