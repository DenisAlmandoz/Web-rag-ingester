import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_DIR = PROJECT_ROOT / "fixtures"
DATA_DIR = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    """Pipeline configuration. Reads .env at the project root if present."""

    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    tavily_api_key: str = ""
    tavily_max_results: int = 5
    tavily_search_depth: str = "basic"

    default_parser: str = "baseline"
    fetch_timeout: float = 20.0
    max_fetch_bytes: int = 5_000_000
    user_agent: str = "web-search-ingestion/0.1 (RAG research pipeline)"

    chunk_size: int = 1200
    chunk_overlap: int = 200

    output_dir: Path = DATA_DIR

    # Databricks (used by the vector-index job and both jobs' writes/syncs)
    databricks_host: str = ""
    databricks_client_id: str = ""
    databricks_client_secret: str = ""
    databricks_warehouse_id: str = ""
    databricks_catalog: str = "main"
    databricks_schema: str = "web_ingest"
    databricks_table: str = "web_chunks"
    databricks_documents_table: str = "web_documents"
    databricks_endpoint_name: str = "vector-search-web-endpoint"
    databricks_index_name: str = "web_chunks_index"
    databricks_embedding_model: str = "databricks-gte-large-en"

    @property
    def mock_mode(self) -> bool:
        """No API key => deterministic offline mode using bundled fixtures."""
        return not self.tavily_api_key.strip()

    @property
    def databricks_ready(self) -> bool:
        """Table writes need a workspace host + a SQL warehouse."""
        return bool(self.databricks_host and self.databricks_warehouse_id)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        # Support plain TAVILY_API_KEY=... shell exports too
        if os.getenv("TAVILY_API_KEY") and not (PROJECT_ROOT / ".env").exists():
            _settings = Settings(tavily_api_key=os.environ["TAVILY_API_KEY"])
        else:
            _settings = Settings()
    return _settings


def reset_settings() -> None:
    """Drop the cached settings (used by tests)."""
    global _settings
    _settings = None
