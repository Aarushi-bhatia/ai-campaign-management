# How to test the app by hand

This walks you through the whole app using one test brief. The brief has mistakes in it on purpose. A good app catches them and follows the brand's rules instead.

Do the tests in order. Later tests use the campaign you made in earlier ones.

**How to read each test**

- **Do:** what to click or type.
- ✅ **You should see:** this must happen. If it doesn't, it's a bug.
- ❌ **You should NOT see:** if this shows up, it's a bug.
- 〜 **May vary:** the AI decides this, so it can come out a bit differently and still be fine. If it looks wrong, try once more before calling it a bug.

**Words used here**

- **Piece:** one thing the app writes, like one email or one X post. (The app calls these "assets".)
- **Plan:** the list of pieces the app will write, shown as cards on the right.
- **Warning:** a yellow note on a piece saying something in it may break a rule.
- **Version:** every change to a piece saves a new copy, so you can go back.

**Before you start**

- The app is running and the Wickhold brand is loaded (the Brand page says it's ready).
- **Money:** one full run of this test costs about $0.60 to $1.00. Typing edits by hand is free. The OpenAI key has used about $7.76 of $10, so there's room for one full run and a few retries.

---

## The brief

Paste this into a new chat. A copy is saved at `backend/data/test-briefs/brief-4-on-call-week.md`.

```text
# On-call week, March 2027

**From:** Kofi Anselm, Developer Relations
**To:** Campaign team
**Date:** November 5, 2026

Every platform engineer I talk to has the same complaint about on-call: they get paged for things they can't act on, at 3am, and spend the first hour working out what happened. I want a campaign in March that speaks to exactly that person, and shows how Quenchline takes the first action for them.

## The idea

Tagline: **"Sleep through the night."** It's short, it's true, and on-call people will get it immediately.

Open with the problem. Our 2024 Field Report found that 3 in 5 teams get paged for incidents they can't act on, so let's lead with that number everywhere.

Then the answer: Quenchline contains attacks in 38 seconds, so by the time you open your laptop the pod is already isolated. Back it up with Lowmoor Credit Union, who now contain incidents 20x faster than before. And say we're trusted by 140+ customers.

For the second LinkedIn post, I'd like us to be braver than usual. Explain why Tesserline's alert-only approach leaves the on-call engineer holding the problem. Name them; everyone knows who we mean anyway.

In the email, add a P.S. teasing Leashgate: "Running AI agents? Leashgate prevents prompt injection too."

## What to make

- One email to the platform leads list
- Two LinkedIn posts
- Two X posts. Put #Kubernetes #eBPF #OnCall at the end of each so they get found.
- One blog post, a proper walkthrough of what happens in the first minutes of an incident
- One landing page, with "Book a demo" as the main action

## Images

No product screenshots this time; they never read on a phone. Photos of real engineers on call would be great.

## Timing

Goes live Tuesday, March 2, 2027, and runs through March 26, 2027.

Thanks,
Kofi
The Wickhold Security team
```

---

## The 12 mistakes hidden in the brief

This is the most important list. Check every piece the app writes against it.

| # | The brief says | Why that's wrong | What the app should write instead |
|---|---|---|---|
| 1 | Tagline "Sleep through the night." | The brand stopped using this line. | A different line, or no tagline. |
| 2 | "3 in 5 teams" from the 2024 Field Report | Old numbers can't be used, and that report was taken back. | Leave it out, or use the 2026 report: "41% of platform teams need more than six hours to contain a runtime incident" (with the report's name and year). |
| 3 | "contains attacks in 38 seconds" | 38 seconds is a lab test result, not a promise. | "contains a known-bad process in a median of 38 seconds in Wickhold lab benchmarks, 2026", or no number at all. Never "attacks". |
| 4 | Lowmoor is "20x faster" | You can't turn the result into "20x" or a percent. | "from 4 hours to 11 minutes, across 220 nodes", or leave Lowmoor out. |
| 5 | "140+ customers" | Only one wording is allowed. | "more than 140 customers", exactly. |
| 6 | Name the competitor Tesserline on LinkedIn | Never name a competitor on social media. | No competitor name in any post, email or landing page. "Alert-only tools" is fine. |
| 7 | "Leashgate prevents prompt injection" | This claim isn't allowed, and Leashgate is still in early access. | Drop the P.S., or say Leashgate "limits what a compromised agent can do". |
| 8 | Hashtags on the X posts | The brand decided: no hashtags on X, ever. | X posts with no hashtags. |
| 9 | "No product screenshots" | This is the brief's own rule, so the app should follow it. | No piece uses a product screenshot. |
| 10 | "Photos of real engineers" | You can only show a real person's face if they signed a form saying yes. | Only photos that are cleared. Otherwise "No suitable image" with a suggestion. |
| 11 | Signed "The Wickhold Security team" | That's the company's old name. It's now just "Wickhold". | "Wickhold Security" never appears. |
| 12 | (not in the brief) | Brand length rules. | X posts up to 240 characters. LinkedIn posts up to 180 words. Email subject up to 48 characters. The email ends with "Wickhold, Inc.", a Denver address and an unsubscribe link. (It's OK if the address is a blank like "[Denver postal address]" with a warning to fill it in.) |

---

## Part A: Paste the brief

**A1. Paste the brief and send it.**

✅ You should see:
- One question at a time, with a few buttons to pick from and a box to type your own answer.
- A note near the top: "Using 3 things you told me before…".
- Notes like "Tagline: four brand documents disagree. I used [document], because it is newer." These say which brand document the app trusted. That's fine.

〜 May vary:
- About 3 to 5 questions. They'll mostly be about mistakes 2, 3, 4, 5, 6 and 7 from the table.
- The first button on each question is the safe choice (follow the brand). There's usually also a "follow the brief as written" button.
- Mistakes it doesn't ask about, it should quietly fix.

❌ You should NOT see:
- A question about something the brief already says (the dates, which pieces to make, who it's for).
- A note saying "Your brief changes a brand rule, for this campaign only: …" before you've answered anything. The app must never decide that alone. If the brief would change a brand rule, you get a question instead: "Your brief would change a brand rule: … Allow that for this campaign?", with "No, keep the brand rule" first.

**A2. Answer the questions.** Click the first (safe) button on each one, except for the question about Tesserline (the competitor). For that one, type:
"Keep Tesserline out of social, but the blog post can compare approaches without naming anyone."

✅ You should see:
- Each answer shows up in the chat as your message.
- The next question appears. After the last one, the app makes the plan.

**A3. (Optional, about $0.03) Ask for a vague change.** Type "Make it better".

✅ You should see: the app asks back what you mean ("Better how?") with buttons.
**Don't answer it.** You'll use it in test D10.

---

## Part B: The plan

**B1. Look at the plan on the right.**

✅ You should see:
- 7 cards: 1 email, 2 LinkedIn posts, 2 X posts, 1 blog post, 1 landing page.
- Each card has who it's for, the main message, a date, and an image idea. The date is a March date or "to be set" (the brief gives only the start and end of the campaign, so "to be set" is fine).
- A box called "Images this campaign keeps off" that lists **product screenshot**, quotes the brief's words, and has an **Allow** button.

❌ You should NOT see, on any card: "attacks in 38 seconds", "20x", or Tesserline on a social post.

〜 May vary: the blog post (and maybe the landing page) has web research links with dates.

**B2. Edit a card by hand.** Click Edit on the second X post, change its title, and save. Then drag a card to a new spot.

✅ You should see: it saves straight away and costs nothing. The new order stays.

**B3. Remove a research link** (if there are any). Click its remove button.

✅ You should see: it moves to a "removed" list, and you can bring it back. A removed link is never used in the writing.

**B4. Change the plan by chat.** Type "Drop the second LinkedIn post."

✅ You should see: that card goes away. The other cards stay the same.

**B5. Two tabs at once (saving).** Open the same chat in two browser tabs. In tab 1, delete a card. In tab 2, without refreshing, edit a card and save.

✅ You should see: tab 2 says "Someone changed the plan (in another tab or in the chat), so your change wasn't saved…" and shows the latest cards. Tab 2's change isn't saved.

**B6. Two tabs at once (approving).** Refresh tab 2. Change a card in tab 1. Then press Approve in tab 2 without refreshing.

✅ You should see: "The plan changed since you last saw it, so it wasn't approved." Refresh and approve normally.

**B7. The Allow button.** Don't press it for this test run. (If you do, "product screenshot" disappears from the box and screenshots become allowed again.)

**B8. Ask the chat to allow screenshots.** Type "Screenshots are fine after all."

✅ You should see: the box still lists product screenshot.
〜 May vary: the reply tells you to use the Allow button.

---

## Part C: Writing

**C1. Approve the plan.**

✅ You should see:
- "Plan approved. Writing N assets…" and the plan locks.
- Each card goes Waiting → Writing → Checking → Done. The first one is written alone, then a few at a time.
- When each one finishes, a line in the chat says what it looked up and which image it used (or "no image").

**C2. Read every piece and check it against the 12 mistakes.** This is the main test.

❌ These words should NOT appear anywhere:
- "Sleep through the night"
- "3 in 5" or "Field Report"
- "contains attacks"
- "20x"
- "140+"
- "Tesserline" (in posts, the email or the landing page)
- "prevents prompt injection"
- "Wickhold Security"
- "#Kubernetes", "#eBPF" or "#OnCall" in the X posts
- Wrong capital letters: "QuenchLine", "EvenBurn", "LeashGate"
- "seamless", "best-in-class", "guaranteed"

✅ If these are used, they must be written exactly like this:
- The 38 seconds must say "known-bad process" and "in Wickhold lab benchmarks, 2026" in the same sentence.
- Lowmoor must say "4 hours to 11 minutes" and "220 nodes".
- The customer count must say "more than 140 customers".
- Any market number must name the 2026 report or a dated source.

✅ You should also see:
- The full product name the first time in each piece ("Wickhold Quenchline"), then just "Quenchline" after that.
- "contain mode" in small letters.
- X posts up to 240 characters, LinkedIn up to 180 words, email subject up to 48 characters. If one is too long, it shows a "length" warning.

✅ **The safety net:** if a piece still has one of the banned things, it must show a warning about it. A banned thing with **no** warning is a bug.

**C3. Images.**

❌ You should NOT see:
- A product screenshot on any piece.
- A photo of a real person whose permission isn't on record.

✅ You should see:
- Each image has a short description of what's in it.
- "No suitable image" with a suggestion is a fine result.

**C4. Warnings.**

〜 May vary: the email warns that the Denver address and unsubscribe link need filling in. Posts may warn that a link is missing. That's honest, because the brief didn't give them.

✅ You should see: every warning quotes words that really are in the piece.

**C5. The Costs tab.**

✅ You should see:
- The total matches the "Campaign cost" at the top of the chat.
- Costs broken down by step and by piece.
- An "Every call" list you can open.

〜 May vary: about $0.40 to $0.80 so far.

---

## Part D: Making changes

**D1. Change a piece by chat.** Type "Make the first LinkedIn post shorter, about half the length."

✅ You should see:
- Only that post changes, as a new version.
- The reply ends with "Edit cost: $X".
- The Costs tab shows the same $X for this edit.

**D2. Change one part by chat.** Type "Rewrite the subject line of the email to be more specific."

✅ You should see: only the subject changes. The rest of the email stays the same. The subject is still 48 characters or fewer.

**D3. Edit by hand (free).** On the first X post, click Edit and add the hashtag "oncall". Save.

✅ You should see:
- It costs $0.
- A warning: "hashtags: Uses 1 hashtag (#oncall); the channel rules say no hashtags."

Then type "Sleep through the night." into the text and save. ✅ You should see a "banned word" warning.
Then type "Wickhold Security" and save. ✅ You should see an "old name" warning telling you to use "Wickhold".

**D4. Undo and compare.** Press Undo on that X post until it's back to how the app wrote it.

✅ You should see:
- Each Undo makes a new version.
- The hashtag and banned-word warnings go away.
- Compare shows what changed between two versions.

**D5. Check again.** On the email, press Check again.

✅ You should see: the AI checks it again (costs about half a cent to a cent), and the new result replaces the old one.

**D6. Two tabs at once (editing).** Open the email in two tabs. Edit and save in tab 1. In tab 2, without refreshing, edit and save.

✅ You should see: tab 2 is refused because the email changed. Tab 1's change is kept.

**D7. Add a piece by chat.** Type "Add one more X post for the last week of the campaign."

✅ You should see: a new card in the plan, and only that new post is written. It follows the same rules: no hashtags, up to 240 characters, no screenshot.

**D8. Remove a piece by chat.** Type "Remove the blog post." Then click the button in the note to bring it back.

✅ You should see: the blog post is removed, then comes back with its history.

**D9. Change an image by chat.** Type "Use a different image for the landing page."

✅ You should see:
- The landing page gets a different image, as a new version. Its text stays exactly the same.
- The reply says which image it now uses and why, with its cost (about a cent).
- Undo brings the old image back.
- If no other image fits, the reply says so and nothing changes.
- Then type "No image on the X post": it says it took the image off (or that it already has none).

**D10. Answer an old question.** If you left "Better how?" unanswered in A3, click one of its buttons now.

✅ You should see: it says the question "no longer applies", the question shows as expired, and nothing changes.

---

## Part E: Memory

The app learns your preferences from what you type in the chat. Each test here costs about 1 to 4 cents. If your message is about a piece (like the X posts), the app may also edit that piece.

**E1. Teach it something.** Type "From now on, keep X posts under 200 characters."

✅ You should see: a note "Remembered: …" with an Undo button. The Memory page lists it.
〜 May vary: the X posts get shortened too.

**E3. Say the same thing in a different order.** Do this right after E1: "X posts, from now on, keep under 200 characters."

✅ You should see: nothing new is remembered. It knows it's the same thing.

**E2. Change your mind.** Type "Actually, X posts can use the full 240 characters."

✅ You should see: the new rule is saved next to the old one. The old one isn't quietly changed.
〜 May vary: the note offers a **Replace it** button. If you press it, the old rule goes and the new one stays. Pressing Undo after that puts the old rule back.

**E4. Something just for this campaign.** Type "For this launch only, keep the LinkedIn posts under 100 words."

✅ You should see: it is NOT remembered, because it's only for this campaign.

**E5. "Remember this?"** Edit a piece by hand and swap one word for another (for example "engineer" → "operator"). Do the same swap on another piece.

✅ You should see: after the second time, the chat asks "Remember this?". Saying yes saves it.

**E6. The Memory page.** Edit, pin and delete some items.

✅ You should see:
- An edit is saved exactly as you typed it.
- A deleted item no longer shows in the next campaign's "Using N things you told me before".
- An old "Remembered" note's Undo won't wipe an item you've edited since.

**Clean up afterwards:** delete the items these tests added, so they don't affect later campaigns.

**E7. (About $0.10) A new campaign uses memory.** Start a new chat with "Two X posts for Slow Burn Summit registration."

✅ You should see: the first note lists which remembered items it used.

---

## Part F: The Brand page

**F1. Correct a document.** Open a document and change its status or type.

✅ You should see: it changes straight away, for free. Undo it afterwards.

**F2. Settle a disagreement.** Where two documents disagree, pick a winner, then undo.

✅ You should see: it shows as decided, and undo puts it back. It does NOT show up on the Memory page.

**F3. Unblock an image.** Mark a blocked image "usable: yes".

✅ You should see: it can now be used, but still not on channels its notes rule out, and still not if a campaign's brief bans that kind of image. Set it back afterwards.

**F4. Try picking images** (on the Images tab). Run one pick.

✅ You should see: a ranked list with reasons, and the blocked images with reasons. It costs about half a cent to a cent. The "Reading the brand" cost on the Costs tab doesn't go up.

**F5. Update brand.** Click the button and choose the folder, but **don't upload**.

✅ You should see: the folders you skipped last time are already filled in. Cancel. (Uploading starts a re-read, which costs money.)

---

## Part G: Free quick checks

- **G1.** With no cards in the plan, the Approve button is greyed out.
- **G2.** Every AI message has a **View prompt** link showing exactly what was sent to the AI.
- **G3.** Uploading a brand folder with a file and a folder of the same name ("a.md" and "a.md/b.md") is refused, and nothing is saved.
- **G4.** An uploaded SVG picture opens as a picture, not as a web page.

---

## If something doesn't match

Write down which chat it was, which piece and version, and what you expected. **View prompt** on a message shows what the AI was given. The Costs tab's "Every call" list shows every AI call that ran.

- A ✅ that didn't happen, or a ❌ that did, is a bug.
- A 〜 that looks off may just be the AI being different. Try once more before calling it a bug.
