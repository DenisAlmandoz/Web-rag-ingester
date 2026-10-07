from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SearchResult(BaseModel):
    """One result returned by the search provider (Tavily or mock)."""

    title: str
    url: str
    content: str = ""
    score: float = 0.0
    raw_content: str | None = None
    # Mock mode only: local fixture file that stands in for a live fetch
    fixture_path: str | None = None


class SearchResponse(BaseModel):
    query: str
    provider: str
    results: list[SearchResult] = Field(default_factory=list)
    response_time: float = 0.0
    mock: bool = False


class FetchedDocument(BaseModel):
    """Raw bytes fetched from the web (or a local fixture), plus context."""

    url: str
    content_type: str = "text/html"
    status_code: int = 200
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    content: bytes = b""
    title_hint: str = ""
    is_pdf: bool = False

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class ParsedDocument(BaseModel):
    """Parser output: flat text plus whatever structure the parser could keep."""

    url: str
    parser: str
    text: str = ""
    title: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    structure: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    parse_seconds: float = 0.0


class Chunk(BaseModel):
    id: str
    doc_id: str
    url: str
    title: str
    index: int
    text: str
    char_count: int
    approx_tokens: int = 0


class DocumentRecord(BaseModel):
    """End state of one URL through the pipeline: parsed + cleaned + chunked."""

    url: str
    title: str
    parser: str
    raw_chars: int
    cleaned_chars: int
    chunks: list[Chunk] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


ParserName = Literal["baseline", "trafilatura", "docling", "unstructured"]
