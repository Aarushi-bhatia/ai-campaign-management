# 04: Image library

**What to build:** When a brand is read, its images are read too. Free-text restriction notes are turned into clear fields, and images with no description get one written by a vision model. If there is no image info file at all, every image is described. The Brand page gets an Images tab showing which images are blocked and why. The app can pick images for an asset: it removes blocked images and those breaking channel rules first, then ranks the rest and writes alt text, or says "nothing fits" with a suggestion. See docs/SPEC.md, "Image library".

**Blocked by:** 02

**Status:** done. Beyond the plan: restrictions are also judged against the brand's own image rules (so unmarked stock clichés are blocked), images with a very short description are described by the vision model too, and the Images tab has a "try picking" box.

- [x] The optional image info file is read when present
- [x] Images with no description, or every image if there's no info file, get a description from a small vision model
- [x] Restriction notes become fields: usable, retired, allowed channels, blocked channels, no-crop, people rules, expired, reason
- [x] Channel image rules from the brand documents are applied (for example no see-through images in email headers)
- [x] Image picking takes asset type, channel, campaign image rules and the asset's message
- [x] Blocking always happens before ranking and uses only the fixed fields
- [x] Picking returns ranked usable images with alt text, or "nothing fits" with a suggestion
- [x] The Images tab shows every image, its status, and why it's blocked
- [x] The user can correct an image's fields on the Brand page, and the correction survives updates
- [x] Direct tests of image blocking with many edge cases
