# Model trial, 2026-11-03

We tried the three chosen models on tasks taken from the sample brand before settling which model does which job. Each task ran on all three models with the same prompt. Prices are OpenAI's Standard tier (see the AI pricing module).

**Status: settled** on 2026-11-04, after all three sample briefs ran end to end (see "Full campaign check" below and [COSTS.md](../COSTS.md)).

## Allocation

| Model | Jobs |
|---|---|
| `gpt-6-luna` (small) | Document cards, metadata, image descriptions, research notes, memory extraction, campaign records |
| `gpt-6.1-terra` (medium) | Brand fact extraction, names, conflicts, writing rules, image choice, claims and tone checks, fixes, edits |
| `gpt-6.1-sol` (large) | Brief review and questions, campaign planning, the brand summary, writing every asset |

## Results

| Task | Luna | Terra | Sol |
|---|---|---|---|
| **Document card:** start-here README, which wrongly calls the 2024 guidelines current | Correct. Found the date and owner, and recorded the "v3 is current" claim as a claim. $0.0004 | Correct, but missed the date and owner, which are in a prose line. $0.0042 | Correct. Found the date, missed the owner. $0.0066 |
| **Document card:** certifications sheet | Correct, with date and owner. $0.0005 | Missed the date. $0.0035 | Correct. $0.0064 |
| **Fact extraction:** certifications sheet and customer quote policy | 33 facts. Key facts right (FedRAMP not held, Vaskell not cleared). Coarser. $0.0016, 27s | 56 facts. Key facts right, with clean subjects such as "FedRAMP Moderate" and "Vaskell Health", which helps group conflicts. $0.017, 35s | 82 facts. Very granular, with less even subject names. $0.062, 46s |
| **Writing:** LinkedIn post whose request contains two forbidden items (a "FedRAMP Authorized" lead, and the uncleared Vaskell story) | Refused both, used the approved wording, said what it changed. Flattest copy. $0.0014 | Same, plus an unrequested image note. $0.012 | Same. Best-reading copy. $0.024 |
| **Claims check:** draft with 6 planted problems | Found all 6. $0.0014 | Found all 6. $0.013 | Found all 6, plus a second note on the Leashgate claim. $0.027 |

## What we learned

- **Luna is strong at document cards.** It was more thorough than Terra at picking dates and owners out of prose headers. Keep it on cards.
- **Terra is the right fit for fact extraction.** It is as accurate as Sol on the facts that matter, its subject names are more consistent, and it costs about a quarter as much. Sol's extra detail splits one rule into many rows, which makes conflicts harder to group, not easier.
- **Writing:** all three obeyed the brand rules on this test, and Sol read best. The test used only legal and channel documents, so it can't show voice and product accuracy. That needs the full campaign run.
- **Claims check:** Luna matched Terra on this test at a tenth of the cost. We keep Terra, as chosen, because real drafts hold subtler claims than planted ones. We'll revisit this with data from the full run.
- **Not yet tested:** image descriptions (vision, ticket 04), memory extraction (ticket 09), chat and planning (ticket 05).

## Caching facts confirmed on real calls

- Input tokens include cache-write tokens. Example: 1,485 in, of which 1,482 were written. Each input token is billed at one rate only.
- Prompts under 1,024 tokens are not cached or written.
- Repeating a 7,849-token prompt on Sol read 7,846 tokens from cache, and the cost fell from $0.024 to $0.004.
- On these models the cache point sits by default at the **end of the latest message**. So every call over 1,024 tokens writes its whole prompt, including the one-off task, at 1.25× the input price. For one-off calls such as document cards and fact extraction, that's about 25% extra on input for nothing. Ticket 10 should set an explicit cache point after the fixed part, or turn caching off for one-off calls.

## Full campaign check, 2026-11-04

All three sample briefs ran end to end with this allocation: questions answered with the agent's suggestion, plan approved, every asset written, checked and fixed, then one chat edit. Assets were read by eye for facts, names, claims and voice.

| Brief | What we looked for | What came out |
|---|---|---|
| 1. Leashgate launch | The 11 listed assets, on their dates and senders, with no early-access label, no price, fail-closed stated plainly, and only approved research cited | All of it. The blog cites the one approved web finding inline with its source. One question was asked, about a real clash between the brief's image and the brand's image rules. |
| 2. Awareness push | Questions only where the brief is vague, then a small plan on approved proof | Two questions (how success is measured, budget), then a landing page and three LinkedIn posts. It uses the approved customer figure, and placeholders where a link wasn't given. |
| 3. Regulated teams | Push-back on "FedRAMP Authorized" and the uncleared Vaskell story | Both refused, each with the document's sentence. Then it led with "Wickhold holds SOC 2 Type II." and the approved Ostler Grocers story. Where no customer quote was supplied, it left a marked placeholder instead of inventing one. |

**Planted problems.** A hand edit added "Wickhold is FedRAMP Authorized" and an invented Vaskell result to a finished post. The free checks flagged the banned phrase at $0. "Check again" (Terra, $0.006) caught the false claim, the uncleared customer story and a naming slip, each quoted from the copy.

**Decision: keep the allocation.**
- **Sol** stays on planning and writing. Its copy kept the brand's voice and every naming rule across 20 assets, and it is about 80% of a campaign's cost. Moving writing to Terra would roughly halve that, but writing is the output the marketer judges.
- **Terra** stays on checks, fixes and edits. Once the check saw the approved campaign, it stopped flagging brief-approved facts, and it still caught every planted problem. Luna matched it on planted problems in the first trial, but these checks now weigh the brief against older documents, which is subtler.
- **Luna** handles memory and research notes for well under a cent per campaign.

The largest cost lever left is not a model swap but the size of the lookups the agent asks for while reviewing a brief (see COSTS.md).
