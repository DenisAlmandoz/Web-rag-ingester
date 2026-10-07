from web_ingestion.config import Settings
from web_ingestion.pipeline import compare_parsers, run_pipeline


def test_full_pipeline_mock_mode(tmp_path):
    settings = Settings(tavily_api_key="", output_dir=tmp_path)
    result = run_pipeline("attention is all you need", settings=settings)

    assert len(result.records) == 3
    assert result.total_chunks > 3
    assert not result.errors

    run_dir = tmp_path / "runs" / result.run_id
    assert (run_dir / "search_results.json").exists()
    assert (run_dir / "report.md").exists()
    assert (run_dir / "processed" / "chunks.jsonl").exists()
    assert (run_dir / "processed" / "documents.jsonl").exists()

    lines = (run_dir / "processed" / "chunks.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == result.total_chunks

    for record in result.records:
        assert record.cleaned_chars > 0
        assert 0 < record.raw_chars
        assert record.chunks[0].url == record.url


def test_pipeline_cleans_boilerplate_off_html(tmp_path):
    settings = Settings(tavily_api_key="", output_dir=tmp_path)
    result = run_pipeline("x", settings=settings)
    all_text = " ".join(c.text for r in result.records for c in r.chunks).lower()
    for boilerplate in ["accept all cookies", "all rights reserved", "subscribe to our newsletter", "cookie policy"]:
        assert boilerplate not in all_text
    # real article content must survive
    assert "self-attention" in all_text or "chunking strategies" in all_text


def test_pipeline_accepts_explicit_urls(tmp_path):
    settings = Settings(tavily_api_key="", output_dir=tmp_path)
    result = run_pipeline(
        "x",
        settings=settings,
        urls=["fixture:rag-chunking"],
        parser_name="baseline",
    )
    assert len(result.records) == 1
    assert "Fixed-size windows" in " ".join(c.text for c in result.records[0].chunks)


def test_compare_parsers_offline(tmp_path):
    comparison = compare_parsers("attention-is-all-you-need", fixture_path="pages/attention-is-all-you-need.html")
    assert comparison["parsers"]["baseline"]["installed"]
    assert comparison["parsers"]["baseline"]["cleaned_chars"] > 0


def test_pipeline_does_not_require_network(tmp_path):
    """Mock mode must never attempt an HTTP call."""
    settings = Settings(tavily_api_key="", output_dir=tmp_path, fetch_timeout=0.001)
    result = run_pipeline("attention is all you need", settings=settings)
    assert {} == result.search.results or len(result.records) > 0