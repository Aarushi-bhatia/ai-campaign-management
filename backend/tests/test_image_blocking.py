from app.brand.images.channel_rules import DEFAULT_CHANNEL
from app.brand.images.picking import AssetSpec, ImageView, blocked_reason, library_text

FINE = {"usable": True, "retired": False, "expired": False, "no_crop": False, "allowed_channels": [],
        "blocked_channels": [], "rules": [], "reason": ""}


def _image(path="hero.jpg", image_type="photography", width=1536, height=1024, transparent=False, override=None,
           **notes):
    return ImageView(1, path, "", "", image_type, (), width, height, transparent, {**FINE, **notes}, override)


def _spec(channel="email", slot="main", exclude=()):
    return AssetSpec(channel=channel, asset_type="post", message="launch", slot=slot, exclude_paths=frozenset(exclude))


def _rules(**email):
    return {"email": {**DEFAULT_CHANNEL, **email}, "blog": dict(DEFAULT_CHANNEL)}


def test_a_cleared_image_is_not_blocked():
    assert blocked_reason(_image(), _spec(), _rules()) is None


def test_the_restriction_reason_is_given_for_an_unusable_image():
    image = _image(usable=False, reason="The person in it has left the company.")

    assert blocked_reason(image, _spec(), _rules()) == "The person in it has left the company."


def test_retired_and_expired_images_are_blocked():
    assert blocked_reason(_image(retired=True), _spec(), _rules()) == "It is retired."
    assert blocked_reason(_image(expired=True), _spec(), _rules()) == "It has expired."


def test_an_image_limited_to_other_channels_is_blocked():
    assert blocked_reason(_image(allowed_channels=["events"]), _spec(), _rules()) == "Only for events."


def test_an_image_blocked_for_the_channel_is_blocked():
    assert blocked_reason(_image(blocked_channels=["email"]), _spec(), _rules()) == "Not for email."
    assert blocked_reason(_image(blocked_channels=["email"]), _spec("blog"), _rules()) is None


def test_see_through_images_are_blocked_where_the_channel_says_so():
    spot = _image("spot.png", "illustration", 800, 800, transparent=True)

    assert blocked_reason(spot, _spec(), _rules(block_transparent=True)) == "See-through images aren't used in email."
    assert blocked_reason(spot, _spec("blog"), _rules(block_transparent=True)) is None


def test_the_wrong_shape_is_blocked():
    portrait = _image(width=800, height=1200)

    assert blocked_reason(portrait, _spec(), _rules(orientation="landscape")) == (
        "email needs a landscape image; this one is portrait."
    )


def test_only_allowed_types_pass_and_blocked_types_never_do():
    illustration = _image(image_type="illustration")

    assert "uses only product_screenshot" in blocked_reason(illustration, _spec(), _rules(allowed_types=["product_screenshot"]))
    assert blocked_reason(illustration, _spec(), _rules(blocked_types=["illustration"])) == (
        "illustration images aren't used in email."
    )


def test_too_narrow_images_are_blocked():
    assert blocked_reason(_image(width=400), _spec(), _rules(min_width=600)) == "Narrower than the 600px email needs."


def test_channel_rules_apply_only_to_the_main_image():
    spot = _image("spot.png", transparent=True)

    assert blocked_reason(spot, _spec(slot="inline"), _rules(block_transparent=True)) is None


def test_the_users_correction_wins_both_ways():
    retired = _image(retired=True, override="yes")
    cleared = _image(override="no")

    assert blocked_reason(retired, _spec(), _rules()) is None
    assert blocked_reason(cleared, _spec(), _rules()) == "You marked it not usable."


def test_a_campaign_can_leave_images_out():
    assert blocked_reason(_image(), _spec(exclude=["hero.jpg"]), _rules()) == "Left out by the campaign."


def test_an_image_type_the_brief_rules_out_is_blocked_even_when_marked_usable():
    """The brief's image rules used to be only a hint to the ranking model (#16)."""
    spec = AssetSpec(channel="email", asset_type="email", message="launch", excluded_types=frozenset({"product_screenshot"}))

    assert blocked_reason(_image(image_type="product_screenshot", override="yes"), spec, _rules()) == (
        "The campaign's brief rules out product screenshot images.")
    assert blocked_reason(_image(image_type="photography"), spec, _rules()) is None


def test_an_image_whose_restrictions_havent_been_read_is_blocked():
    unread = ImageView(1, "new.jpg", "", "", "photography", (), 100, 100, False, None)

    assert blocked_reason(unread, _spec(), _rules()) == "Its rights and restrictions haven't been checked yet (or couldn't be): use Read again."


# Group 5 of the design review (#18)

def test_usable_yes_overrules_the_verdict_but_not_the_images_own_channel_limits():
    retired = _image(override="yes", retired=True)
    email_only = _image(override="yes", allowed_channels=["email"])
    not_for_x = _image(override="yes", blocked_channels=["x"])

    assert blocked_reason(retired, _spec(), _rules()) is None  # the marketer's "yes" stands over the notes' verdict
    assert blocked_reason(email_only, _spec("linkedin"), _rules()) == "Only for email."  # was usable everywhere
    assert blocked_reason(not_for_x, _spec("x"), _rules()) == "Not for x."
    assert blocked_reason(email_only, _spec("email"), _rules()) is None


def test_an_image_that_must_not_be_cropped_says_so_to_the_ranking():
    """no_crop was read from the notes but never used anywhere."""
    text = library_text([_image(no_crop=True), _image(path="other.jpg")])

    assert text.count("must not be cropped") == 1
