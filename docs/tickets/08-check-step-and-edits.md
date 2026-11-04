# 08: Check step and edits

**What to build:** Every written asset is checked against the brand's rules, fixed once automatically if needed, and given a note of what was fixed and any warnings that remain. The user then edits assets in two ways: by chat ("shorten the second post"), which changes only that asset or field, or by typing straight into the asset, which costs nothing. Every change is a new version, with Undo and Compare. See docs/SPEC.md, "Asset checker" and "Asset versions".

**Blocked by:** 07

**Status:** done.

- [x] Free checks, with no AI: banned words, length limits from channel rules, product name rules, image rules, citations against approved research
- [x] AI check: claims against approved claims, and brand tone
- [x] After writing, both checks run; one automatic fix is tried; a note lists what was fixed; anything still failing shows as a warning
- [x] Cards show Waiting → Writing → Checking → Done
- [x] A chat edit finds the asset and field meant, asks if unclear, and rewrites only that
- [x] A wide edit ("everywhere") goes asset by asset and lists what changed
- [x] Chat-edited assets are checked again
- [x] Typing directly into an asset saves a version and runs only the free checks, at $0
- [x] "Check again" runs the full AI check on demand
- [x] Every write, fix, chat edit and hand edit is a new version; Undo and "Compare with previous" work
- [x] Each asset has a Copy button
- [x] The cost of each edit is shown
- [x] Direct tests of the free checks with many edge cases
- [x] API tests: a chat edit changes one asset only and saves a version; Undo restores it; a hand edit logs no AI cost
