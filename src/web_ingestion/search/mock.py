import json
import time

from ..config import FIXTURES_DIR, Settings
from ..models import SearchResponse, SearchResult


class MockTavilyClient:
    """Offline stand-in for Tavily: replays a recorded response from fixtures.

    Lets the whole pipeline (search -> fetch -> parse -> clean -> chunk) run
    without an API key or network access. Fixture URLs point at local HTML
    files in fixtures/pages/, which the fetcher resolves to disk.
    """

    provider = "mock"
    mock = True

    def __init__(self, settings: Settings | None = None):
        self.settings = settings
        self._fixture = FIXTURES_DIR / "search_results.json"

    def search(self, query: str, max_results: int | None = None) -> SearchResponse:
        start = time.perf_counter()
        data = json.loads(self._fixture.read_text(encoding="utf-8"))
        raw_results = data.get("results", [])
        if max_results:
            raw_results = raw_results[:max_results]

        results = [
            SearchResult(
                title=item["title"],
                url=item["url"],
                content=item.get("content", ""),
                score=float(item.get("score", 0.0)),
                raw_content=item.get("raw_content"),
                fixture_path=item.get("fixture_path"),
            )
            for item in raw_results
        ]
        return SearchResponse(
            query=query,
            provider=self.provider,
            results=results,
            response_time=time.perf_counter() - start,
            mock=True,
        )
