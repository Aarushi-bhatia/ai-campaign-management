# Screen recording: the whole flow

One brief from start to finish, plus the small things. About 20–25 minutes; cut what you don't need.

Each step has:
- **Do:** what to click.
- **Type:** exactly what to type (copy it).
- ✅ **You'll see:** what should appear.
- 〜 **May vary:** the AI decides this, so the wording or number can differ. That's fine.
- **Say:** one line to say, in your own words. Optional.

**Money:** about $1.00–1.30 for the whole recording. Everything marked **free** makes no AI call.

---

## Before you record

1. The app is running at http://localhost:5173.
2. Bottom left, the **Brand** card shows **Wickhold** (click it and pick Wickhold if not).
3. Delete leftover test memory: open **Memory**, delete anything like "operator" or "200 characters".
4. Keep the brief ready to paste: `backend/data/test-briefs/brief-4-on-call-week.md` (all of it).
5. Full screen browser, zoom 100%.

---

## Part 1: Brands (free, 2 min)

**1.1 The brand switcher.**
- **Do:** Click the **Brand** card at the bottom left.
- ✅ A list opens just above it: **XYZ** and **Wickhold**, each with a coloured dot and "Ready". A tick is next to Wickhold. "Add a brand" is at the bottom of the list.
- **Say:** "One app, several brands. Each brand has its own documents, memory and chats."

**1.2 Switch to XYZ.**
- **Do:** Click **XYZ**.
- ✅ The list closes. The card shows XYZ. Above it, the heading changes to **XYZ**, and the chat list shows only XYZ's chats ("heyyy").
- **Do:** Click **Memory**.
- ✅ The heading says **Memory: XYZ**. XYZ's memory is separate from Wickhold's.

**1.3 A new campaign follows the chosen brand.**
- **Do:** Click the **Brand** card → **Wickhold**. Then click **New campaign**.
- ✅ The chat says: "This campaign will use **Wickhold**. Switch brands at the bottom left."
- ✅ The chat list now only shows Wickhold's chats.
- **Say:** "New campaigns use the brand chosen here. Old chats keep the brand they started with."

