from ..config import Settings
from .base import SearchClient
from .mock import MockTavilyClient
from .tavily import TavilyClient


def get_search_client(settings: Settings) -> SearchClient:
    """Live Tavily when a key is configured, fixture-backed mock otherwise."""
    if settings.mock_mode:
        return MockTavilyClient(settings)
    return TavilyClient(settings)
