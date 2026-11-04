import pytest

from app.ai.pricing import cost_usd

MILLION = 1_000_000


def test_uncached_input_and_output():
    assert cost_usd("gpt-6.1-sol", MILLION, 0, 0, MILLION) == pytest.approx(2.00 + 10.00)


def test_each_input_token_is_billed_at_one_rate_only():
    # 1M input: 200k uncached, 500k read from cache, 300k written to cache.
    cost = cost_usd("gpt-6.1-terra", MILLION, 500_000, 300_000, 0)

    assert cost == pytest.approx(0.2 * 1.00 + 0.5 * 0.05 + 0.3 * 1.25)


def test_small_model_prices():
    assert cost_usd("gpt-6-luna", MILLION, MILLION, 0, MILLION) == pytest.approx(0.01 + 0.50)


def test_dated_snapshot_uses_its_model_price():
    assert cost_usd("gpt-6-luna-2026-03-17", MILLION, 0, 0, 0) == pytest.approx(0.10)


def test_unknown_model_has_no_price():
    assert cost_usd("some-new-model", 1000, 0, 0, 1000) is None

