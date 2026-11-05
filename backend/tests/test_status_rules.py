from app.brand.rules.status import DocView, LinkView, decide_statuses

NEW = DocView(1, "guidelines-2026.md", "current", "These guidelines are current.", "2026-02-10")
OLD = DocView(2, "guidelines-v3-final.md", "current", "Version 3.0 (FINAL)", "2024-09-01")
README = DocView(3, "README.md", "unknown", "", "2025-11-01")


def _status(docs, links, corrections=None):
    return decide_statuses(docs, links, corrections or {})


def test_a_document_that_says_it_replaces_another_marks_it_replaced():
    result = _status([NEW, OLD], [LinkView(1, 2, "replaces", "These replace the 2024 guidelines.")])

    assert result[2].status == "replaced"
    assert result[2].replaced_by == 1
    assert "guidelines-2026.md says it replaces this" in result[2].reason
    assert result[1].status == "current"


def test_replacing_beats_a_label_calling_the_old_one_current():
    links = [LinkView(1, 2, "replaces", "These replace the 2024 guidelines."), LinkView(3, 2, "current", "v3 is current.")]

    result = _status([NEW, OLD, README], links)

    assert result[2].status == "replaced"
    assert "README.md calls it current, but a document that replaces another beats a label" in result[2].reason


def test_out_of_date_statements_mark_a_document_replaced():
    result = _status([NEW, OLD], [LinkView(1, 2, "outdated", "If a deck says otherwise, the deck is out of date.")])

    assert result[2].status == "replaced"
    assert "says this is out of date" in result[2].reason


def test_when_two_documents_replace_each_other_the_newer_wins():
    links = [LinkView(1, 2, "replaces", "a"), LinkView(2, 1, "replaces", "b")]

    result = _status([NEW, OLD], links)

    assert result[1].status == "current"
    assert result[2].status == "replaced"


def test_when_two_undated_documents_replace_each_other_a_person_decides():
    first = DocView(1, "a.md", "unknown", "", "")
    second = DocView(2, "b.md", "unknown", "", "")
    links = [LinkView(1, 2, "replaces", "a"), LinkView(2, 1, "replaces", "b")]

    result = _status([first, second], links)

    assert result[1].status == result[2].status == "unclear"


def test_a_document_that_calls_itself_a_draft_is_a_draft():
    draft = DocView(4, "persona-DRAFT.md", "draft", "DRAFT, do not circulate", "")

    assert _status([draft], [])[4].status == "draft"


def test_a_file_in_an_archive_folder_is_archived():
    post = DocView(5, "archive/blog/post.md", "unknown", "", "2023-04-18", ("archive", "year 2023"))

    result = _status([post], [])

    assert result[5].status == "archived"
    assert "archive" in result[5].reason


def test_with_nothing_said_a_document_is_current():
    assert _status([README], [])[3].status == "current"


def test_a_correction_beats_everything():
    result = _status([NEW, OLD], [LinkView(1, 2, "replaces", "x")], corrections={2: "current"})

    assert result[2].status == "current"
    assert result[2].reason == "You set this on the Brand page."


def test_links_from_unknown_documents_are_ignored():
    assert _status([OLD], [LinkView(99, 2, "replaces", "x")])[2].status == "current"
