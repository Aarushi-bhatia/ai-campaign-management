# Decisions

## 1. System overview

The application helps marketers turn a campaign brief into content for different channels, using the selected brand's documents, rules and saved preferences.

A campaign follows fixed stages: **brief → questions (if any) → plan → approval → writing → done**. The agent asks for missing information, prepares a plan and waits for the marketer's approval before generating any content.

The application uses AI to understand documents and generate content. Application code handles decisions that need predictable results, such as resolving document conflicts, checking rules and controlling campaign stages.

Other important choices:

- The brand's documents are processed and stored when they are added or updated. They are not sent in full with every request.
- The agent retrieves relevant information through tools instead of receiving the entire brand folder.
- Three model sizes are used for different tasks, so simpler work does not always require the most expensive model.
- PostgreSQL with pgvector stores both application data and document embeddings. A separate vector database was not needed.
- Brand knowledge and conversation memory are stored separately because they have different sources and levels of reliability.

## 2. Brand layer: how it works and why

The brand layer gives the agent access to a company's existing guidelines, product facts, approved claims and channel rules. This matters because a brand folder can contain old documents, conflicting information and internal notes that should never appear in public content.

**Reading documents**

When documents are added, the application:

- Splits them at headings, with further splitting for sections that are too long. Each chunk keeps its heading path and contains 60–800 tokens, without overlap.
- Converts each chunk into an embedding using `text-embedding-3-small`, so the application can search by meaning.
- Extracts facts in a fixed JSON format. Every fact must include a quote from its source document. Facts with missing or unverifiable quotes are rejected.
- Stores document details such as type, status, date, owner and which document it replaces. Claims about a document's owner or replacement need a quote of more than one word.
- Uses SHA-256 hashes to detect changed files, so unchanged documents do not need to be processed again.

A short summary of the brand, built from facts that have won conflict resolution, is included in every prompt. The rest of the information is retrieved only when needed.

**Finding information**

The agent has separate tools for different kinds of information:

- Document search returns the six closest matching chunks, each cut to 1,500 characters.
- Fact lookup returns up to 30 facts using keyword matching, with a boost for an exact product or name match.
- Channel rules are retrieved separately, with up to 60 rules available.
- The agent can read one document at a time, up to 12,000 characters.

**Keeping corrections**

A marketer can correct information on the Brand page. These manual corrections take priority over extracted facts and remain in place when documents are updated. Internal documents can also be marked "background only, never quote".

**Why this design?**

I wanted the agent to use information that can be traced back to its source, without sending the entire brand folder to the model every time. Separating extraction from conflict resolution also means that the model can interpret a document, while application code applies the same rules consistently.

## 3. Memory: how it works and why

Brand knowledge comes from company documents. Memory comes from what the marketer tells the agent. I keep them separate because a casual comment in a conversation should not override an approved brand claim.

There are two types of memory:

- **Core memory:** lasting preferences and instructions, such as words the marketer wants to avoid. It is kept small (up to 50 items) and goes into every prompt, so every call follows it and no memory search is needed.
- **Campaign history:** short records of past campaigns. Only planning reads the recent ones, so new plans don't repeat old ones, and history can grow without making every call longer.

The agent learns only from what the marketer says in the chat. It never learns from the brief or from answers to its questions, because those apply to one campaign. It also skips one-off requests such as "for this launch only"; this depends on the model's judgement. Repeated hand edits are a signal too: when the same wording change is made twice, the app asks whether to remember it rather than saving it silently.

Memory never quietly overrules anything. A new instruction that contradicts an old one is kept beside it until the marketer chooses, and the current brief always takes priority over memory.

## 4. Handling conflicting documents

Documents often disagree. For example, a sales deck might contain a customer claim that Legal has since rejected. Simply choosing the newest document would not be reliable because dates can be missing or a newer document can still be wrong.

The application uses these rules in order:

1. **Replacement:** A document that explicitly replaces another takes priority.
2. **Owner:** The document responsible for that topic wins. For example, Legal's claims document takes priority over a sales deck for legal claims.
3. **Approval:** Approved documents take priority over drafts.
4. **Date:** Newer documents take priority over older ones.
5. **Status:** Live documents take priority over archived ones.
6. **Human decision:** If no rule resolves the conflict, the marketer decides.

