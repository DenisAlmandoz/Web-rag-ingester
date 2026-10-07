from typing import Protocol

from ..models import SearchResponse


class SearchClient(Protocol):
    """Anything that can turn a query into ranked results."""

    provider: str
    mock: bool

    def search(self, query: str, max_results: int | None = None) -> SearchResponse: ...
