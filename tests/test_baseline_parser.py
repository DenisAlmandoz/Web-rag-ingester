from pathlib import Path

from web_ingestion.config import FIXTURES_DIR
from web_ingestion.models import FetchedDocument
from web_ingestion.parsers import get_parser


def _fixture_doc(name: str) -> FetchedDocument:
    path: Path = FIXTURES_DIR / "pages" / name
    content = path.read_bytes()
    return FetchedDocument(url=f"https://example.com/{name}", content=content, content_type="text/html")


def test_baseline_extracts_article_not_chrome():
    doc = _fixture_doc("attention-is-all-you-need.html")
    parser = get_parser("baseline")
    parsed = parser.parse(doc)
    assert "Self-attention in one paragraph" in parsed.text
    assert "tracking script that must never appear" not in parsed.text
    assert "cookie" not in parsed.text.lower()
    assert "Copyright" not in parsed.text
    assert parsed.structure and parsed.structure[0]["title"] == "Attention Is All You Need — paper explained"


def test_baseline_preserves_paragraph_breaks():
    doc = _fixture_doc("rag-chunking.html")
    parsed = get_parser("baseline").parse(doc)
    assert "\n\n" in parsed.text
    assert "Fixed-size windows" in parsed.text
    assert "Semantic chunking" in parsed.text


def test_baseline_keeps_metadata_title():
    doc = _fixture_doc("web-ingestion-pipeline.html")
    parsed = get_parser("baseline").parse(doc)
    assert parsed.title == "Building a web ingestion pipeline for RAG"
    assert parsed.metadata["description"].startswith("Search, fetch, parse")


def test_baseline_rejects_pdf_gracefully():
    doc = FetchedDocument(url="https://x.test/report.pdf", content=b"%PDF-1.4 fake", is_pdf=True)
    parsed = get_parser("baseline").parse(doc)
    assert parsed.text == ""
    assert parsed.warnings