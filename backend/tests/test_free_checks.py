"""The free checks, tested directly with many edge cases."""

from app.campaign.checking.free import CheckRules, free_checks


def _post(text: str, hashtags: list[str] | None = None, sources: list[str] | None = None) -> dict:
    return {"author": "Team", "text": text, "hashtags": hashtags or [], "sources": sources or []}


def _checks(content: dict, kind: str = "linkedin_post", **rules) -> list[tuple[str, str]]:
    return [(p.check, p.quote) for p in free_checks(kind, content, CheckRules(**rules))]


BANNED = [{"term": "best-in-class", "instead": ""}, {"term": "leverage", "instead": "use"}]


def test_a_banned_word_is_found_whatever_its_case():
    assert _checks(_post("We LEVERAGE pods."), banned=BANNED) == [("banned word", "LEVERAGE")]


def test_spaces_and_hyphens_match_each_other():
    assert _checks(_post("A best in class agent."), banned=BANNED) == [("banned word", "best in class")]


def test_a_banned_word_inside_another_word_is_fine():
    assert _checks(_post("Leveraged buyouts aside, nothing."), banned=BANNED) == []


def test_banned_words_are_found_in_nested_sections():
    email = {"subject": "Hi", "sections": [{"heading": "Why", "body": "It is best-in-class."}], "button_link": "#"}
    assert _checks(email, "email", banned=BANNED) == [("banned word", "best-in-class")]


def test_a_banned_word_is_reported_once_per_asset():
    assert len(_checks(_post("leverage, leverage, leverage"), banned=BANNED)) == 1


def test_a_banned_line_is_found_without_its_full_stop():
    lines = [{"term": "Sleep through the night.", "instead": ""}]
    for text in ("Sleep through the night", "Sleep through the night.", "“Sleep through the night!”"):
        assert _checks(_post(f"Wickhold. {text} Book a demo."), banned=lines) == [("banned word", "Sleep through the night")]


def test_curly_quotes_and_dashes_dont_hide_a_word():
    assert _checks(_post("It’s best–in–class."), banned=BANNED) == [("banned word", "best-in-class")]


OLD = [{"old": "Tallowatch", "new": "Evenburn"}, {"old": "Acme", "new": "Acme Cloud"}]


def test_a_retired_name_is_found():
    assert _checks(_post("Try Tallowatch today."), old_names=OLD) == [("old name", "Tallowatch")]


def test_an_old_name_that_is_part_of_the_new_name_is_fine():
    assert _checks(_post("Acme Cloud is here."), old_names=OLD) == []
    assert _checks(_post("Acme is here."), old_names=OLD) == [("old name", "Acme")]


def test_formerly_lines_are_allowed():
    assert _checks(_post("Evenburn, formerly Tallowatch, is here."), old_names=OLD) == []


def test_an_x_post_over_280_characters_fails_with_its_hashtags_counted():
    text = "a" * 270
    assert _checks(_post(text), "x_post") == []
    assert [c for c, _ in _checks(_post(text, hashtags=["kubernetes"]), "x_post")] == ["length"]


def test_a_brand_limit_tighter_than_the_platform_wins():
    limits = [{"channel": "x", "field": "text", "max": 200, "unit": "characters"}]
    assert [c for c, _ in _checks(_post("a" * 250), "x_post", limits=limits)] == ["length"]


def test_a_word_limit_counts_words():
    limits = [{"channel": "email", "field": "subject", "max": 3, "unit": "words"}]
    email = {"subject": "One two three four", "sections": [{"heading": "", "body": "Hi."}], "button_link": "#"}
    assert [c for c, _ in _checks(email, "email", limits=limits)] == ["length"]
    assert _checks({**email, "subject": "One two three"}, "email", limits=limits) == []


def test_limits_for_another_channel_dont_apply():
    limits = [{"channel": "email", "field": "text", "max": 5, "unit": "characters"}]
    assert _checks(_post("Longer than five."), limits=limits) == []


def test_a_landing_page_headline_is_its_first_heading():
    limits = [{"channel": "landing_page", "field": "headline", "max": 10, "unit": "characters"}]
    page = {"sections": [{"kind": "hero", "heading": "A very long headline", "body": "", "items": [], "button_text": ""}]}
    assert [c for c, _ in _checks(page, "landing_page", limits=limits)] == ["length"]


APPROVED = frozenset({"https://example.org/report"})


def test_an_approved_source_passes_with_or_without_www_and_slash():
    assert _checks(_post("See https://www.example.org/report/.", sources=["https://example.org/report"]),
                   approved_urls=APPROVED) == []


def test_a_link_in_the_text_that_wasnt_approved_fails():
    assert _checks(_post("See https://other.example/x for more."), approved_urls=APPROVED) == [
        ("citation", "https://other.example/x")]


def test_a_listed_source_that_wasnt_approved_fails():
    assert [c for c, _ in _checks(_post("Text.", sources=["https://invented.example"]))] == ["citation"]


def test_the_assets_own_button_link_is_not_a_citation():
    email = {"subject": "Hi", "sections": [{"heading": "", "body": "Hi."}], "button_text": "Go",
             "button_link": "https://acme.example/start"}
    assert _checks(email, "email") == []


def test_a_blocked_image_is_a_problem():
    assert _checks(_post("Fine."), image_problem="It is retired.") == [("image", "")]


def test_clean_copy_passes_every_check():
    assert _checks(_post("Acme Cloud contains failures early."), banned=BANNED, old_names=OLD, approved_urls=APPROVED) == []


def test_a_banned_spelling_that_differs_only_in_capitals_is_matched_exactly():
    rules = [{"term": "LeashGate", "instead": "Leashgate"}]
    assert _checks(_post("Leashgate is here."), banned=rules) == []
    assert _checks(_post("LeashGate is here."), banned=rules) == [("banned word", "LeashGate")]


def test_a_link_the_brief_or_brand_gives_is_not_a_citation():
    known = frozenset({"https://acme.example/product"})
    assert _checks(_post("More at https://acme.example/product."), approved_urls=known) == []


# Edge cases in length limits

def test_a_word_limit_does_not_replace_the_platforms_character_limit():
    limits = [{"channel": "linkedin", "field": "text", "max": 1000, "unit": "words"}]
    post = {"author": "Acme", "text": "abcd " * 700, "hashtags": []}  # 700 words, 3,500 characters

    checks = [c for c, _ in _checks(post, limits=limits)]

    assert checks == ["length"]  # the 3,000-character cap still applies; the word limit used to replace it


def test_an_x_link_counts_as_23_characters():
    link = "https://wickhold.example/blog/leashgate-general-availability-launch-announcement"
    post = {"author": "Acme", "text": f"{'a' * 240} {link}", "hashtags": []}  # 321 raw, 264 as X counts it

    assert _checks(post, "x_post", approved_urls=frozenset({link})) == []  # was flagged as too long


def test_hashtags_are_flagged_only_past_the_number_the_channel_rules_allow():
    """The limit is the structured number from the writing rules. A wording regex used to fire on rules that allow
    hashtags, such as "Avoid hashtags mid-sentence; up to two at the end are fine"."""
    post = {"author": "Acme", "text": "Leashgate is here. #AIsecurity", "hashtags": ["Kubernetes", "#aisecurity"]}

    assert _checks(post, "x_post", hashtag_max=0) == [("hashtags", "#Kubernetes")]
    assert _checks(post, "x_post", hashtag_max=2) == []  # #AIsecurity is counted once
    assert _checks(post, "x_post", hashtag_max=1) == [("hashtags", "#Kubernetes")]
    assert _checks(post, "x_post") == []  # the rules give no number: left to the AI check
