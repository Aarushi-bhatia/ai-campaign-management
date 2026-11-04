"""Dollar prices per million tokens, Standard tier.

Source: https://developers.openai.com/api/docs/pricing (checked 2026-11-03).
Cache writes use the default 30-minute lifetime. Each input token is billed at exactly
one rate: uncached, cached (read) or cache write. The write charge is not an extra fee.
"""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Price:
    input: float
    cached_input: float
    cache_write: float
    output: float


PRICES: dict[str, Price] = {
    "gpt-6.1-sol": Price(input=2.00, cached_input=0.10, cache_write=2.50, output=10.00),
    "gpt-6.1-terra": Price(input=1.00, cached_input=0.05, cache_write=1.25, output=5.00),
    "gpt-6-luna": Price(input=0.10, cached_input=0.01, cache_write=0.125, output=0.50),
    # Listed on the model's own page, not the main pricing page.
    "text-embedding-3-small": Price(input=0.02, cached_input=0.02, cache_write=0.02, output=0.0),
}

_DATED_SNAPSHOT = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def price_for(model: str) -> Price | None:
    """Looks up a model, also when the API reports a dated snapshot such as `gpt-6-luna-2026-03-17`."""
    return PRICES.get(model) or PRICES.get(_DATED_SNAPSHOT.sub("", model))


def cost_usd(model: str, tokens_in: int, tokens_cached: int, tokens_cache_write: int, tokens_out: int) -> float | None:
    """Cost of one call, or None when the model has no known price.

    `tokens_in` is the total input, including the cached and cache-write tokens.
    """
    price = price_for(model)
    if price is None:
        return None
    uncached = tokens_in - tokens_cached - tokens_cache_write
    return (
        uncached * price.input
        + tokens_cached * price.cached_input
        + tokens_cache_write * price.cache_write
        + tokens_out * price.output
    ) / 1_000_000