**1.4 Adding a brand (show only, don't upload).**
- **Do:** Brand card → **Add a brand**.
- ✅ The page to upload a brand folder.
- **Say:** "You upload a folder. The app reads it once: about $1.60 for 84 documents. Until it's ready, New campaign is greyed out with 'still being read'."
- **Do:** Go back to your new chat in the sidebar. **Don't upload.**

---

## Part 2: The Brand page (free except 2.5, 3 min)

**Do:** Click **Brand page**.

**2.1 Documents tab.**
- ✅ Every document with its kind, status (current, replaced, draft, archived) and the reason, with a quote from the document as proof.
- **Do:** Find `Brand_Guidelines_v3_FINAL.md`.
- ✅ It's **replaced**, by `Brand_Guidelines_2026.md`.
- **Say:** "'FINAL' in a file name means nothing. A document that says it replaces another wins, and the quote proves it."

**2.2 Conflicts tab.**
- ✅ Each disagreement, which document won, and why, for example: "approved-claims-2026.md is in charge of customer count; sales-deck-notes-q3.md is internal".
- **Say:** "The AI only finds disagreements. Plain code picks the winner in a fixed order: replaces, then who owns the topic, approved, newer, live. If nothing settles it, a person decides here."

**2.3 Names tab.**
- ✅ Product names with their short forms, and old names with proof: "Wickhold Security" → "Wickhold".

**2.4 Brand summary tab.**
- ✅ A short summary built only from the facts that won.
- **Say:** "Only this summary goes into every prompt. The agent looks up the rest with tools, so a small X post doesn't pay for 84 documents."

**2.5 Images tab (about 1 cent).**
- **Do:** Click **Try picking images for an asset**, pick a channel, run it.
- ✅ A ranked list with reasons, and a list of **blocked** images, each with why (for example no consent form, or a retired product screenshot).
- **Say:** "Banned images are removed by rules before the AI ranks anything, so it can't pick one."

---

## Part 3: Memory page (free, 30 sec)

**Do:** Click **Memory**.

- ✅ Heading **Memory: Wickhold**. Two tabs: **Core memory (N/50)** and **Campaign history (N)**.
- ✅ Each item has **Pin**, edit and delete.
- **Say:** "Core memory is up to 50 rules that go into every prompt. History is short records of past campaigns, read only when planning, so new plans don't repeat old ones."

---

## Part 4: Paste the brief (about $0.10, 3 min)

**Do:** Open your new chat. Paste the whole brief. Press Enter.

✅ You'll see:
- A note: "Using N things you told me before: …" (the memory items it used).
- Possibly notes like: "Tagline: four brand documents disagree. I used Brand_Guidelines_2026.md, because it is newer."
- "Before I plan, I need N answers. One at a time:" and the first question card.
- Each card: the question, a short "why" that **quotes a brand sentence and its file**, the safe option first and marked **(suggested)**, and a box to type your own answer.

〜 May vary: 2–5 questions. Most likely about: the old Field Report number, "38 seconds", "20x faster", "140+ customers", naming Tesserline, the Leashgate P.S.

**Say:** "This brief has 12 planted mistakes. The agent doesn't copy them. It pushes back with the brand's own sentence, and fixes the small ones quietly."

**4.1 Answer the questions.**
- **Do:** Click the first (suggested) button on each one…
- …**except** a question about **Tesserline**. For that one, type in the card's box:

  ```
  Keep Tesserline out of social, but the blog post can compare approaches without naming anyone.
  ```
- ✅ Your typed words show in the chat exactly as you typed them, and the next question comes.

**4.2 If a card starts "Your brief would change a brand rule: …"** (may not appear for this brief).
- **Type** in the chat box: `maybe`
- ✅ "I need a clear yes or no here, so a brand rule isn't changed by mistake. Pick one of the two answers." The same question appears again. The old card says "“maybe” wasn't a clear yes or no, so this is asked again below."
- **Type:** `no`
- ✅ The card shows **Answered: No, keep the brand rule**.
- **Say:** "A brief can't quietly change a brand rule. Only a clear yes counts."

✅ After the last answer: a web search note ("Searched the web for … : N findings, shown on the plan.") and the plan.

---

## Part 5: The plan (mostly free, 3 min)

**5.1 Look at the plan on the right.**
- ✅ 7 cards: 1 email, 2 LinkedIn posts, 2 X posts, 1 blog post, 1 landing page. Each has audience, main message, date and image idea.
- ✅ A box **"Images this campaign keeps off"** that lists **product screenshot**, quotes the brief's words, and has an **Allow** button.
- ✅ Research findings with a link and date, each with a remove button.
- ❌ No card says "38 seconds" without "lab benchmarks", "20x", or names Tesserline on social.
- **Say:** "Nothing is written until I approve. Fixing a card here is free; rewriting seven pieces isn't."

**5.2 Edit a card by hand (free).**
- **Do:** On the landing page card, click Edit, change the title to:
  ```
  Contain first, investigate after
  ```
  Save.
- ✅ Saves at once. No cost.

**5.3 Remove a research finding (free).**
- **Do:** Click remove on one finding.
- ✅ It moves to a "removed" list and can be brought back. **Say:** "Removed sources are never used in the writing."

**5.4 Change the plan by chat (about 1 cent).**
- **Type:**
  ```
  Drop the second X post.
  ```
- ✅ That card disappears; the rest stay the same. The reply is in the past tense ("I dropped…").

**5.5 Ask for something the brief banned (about 1 cent).**
- **Type:**
  ```
  Screenshots are fine after all.
  ```
- ✅ The box still lists product screenshot.
- 〜 The reply points you to the **Allow** button. **Don't press it.**
- **Say:** "Lifting an image ban is a button, not something the chat can do by accident."

---

## Part 6: Writing (about $0.50, 2 min, mostly waiting)

**Do:** Click **Approve plan**.

✅ You'll see:
- "Plan approved with N research findings. Writing 6 assets, a few at a time."
- Each piece's tab on the right goes **Waiting → Writing → Checking → Done**.
- One note per piece: "LinkedIn post “…” written. Looked up linkedin rules, 30 facts; image images/…jpg." Some add "Fixed: …" or "N warnings left."
- At the end: "6 of 6 assets written. Campaign cost so far: $…"

**Say:** "Each piece is its own AI call with only its own channel rules and facts. Then free rule checks, then an AI check of claims and tone, one automatic fix, and honest warnings for whatever is left."

(Pause the recording while it writes, if you like.)

---

## Part 7: The finished pieces (free, 3 min)

**Do:** Open each tab on the right: email, LinkedIn post, X post, blog post, landing page.

✅ Each shows a realistic preview: inbox, LinkedIn card, X post, article, web page.

**7.1 The 12 mistakes, fixed.** Point at these:
- ❌ Not anywhere: "Sleep through the night", "3 in 5", "Field Report", "contains attacks", "20x", "140+", "prevents prompt injection", "Wickhold Security".
- ❌ X post: no hashtags. LinkedIn, X, email, landing page: no "Tesserline".
- ✅ If used, exactly: "more than 140 customers"; "from 4 hours to 11 minutes, across 220 nodes"; 38 seconds always with "known-bad process" and "Wickhold lab benchmarks, 2026".
- ✅ "Wickhold Quenchline" the first time, "Quenchline" after.
- ✅ No product screenshot anywhere. "No suitable image" with a suggestion is a fine result.

**7.2 Warnings.**
- ✅ Yellow warnings quote the exact words they're about.
- 〜 The email likely warns that the Denver address and unsubscribe link need filling in. **Say:** "It doesn't invent an address. It leaves a blank and warns."

**7.3 View prompt (free).**
- **Do:** Click **View prompt** under any AI message.
- ✅ Exactly what was sent: the fixed part (rules, brand summary, memory), the task, the tool calls, and tokens and cost, including how much was **cached**.
- **Say:** "The fixed part is the same on every call, so it's cached and costs about a tenth."

---

## Part 8: The little checks, by hand (all free, 3 min)

All of these are on the **X post**. Each Save costs $0 and runs the free checks at once.

**Do:** Open the X post → **Edit**.

| Step | Do / type | ✅ Warning you'll see after Save |
|---|---|---|
| 8.1 Hashtag | Add at the end: ` #oncall` | **hashtags:** Uses 1 hashtag (#oncall); the channel rules say no hashtags. |
| 8.2 Banned word | Add: ` A seamless first response.` | **banned word:** Uses “seamless” in text. |
| 8.3 Wrong capitals | Change one "Quenchline" to `QuenchLine` | **banned word:** Uses “QuenchLine” in text. Use Quenchline instead. |
| 8.4 Old name | Add: ` From Wickhold Security.` | **old name:** Uses the retired name “Wickhold Security” in text. Use Wickhold. |
| 8.5 Banned claim | Add: ` Leashgate prevents prompt injection.` | **banned word:** Uses “prevents prompt injection” in text. Use Leashgate limits what a compromised agent can do instead. |
| 8.6 Too long | (by now it's over 240) | **length:** text is N characters; the limit is 240. |

**Say:** "These are plain code checks. No AI, no cost, instant."

**8.7 Undo and Compare (free).**
- **Do:** Press **Undo** until the post is back to how the app wrote it.
- ✅ Each Undo is a new version. The warnings go away one by one.
- **Do:** Click **Compare** on the post (before the last Undo is a good moment).
- ✅ Added words in green, removed words in red, against the version before. Click **Preview** to go back.
- **Say:** "Every change is a version. Nothing is lost."

---

## Part 9: Editing by chat (about $0.10, 3 min)

**9.1 One part of one piece.**
- **Type:**
  ```
  Make the subject line of the email shorter
  ```
- ✅ Only the subject changes (still 48 characters or fewer). The reply says what it did in the past tense, lists the change, and ends with **"Edit cost: $…"**.

**9.2 "Which one?"**
- **Type:**
  ```
  Shorten the LinkedIn post
  ```
- ✅ A question: **"Which LinkedIn post should I shorten?"** with only the two LinkedIn posts, by number and title.
- **Do:** Click one.
- ✅ Only that post is shortened.
- **Say:** "When it isn't sure which piece I mean, it asks, and only offers the ones that fit."

**9.3 Change an image.**
- **Type:**
  ```
  Use another image for the LinkedIn post
  ```
- ✅ The reply names the new image and why. The text stays exactly the same.
- **Do:** Press **Undo** on that post.
- ✅ The old image is back (or no image, if it had none).
- 〜 If nothing else fits, it says so and nothing changes.

**9.4 Remove and bring back.**
- **Type:**
  ```
  Remove the landing page
  ```
- ✅ It's removed. The note says it's hidden, not deleted, with a button to bring it back.
- **Do:** Click that button.
- ✅ The landing page comes back in its place, with all its versions.

**9.5 Add a piece.**
- **Type:**
  ```
  Add one more X post for the last week of the campaign.
  ```
- ✅ A new card in the plan, and only that post is written. Same rules: no hashtags, 240 characters max.

**9.6 Check again (about 1 cent).**
- **Do:** On the blog post, click **Check again**.
- ✅ "Checked … again: N warnings" (or "no problems"), with its cost.

---

## Part 10: Memory (about $0.05, 2 min)

**10.1 It learns a lasting rule.**
- **Type:**
  ```
  From now on, keep X posts under 200 characters.
  ```
- ✅ A note **"Remembered: …"** with an **Undo** button.
- 〜 It may also shorten the X posts.

**10.2 Same thing, said differently.**
- **Type:**
  ```
  X posts, from now on, keep under 200 characters.
  ```
- ✅ Nothing new is remembered. It knows it's the same rule.

**10.3 A one-off is not remembered.**
- **Type:**
  ```
  For this launch only, keep the LinkedIn posts under 100 words.
  ```
- ✅ No "Remembered" note.
- **Say:** "It learns general rules, not one-off requests. And it never learns from the brief itself."

**10.4 "Remember it?" from hand edits (free).**
- **Do:** On one piece, click **Edit**, swap one word for another, for example `engineer` → `operator`. Save.
- **Do:** Make the same swap on a second piece. Save.
- ✅ After the second save: **"You've made this change by hand more than once. Remember it?"**
- **Do:** Click the button to remember it.
- ✅ A "Remembered: …" note with Undo.
- **Say:** "Fixing the same word twice by hand is a rule I never said out loud. It asks, because a hand edit might be meant for one piece only."

**10.5 The Memory page.**
- **Do:** Click **Memory**.
- ✅ Both new items are there. Click **Pin** on one: it shows **★ Pinned**.
- **Say:** "Pinned items are never dropped when memory is full."

---

## Part 11: Costs and wrap up (free, 1 min)

**11.1 Costs.**
- **Do:** Back in the chat, open the **Costs** tab on the right.
- ✅ The total matches **Campaign cost** at the top. Costs by step and by piece, and an **Every call** list.
- **Say:** "Every AI call is logged with its tokens and cost. Small jobs use the small model; writing uses the bigger ones."

**11.2 Brands again.**
- **Do:** Brand card → **XYZ**.
- ✅ The chat list changes to XYZ's chats; the Wickhold campaign isn't in it. **Memory** shows XYZ's memory, without the new items.
- **Do:** Switch back to **Wickhold**.
- ✅ Your campaign is back in the list.
- **Say:** "Each brand keeps its own documents, memory and chats. The design decisions and trade-offs are in DECISIONS.md."

---

## After recording

- On **Memory** (Wickhold), delete the test items: "200 characters" and "operator".
- If a take goes wrong, delete nothing yourself: tell me and I'll remove the chat.
