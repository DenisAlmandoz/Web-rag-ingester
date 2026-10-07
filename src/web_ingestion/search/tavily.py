import time

import httpx

from ..config import Settings
from ..models import SearchResponse, SearchResult

API_BASE = "https://api.tavily.com"


class TavilyClient:
    """Live Tavily API client (https://docs.tavily.com).

    Endpoints used:
      - POST /search   : keyword/semantic web search, returns ranked URLs + snippets
      - POST /extract  : fetches full main content of given URLs server-side
    """

    provider = "tavily"
    mock = False

    def __init__(self, settings: Settings):
        if not settings.tavily_api_key:
            raise ValueError("TavilyClient requires tavily_api_key")
        self.settings = settings
        self.headers = {"Authorization": f"Bearer {settings.tavily_api_key}"}

    def search(self, query: str, max_results: int | None = None) -> SearchResponse:
        payload = {
            "query": query,
            "search_depth": self.settings.tavily_search_depth,
            "max_results": max_results or self.settings.tavily_max_results,
            "include_raw_content": True,
        }
        start = time.perf_counter()
        response = httpx.post(f"{API_BASE}/search", json=payload, headers=self.headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        results = [
            SearchResult(
                title=item.get("title", ""),
                url=item.get("url", ""),
                content=item.get("content", ""),
                score=float(item.get("score", 0.0)),
                raw_content=item.get("raw_content"),
            )
            for item in data.get("results", [])
        ]
        return SearchResponse(
            query=query,
            provider=self.provider,
            results=results,
            response_time=time.perf_counter() - start,
        )

    def extract(self, urls: list[str]) -> dict[str, str]:
        """Server-side full-content extraction for URLs (Tavily /extract)."""
        if not urls:
            return {}
        response = httpx.post(
            f"{API_BASE}/extract",
            json={"urls": urls, "include_images": False},
            headers=self.headers,
            timeout=60,
        )
        response.raise_for_status()
        out: dict[str, str] = {}
        for item in response.json().get("results", []):
            raw = item.get("raw_content")
            if raw and item.get("url"):
                out[item["url"]] = raw
        return out
