# Retest after the last fixes

You already tested the whole app by hand. Since then, only these things changed:

1. **Two bug fixes.**
   - Undo now takes an image off again when the piece had no image before.
   - Typing "yes" or "no" to a brand-rule question now counts, just like clicking the buttons.
2. **Code tidy-up, with no change in behaviour.** The code that runs a campaign chat was split into smaller files, and five long functions were split into smaller steps. The automatic tests all pass. Parts 3 and 4 below are a quick check that nothing broke in the real app.

Same symbols as the main test plan:
- ✅ must happen
- ❌ must NOT happen
- 〜 may vary, because the AI decides it

**Money:** about $0.35 in all.
- Answering questions, editing by hand and Undo are free.
- Only the steps marked with a cost call the AI.
- Don't press Approve in Part 1. That would write 11 pieces and cost about $0.40 more.

---

## Part 1: Typing yes or no to a brand-rule question (fix 2)

Use a new chat: paste the Leashgate brief again (the review costs about $0.02 to $0.10). The old Leashgate chat was half-answered before the last fix, so its cards show the old behaviour.

To get the brief, open the old "Campaign brief: Wickhold Leashgate general availability" chat, copy your first message (the whole brief), and paste it into a new chat. The new chat asks about four questions that start "Your brief would change a brand rule: …".

These questions come one at a time. There are about four. If you run out before the last step, skip what's left.

〜 May vary: the AI decides which questions to ask, so the number can differ from last time. If none starts "Your brief would change a brand rule", send me a screenshot.

**1.1 An unclear answer.** Wait for a card whose question starts **"Your brief would change a brand rule: …"**. Other questions (like "Should we…?") take any answer, so "maybe" is fine there; answer those with a button. On the brand-rule card, type in the chat box: `maybe`

✅ You should see:
- A reply: "I need a clear yes or no here, so a brand rule isn't changed by mistake. Pick one of the two answers."
- The same question again, still open, under that reply.
- The card above your "maybe" now says: "“maybe” wasn't a clear yes or no, so this is asked again below." It has no buttons. Even after you answer below, it never says "Answered".

❌ You should NOT see:
- A note starting "Your brief changes a brand rule…".
- The next question, or a plan.

**1.2 A typed yes.** In the chat box, type: `yes`

✅ You should see:
- A note: "Your brief changes a brand rule, for this campaign only: …" with the rule written out.
- The question card now shows the answer **"Yes, for this campaign only"**, not just "yes".
- The next question appears.

**1.3 A typed no, in the card's answer box.** On the next question, use the card's own "type your own answer" box (not the chat box). Type `No` and send it.

✅ You should see:
- Your message in the chat says **"No"**, exactly what you typed.
- The card shows **"Answered: No, keep the brand rule"**: what your "No" counted as.
- The next question appears. It's a different question (the counter says how many are left), so seeing Yes/No buttons again is right.

❌ You should NOT see: a "Your brief changes a brand rule…" note for this question.

**1.4 A mixed answer.** On the next question, type in the chat: `yes, keep the rule`

✅ You should see: the "I need a clear yes or no here…" reply, and the same question again. It can't tell whether you mean yes or no, so it asks instead of guessing.

Now type `allow it`.

✅ You should see: it counts as yes. The note appears, and the card says "Yes, for this campaign only".

**1.5 The last question (about $0.15, the plan is made).** Click either button on any question that's left. After the last answer, the plan appears.

✅ You should see:
- The plan cards on the right.
- The box **"Brand rules your brief changes, for this campaign only"** lists exactly the rules you said yes to (in 1.2 and 1.4, plus any you clicked yes on), and none you said no to.

〜 May vary: the plan's cards and wording.

**1.6 Drop one rule again (free).** In that box, click **Keep the brand rule** on one rule.

✅ You should see: that rule leaves the box.

❌ Don't press Approve.

---

## Part 2: Undo takes an image off again (fix 1)

Use the chat called **"On-call week, March 2027"**, the finished one with 6 pieces. Its second piece is the LinkedIn post "The wait before containment", which has an image.

**Why this order:** the bug only shows when the version Undo goes back to was saved with no image. A hand edit made after taking the image off gives exactly that.

**2.1 Take the image off (about $0.01).** Type: `No image on the LinkedIn post`

✅ You should see:
- A reply that says it took the image off.
- The LinkedIn post now shows no image.

**2.2 Edit by hand (free).** On the LinkedIn post, click Edit. Add a few words at the end, for example "Typed by hand." Save.

✅ You should see: your words are in the post, and there's still no image.

**2.3 Add an image by chat (about $0.02).** Type: `Use another image for the LinkedIn post`

✅ You should see:
- A reply that says which image it now uses.
- The post shows an image again.
- Your "Typed by hand." words are still there.

〜 May vary: which image it picks. If it says nothing fits, the fix can't be tested this way. Skip to Part 3.

**2.4 Undo (free).** Press Undo on the LinkedIn post once.

✅ You should see:
- **The image is gone again.** This is the fix.
- Your "Typed by hand." words are still there.

❌ You should NOT see: the image from 2.3 still on the post after Undo. That was the bug.

**2.5 Undo once more (free).**

✅ You should see: still no image, and your hand-typed words are gone. This is the version from 2.1.

**2.6 Bring the original back (free).** In the versions list, restore version 1 of the LinkedIn post.

✅ You should see: the original text, with the original image (`office-hands-keyboard.jpg`).

---

## Part 3: Quick check that nothing broke (code tidy-up)

Stay in the **"On-call week, March 2027"** chat.

**3.1 Change one part by chat (about $0.02).** Type: `Make the subject line of the email shorter`

✅ You should see:
- Only the email's subject changes.
- The reply lists the change and its cost, and ends with "Edit cost: $…".

**3.2 An unclear request (about $0.01).** Type: `Make it better`

✅ You should see: a question asking which piece you mean, with a button for each piece.

〜 May vary: it may ask what kind of change you want instead. That's fine too.

Click one of its buttons.

✅ You should see: that piece is edited.

〜 May vary: how it changes the wording.

**3.3 Remove and bring back (about $0.01).** Type: `Remove the second X post`

✅ You should see:
- It's removed.
- The note says it's hidden, not deleted, and has a button to bring it back.

Click that button.

✅ You should see: the X post comes back in its old place.

**3.4 Check again (about $0.01).** On the blog post, press Check again.

✅ You should see: a note saying "Checked … again: N warnings" (or "no problems"), with its cost.

**3.5 Undo and Restore (free).** On the email, press Undo. Then restore its newest version from the versions list.

✅ You should see: the subject goes back to the old one, then back to the short one.

**3.6 "Remember this?" (free).**
- On one piece, edit by hand and swap one word for another, for example "engineer" → "operator". Save.
- Do the same swap on a different piece.

✅ You should see: after the second save, the chat offers "You've made this change by hand more than once. Remember it?"

Click Remember it.

✅ You should see: a "Remembered: …" note in the chat.

Afterwards, delete that item on the Memory page, so it doesn't affect later campaigns.

---

## Part 4: Costs (free)

Open the **Costs** tab for both chats.

✅ You should see: each step you ran above listed with its cost. The total for this retest is about $0.35.

---

## If something doesn't match

Note:
- the step number
- what you saw
- a screenshot

and send them to me.
