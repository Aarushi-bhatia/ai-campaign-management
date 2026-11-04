# 03: Facts, conflicts, brand summary and corrections

**What to build:** After the document cards are written, the app pulls single facts out of rule and fact documents, learns old and new names, works out which documents replace which, and gives every document its final status. It finds facts that disagree, settles each conflict with the agreed order and a one-line reason, and marks truly unclear ones "needs a human". It then builds a short brand summary from the winning facts. On the Brand page the user can see all of this and correct it, and "Update brand" takes new or changed files without losing those corrections. See docs/SPEC.md, "Brand reader", steps 3 and 4.

**Blocked by:** 02

**Status:** done, except the optional brand dropdown. Beyond the plan: conflicts are judged by sides (documents that agree never compete), and internal documents are never in charge of public claims.

- [x] Single facts are pulled out (medium model) with subject, attribute, value, kind (must / must not / may / fact), scope and proving sentence. The section is not stored; the quote is checked against the whole document.
- [x] An old/new names table is built, and facts under an old name group with the new name
- [x] "Replaces" links between documents are resolved, and each document gets a final status that takes all documents into account
- [x] Conflicts are settled in this order: a document that says it replaces another; the owner of the topic; approved over draft; newer over older; live over archive; otherwise "needs a human"
- [x] Each decision stores winner, loser and a one-line reason
- [x] A 3–5 page brand summary is built from winning facts (voice, banned words, naming rules, standard company description, product one-liners)
- [x] Brand page tabs: Conflicts (winner, loser, reason) and Brand summary (exact text sent to the AI)
- [x] The user can change a document's status or type, flip a conflict winner, and edit the summary
- [x] Corrections are saved as brand decisions and always win over automatic results
- [x] "Update brand" uploads new or changed files; only those are read by AI; the comparison step re-runs over all saved cards
- [x] A new document can mark an older one as replaced without the older one being read again
- [x] Corrections survive an update
- [ ] (If time allows) A brand dropdown appears when more than one brand exists, and brands never mix
- [x] Direct tests of the conflict winner order with many edge cases
- [x] API tests: a new file replaces an old one; a correction survives an update
