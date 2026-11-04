# 09: Memory

**What to build:** The agent remembers what's worth keeping between campaigns and lets the user see and change it. Core memory holds general corrections, preferences and conflict decisions. It's kept small and is always loaded. Campaign history holds a short record of each past campaign and is looked up only while planning. New memories save automatically with an Undo note. The Memory page shows both, with the chat each item came from. See docs/SPEC.md, "Memory".

**Blocked by:** 05, 08

**Status:** done. Brand page corrections are kept as brand decisions (they already persist and win), not copied into core memory; conflict answers given in chat are added to core memory.

- [x] At the end of a chat and when the user corrects the agent, a small model suggests memory items
- [x] Kept: general corrections, preferences (asset mix, tone, length), conflict decisions and Brand page corrections
- [x] Not kept: campaign-only details, one-off edits, anything already in the brand folder
- [x] New items save automatically, with a "Remembered: …" note and Undo in the chat
- [x] Core memory is capped (about 50 items) and near-duplicates are merged
- [x] Core memory is part of the fixed prompt part for every call
- [x] Each finished campaign gets a short record: name, goal, audience, assets, main angle, images used, dates
- [x] Campaign history is looked up only during planning
- [x] When the user keeps making the same hand fix, the agent offers "Remember this?"
- [x] The Memory page has two tabs (core memory, campaign history); each item shows its source chat; items can be edited, deleted or pinned
- [x] A new chat shows which memories it used
- [x] Memory is kept per brand
- [x] API tests: an item is created and undone; an item carries into a new chat's fixed prompt part; campaign history is only used in planning
