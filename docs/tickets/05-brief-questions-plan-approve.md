# 05: Brief → questions → plan → approve

**What to build:** A user starts a new campaign chat and pastes a brief. The agent looks up only the brand facts it needs. If something important is unclear, missing or wrong, it asks, one question at a time, as a card with clickable options and a text box. If the brief states something the brand's rules say is false, it pushes back with proof and suggests a fix. It then proposes a plan as cards on the right, with an Assumptions section. The user changes the plan by chat or directly on the cards, then presses "Approve plan". See docs/SPEC.md, "Campaign agent".

**Blocked by:** 03

**Status:** done. Tried on all three sample briefs with the real models. Drag-to-reorder and field edits on the plan cards are tested through the API only.

- [x] One campaign per chat; "New campaign" in the sidebar starts one; briefs are only pasted
- [x] Brand lookup tools exist: search the brand, get a channel's rules, get approved claims for a topic, read a section, get conflicts for a topic
- [x] Lookup tools return only current, allowed material; not-safe-to-quote material is labelled as background
- [x] Every request uses the fixed prompt order, with the brand summary in the fixed part
- [x] The agent moves through fixed stages and can't skip one; writing is impossible before approval
- [x] Questions are asked only when the user's message is unclear, something important is missing, the brief clashes with brand rules, or a conflict can't be settled; never for what the folder or brief already answers
- [x] Questions come one at a time as cards with 2–4 options (suggested first) and a text box; at most 3–5 per round; none for a clear brief
- [x] Wrong facts in a brief produce push-back that cites the source and suggests safe wording
- [x] Brief overrides are saved as scoped rules that apply only to the named points and only to this campaign
- [x] The user's answer to a conflict question is saved as a brand decision
- [x] The chat shows a one-line note each time a document is chosen over another for this campaign
- [x] The agent plans only email, LinkedIn, X, blog and landing page, and only for social networks the brand uses
- [x] Plan cards show type, channel, audience, main message, date, image idea and research (empty for now)
- [x] The plan shows an Assumptions section
- [x] The plan can be changed by chat, and by delete, drag to reorder and typing into fields on the cards
- [x] "Approve plan" locks the plan for writing
- [x] API tests: a clear brief goes straight to a plan; a vague brief produces question cards; a false claim produces push-back with the source; writing before approval is refused
