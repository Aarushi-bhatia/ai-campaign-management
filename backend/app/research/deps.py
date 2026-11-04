from functools import lru_cache

from app.config import get_settings
from app.research.client import FirecrawlClient, WebResearch


@lru_cache
def get_web_research() -> WebResearch | None:
    """None when no Firecrawl key is set: planning then goes ahead without web research."""
    key = get_settings().firecrawl_api_key
    return FirecrawlClient(key) if key else None
