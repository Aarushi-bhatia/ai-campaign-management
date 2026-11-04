# 02: Upload a brand and see document cards

**What to build:** A user clicks "Add brand" in the sidebar and uploads a brand folder, or the app reads the folder named in settings on first start. Progress is shown while it reads. When reading finishes, the Brand page opens automatically and its Documents tab shows, for every document: its type, its claimed status, its date, its owner and role, whether it's safe to quote in public, and the exact sentence that proves each of these. Re-reading skips files that haven't changed. See docs/SPEC.md, "Brand reader", steps 1 and 2.

**Blocked by:** 01

**Status:** done. The folder picker screen is built, but it was only exercised through the same upload API, because the browser file chooser can't be automated

- [x] Upload a folder in the app, or preload one from the settings file
- [x] Any folder of text documents and images works; no fixed layout is assumed
- [x] Reading progress is shown live
- [x] Step 1 (no AI) records file name, folder, length, headings, any labels at the top of the file, and file-name hints
- [x] Step 2 (small model, fixed output shape) writes a card per document: type, claimed status, date, owner and role, topics it rules on, safe to quote, documents it says it replaces, "this beats that" statements, products/channels/customers mentioned
- [x] Every card field carries its proving sentence, or is "unknown"
- [x] Documents are split into sections by headings and stored with search vectors
- [x] Results are saved by file content and prompt version; unchanged files are not read again
- [x] The Brand page opens automatically after first read and is reachable from the sidebar
- [x] The Documents tab lists every card with its proving sentences
- [x] The cost of reading the brand is logged separately from campaigns
- [x] Everything is stored per brand
- [x] API test: upload a small made-up messy brand and check the cards (with the fake AI)
