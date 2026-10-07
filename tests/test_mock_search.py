import json

from web_ingestion.config import FIXTURES_DIR, Settings
from web_ingestion.search import get_search_client


def test_mock_mode_selected_without_key():
    settings = Settings(tavily_api_key="")
    assert settings.mock_mode is True
    assert get_search_client(settings).provider == "mock"


def test_mock_search_returns_fixture_results():
    client = get_search_client(Settings(tavily_api_key=""))
    response = client.search("attention is all you need")
    assert response.mock is True
    assert len(response.results) == 3
    for item in response.results:
        assert item.fixture_path
        assert (FIXTURES_DIR / item.fixture_path).exists()


def test_mock_search_respects_max_results():
    client = get_search_client(Settings(tavily_api_key=""))
    response = client.search("x", max_results=1)
    assert len(response.results) == 1


def test_fixture_file_is_valid_json():
    data = json.loads((FIXTURES_DIR / "search_results.json").read_text(encoding="utf-8"))
    assert data["results"]
    assert all({"title", "url", "fixture_path"} <= set(r) for r in data["results"])