The application stops when one rule leaves a clear winner. Documents that agree are grouped together rather than treated as competing claims. Internal notes never decide what can appear in public-facing content.

One deliberate trade-off is that date is checked before status. A newer archived document can therefore beat an older live document. I kept this order because a document being marked live does not automatically make its information more accurate.

If a conflict remains unresolved, neither side is given to the agent as an approved fact. It must ask the marketer. The answer is saved as a brand decision, not as conversation memory.

The same approach applies when a brief contradicts a brand rule. The agent asks for confirmation before accepting the change. If the brief contains a fact that conflicts with the brand documents, the agent quotes the relevant brand sentence when asking about it.

## 5. What I deliberately left out

I left out features that added complexity without being necessary for the current scope:

- **Live text generation:** Content is generated as a completed result rather than streamed word by word. Streaming was not essential for the workflow.
- **Simultaneous edits:** Not much engineering here, since the app is for one marketer. An out-of-date save is simply refused, so it can't overwrite a newer change (optimistic locking).
- **Repeated automatic fixes:** The application tries one correction and then shows remaining warnings. Repeated fixes sometimes removed valid information.

These choices kept the focus on getting the campaign workflow and brand handling right before expanding the feature set.

## 6. Where an AI tool led me wrong

AI tools helped with implementation and debugging, but their suggestions were not always correct for the application's requirements. I treated generated code and explanations as proposals, not as proof that something worked.

**Editing by hand only after writing.** For hand edits in the right panel, the AI tool recommended allowing them only once the pieces were written. While the plan was still open, the plan cards would stay read-only, and any change would go through the chat.

That had it backwards. The plan is the cheapest place to fix something: a card is a few lines, and a mistake there gets copied into every piece written from it. Sending each small fix through the chat costs an AI call and a wait, and the AI has to work out what I meant, while typing the change is exact and free.

So plan cards are editable in the right panel too: change a field, delete a card or drag it to a new place, for $0. The chat still works for bigger changes, such as "drop the second LinkedIn post".

## 7. What I would do with two more weeks

My priorities would be:

1. **Improve retrieval:** Prevent search from returning claims that have already lost a conflict.
2. **Evals for the agent:** Tests use a fake AI, so the model's judgement is only checked by hand. A fixed set of briefs with known answers would score every prompt or model change automatically.
3. **Brand onboarding as background jobs:** Reading a brand runs in a thread inside the API. A job queue with its own worker would keep it away from the chat and retry failed documents.
4. **Reduce AI costs:** Fact extraction accounts for a large share of brand-reading costs, so I would investigate how to reduce those calls.
5. **Add frontend tests:** Cover important user interactions and workflows that backend tests cannot catch.
6. **Support more document types:** Add PDF and slide ingestion so brands are not limited to the formats currently supported.
7. **Limit memory by size, not count:** Core memory is capped at 50 items, but 50 short rules and 50 long ones cost very different amounts in every prompt. A token budget would measure what actually matters.

## 8. Other engineering decisions

**Cost**

- **Prompt caching:** each prompt has a fixed part and a task part, with hand-placed cache points, so the repeated brand summary and rules are cheap.
- **Cost tracking:** every AI call is logged with its tokens and cost. You can see the cost of each step, of each edit, and of the "View prompt" button.

**Output quality**

- **Rule checks before the AI check:** free code checks run first (banned words, old names, length, hashtags), then an AI judge checks claims and tone (LLM-as-judge).
- **Web research:** findings show their link and date, can be removed, and the same search never runs twice in one campaign.

**Agent behaviour**

- **Question cards:** one question at a time, at least two real options, the safe option first, and a link to the conflict when one applies.
- **Edit routing:** a chat message is sorted into add, edit or ask (intent routing). Only the piece and part you mean change, and when it's unclear the app lists the pieces you could mean.

**Data safety**

- **Versions:** every change to a piece is saved as a version (versioning), so Undo, Compare and Restore work. Removing a piece only hides it (soft delete).
- **Memory safety:**
  - Undo never reverses a change made after it.
  - Pinned items are never dropped.
  - When memory is full of pinned items, the app refuses to add more and says so.

**Code quality**

- **Linting:** ruff, with a complexity limit of 10 per function.
