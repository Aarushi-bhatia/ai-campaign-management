from app.brand.rules.conflicts import Candidate, pick_winner

LEGAL = Candidate(1, "legal/certifications.md", "current", "2026-10-02")
SALES = Candidate(2, "sales/deck-notes.md", "current", "2026-09-30")
OLD = Candidate(3, "guidelines-v3.md", "replaced", "2024-09-01")
NEW = Candidate(4, "guidelines-2026.md", "current", "2026-02-10")
DRAFT = Candidate(5, "persona-DRAFT.md", "draft", "2026-06-01")
ARCHIVED = Candidate(6, "archive/old-post.md", "archived", "")


def _pick(candidates, owners=(), replaces=(), outranked=(), outranking=(), topic="certifications", side_of=None):
    return pick_winner(
        list(candidates), list(owners), topic, set(replaces), set(outranked), set(outranking), side_of
    )


def test_a_replacing_document_wins():
    verdict = _pick([OLD, NEW], replaces=[(4, 3)])

    assert (verdict.winner_file_id, verdict.rule) == (4, "replaces")
    assert verdict.reason == "guidelines-2026.md replaces guidelines-v3.md."


def test_the_document_in_charge_of_the_topic_wins():
    verdict = _pick([LEGAL, SALES], owners=[1])

    assert (verdict.winner_file_id, verdict.rule) == (1, "owner")
    assert verdict.reason == "legal/certifications.md is in charge of certifications; sales/deck-notes.md is not."


def test_being_in_charge_beats_being_newer():
    older_owner = Candidate(1, "legal.md", "current", "2025-01-01")
    newer_note = Candidate(2, "notes.md", "current", "2026-01-01")

    assert _pick([older_owner, newer_note], owners=[1]).winner_file_id == 1


def test_a_document_another_ranks_higher_counts_as_in_charge():
    assert _pick([LEGAL, SALES], outranking=[2]).winner_file_id == 2


def test_a_document_ranked_lower_loses():
    assert _pick([LEGAL, SALES], owners=[1, 2], outranked=[2]).winner_file_id == 1


def test_approved_beats_draft():
    verdict = _pick([DRAFT, SALES])

    assert (verdict.winner_file_id, verdict.rule) == (2, "approved")


def test_newer_beats_older():
    verdict = _pick([LEGAL, SALES])

    assert (verdict.winner_file_id, verdict.rule) == (1, "newer")
    assert "(2026-10-02) is newer than sales/deck-notes.md (2026-09-30)" in verdict.reason


def test_live_beats_archived_when_dates_are_missing():
    verdict = _pick([ARCHIVED, SALES])

    assert (verdict.winner_file_id, verdict.rule) == (2, "live")


def test_rules_narrow_the_field_in_turn():
    # Two owners tie on "owner"; the draft one then loses on "approved".
    draft_owner = Candidate(5, "persona-DRAFT.md", "draft", "")
    verdict = _pick([LEGAL, SALES, draft_owner], owners=[1, 5])

    assert (verdict.winner_file_id, verdict.rule) == (1, "approved")


def test_a_tie_is_left_for_a_person():
    first = Candidate(1, "a.md", "current", "")
    second = Candidate(2, "b.md", "current", "")

    verdict = _pick([first, second])

    assert verdict.winner_file_id is None
    assert verdict.rule == "needs_human"
    assert "a.md, b.md" in verdict.reason


def test_a_replaced_document_loses_even_when_its_replacement_is_not_in_the_conflict():
    replaced_owner = Candidate(1, "pricing-2025.md", "replaced", "2025-01-01")
    note = Candidate(2, "slack-export.md", "current", "2026-10-16", internal=True)

    verdict = _pick([replaced_owner, note], owners=[1])

    assert (verdict.winner_file_id, verdict.rule) == (2, "replaces")
    assert verdict.reason == "pricing-2025.md has been replaced; slack-export.md has not."



def test_with_no_document_in_charge_internal_notes_lose():
    note = Candidate(1, "battlecards-internal.md", "current", "", internal=True)
    tiers = Candidate(2, "pricing-tiers-2026.md", "current", "")

    verdict = _pick([note, tiers])

    assert (verdict.winner_file_id, verdict.rule) == (2, "owner")
    assert verdict.reason == "battlecards-internal.md is internal, so not in charge of what is said in public."


def test_an_internal_document_named_in_charge_still_loses_to_a_public_one():
    note = Candidate(1, "battlecards-internal.md", "current", "", internal=True)
    tiers = Candidate(2, "pricing-tiers-2026.md", "current", "")

    voice = Candidate(3, "voice-guide.md", "current", "")

    verdict = _pick([note, tiers, voice], owners=[1, 2])

    assert (verdict.winner_file_id, verdict.rule) == (2, "owner")
    assert verdict.reason == (
        "pricing-tiers-2026.md is in charge of certifications; voice-guide.md is not; "
        "battlecards-internal.md is internal, so not in charge of what is said in public."
    )


def test_documents_that_agree_do_not_compete():
    old = Candidate(1, "guidelines-v3.md", "replaced", "2024-09-01")
    guidelines = Candidate(2, "guidelines-2026.md", "current", "2026-09-01")
    claims = Candidate(3, "approved-claims.md", "current", "2026-09-28")
    naming = Candidate(4, "capitalization.md", "current", "")

    verdict = _pick([old, guidelines, claims, naming], owners=[2, 3, 4], side_of={1: 0, 2: 1, 3: 1, 4: 1})

    assert verdict.rule == "replaces"
    assert verdict.winner_file_id in (2, 3, 4)
    assert verdict.reason == "guidelines-v3.md has been replaced; guidelines-2026.md has not."


def test_an_internal_document_never_wins_as_in_charge():
    """When the only document named in charge was internal, the owner rule fell back to it, and it won."""
    notes = Candidate(7, "internal/notes.md", "current", "2026-05-01", internal=True)
    guide = Candidate(8, "pricing-guide.md", "current", "2026-01-01")

    verdict = _pick([notes, guide], owners=[7], topic="pricing")

    assert (verdict.winner_file_id, verdict.rule) == (8, "owner")
    assert "internal/notes.md is internal, so not in charge of what is said in public" in verdict.reason
    assert "is in charge of pricing" not in verdict.reason
