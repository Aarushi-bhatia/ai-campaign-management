"""The only path to the web: search, with each result's page text. Tests swap it for a fake."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

FIRECRAWL_SEARCH = "https://api.firecrawl.dev/v2/search"
DATE_KEYS = ("publishedTime", "article:published_time", "datePublished", "date", "modifiedTime")


@dataclass(frozen=True)
class WebPage:
    url: str
    title: str
    text: str
    date: str
    """When the page says it was published, or "" when it doesn't say."""


class WebResearch(Protocol):
    def search(self, query: str, limit: int) -> list[WebPage]: ...


class ResearchFailed(Exception):
    pass


class FirecrawlClient:
    def __init__(self, api_key: str, timeout: float = 90) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def search(self, query: str, limit: int) -> list[WebPage]:
        try:
            response = httpx.post(
                FIRECRAWL_SEARCH,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"query": query[:500], "limit": limit,
                      "scrapeOptions": {"formats": [{"type": "markdown"}], "onlyMainContent": True}},
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as error:
            raise ResearchFailed(f"Web search failed: {error}") from error
        results = response.json().get("data", {}).get("web", [])
        return [
            WebPage(
                url=(item.get("metadata") or {}).get("url") or item["url"],
                title=item.get("title") or (item.get("metadata") or {}).get("title") or item["url"],
                text=item.get("markdown") or item.get("description") or "",
                date=_date(item.get("metadata") or {}),
            )
            for item in results
            if item.get("url")
        ]


def _date(metadata: dict) -> str:
    for key in DATE_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:10]
    return ""


class FakeWebResearch:
    """Returns scripted pages for a query, and remembers every query asked."""

    def __init__(self, pages: Callable[[str], list[WebPage]] | None = None) -> None:
        self._pages = pages or (lambda query: [])
        self.queries: list[str] = []

    def search(self, query: str, limit: int) -> list[WebPage]:
        self.queries.append(query)
        return self._pages(query)[:limit]
