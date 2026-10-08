"""Orchestration: search -> fetch -> parse -> clean -> chunk -> persist.

Output layout per run:

    data/runs/<run_id>/
        search_results.json          what the provider returned
        raw/<slug>.html              untouched payloads (reproducibility)
        parsed/<parser>/<slug>.json  parser output before cleaning
        processed/documents.jsonl    cleaned text + chunk boundaries (RAG-ready)
        report.md                    human-readable summary
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .config import Settings, get_settings
from .fetch import HttpFetcher, save_raw
from .models import Chunk, DocumentRecord, FetchedDocument, ParsedDocument, SearchResponse, SearchResult
from .parsers import get_parser, timed_parse
from .search import get_search_client
from .transform import chunk_text, clean_text, dedupe_lines

logger = logging.getLogger(__name__)


@dataclass
class RunResult:
    run_id: str
    run_dir: Path
    search: SearchResponse
    records: list[DocumentRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_chunks(self) -> int:
        return sum(len(r.chunks) for r in self.records)


def slugify(value: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug[:max_len] or "page"


def run_pipeline(
    query: str,
    *,
    settings: Settings | None = None,
    parser_name: str | None = None,
    max_results: int | None = None,
    urls: list[str] | None = None,
) -> RunResult:
    settings = settings or get_settings()
    parser_name = parser_name or settings.default_parser

    parser = get_parser(parser_name)
    if parser is None:
        from .parsers import unavailable_reason

        raise RuntimeError(unavailable_reason(parser_name))

    fetcher = HttpFetcher(settings)
    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    run_dir = settings.output_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1. SEARCH ------------------------------------------------------------
    if urls:
        search = SearchResponse(query=query, provider="direct", results=[SearchResult(title=u, url=u) for u in urls])
    else:
        client = get_search_client(settings)
        logger.info("Searching via %s: %r", client.provider, query)
        search = client.search(query, max_results=max_results)

    (run_dir / "search_results.json").write_text(search.model_dump_json(indent=2), encoding="utf-8")

    result = RunResult(run_id=run_id, run_dir=run_dir, search=search)

    # 2-5. FETCH -> PARSE -> CLEAN -> CHUNK --------------------------------
    for i, item in enumerate(search.results, start=1):
        try:
            doc = fetcher.fetch(item.url, fixture_path=item.fixture_path)
            save_raw(doc, run_dir / "raw")
            record = _process_one(doc, item, parser, settings, run_dir)
            result.records.append(record)
            logger.info(
                "[%d/%d] %s -> %d chars, %d chunks",
                i,
                len(search.results),
                item.url,
                record.cleaned_chars,
                len(record.chunks),
            )
        except Exception as exc:  # noqa: BLE001 - one bad URL must not kill the run
            logger.error("Failed %s: %s", item.url, exc)
            result.errors.append(f"{item.url}: {exc}")

    _write_outputs(result)
    return result


def _process_one(
    doc: FetchedDocument,
    item: SearchResult,
    parser,
    settings: Settings,
    run_dir: Path,
) -> DocumentRecord:
    doc.title_hint = item.title

    parsed: ParsedDocument = timed_parse(parser, doc)
    parsed_dir = run_dir / "parsed" / parser.name
    parsed_dir.mkdir(parents=True, exist_ok=True)
    (parsed_dir / f"{slugify(doc.url)}.json").write_text(parsed.model_dump_json(indent=2), encoding="utf-8")

    cleaned = clean_text(dedupe_lines(parsed.text))
    doc_id = slugify(doc.url)
    chunks: list[Chunk] = chunk_text(
        cleaned,
        doc_id=doc_id,
        url=doc.url,
        title=parsed.title or item.title,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )

    return DocumentRecord(
        url=doc.url,
        title=parsed.title or item.title,
        parser=parser.name,
        raw_chars=len(parsed.text),
        cleaned_chars=len(cleaned),
        chunks=chunks,
        metadata={**parsed.metadata, "parse_seconds": round(parsed.parse_seconds, 3), "warnings": parsed.warnings},
    )


def _write_outputs(result: RunResult) -> None:
    processed_dir = result.run_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    with (processed_dir / "documents.jsonl").open("w", encoding="utf-8") as fh:
        for record in result.records:
            fh.write(record.model_dump_json() + "\n")

    with (processed_dir / "chunks.jsonl").open("w", encoding="utf-8") as fh:
        for record in result.records:
            for chunk in record.chunks:
                fh.write(chunk.model_dump_json() + "\n")

    lines = [
        f"# Run {result.run_id}",
        "",
        f"- Query: `{result.search.query}`",
        f"- Provider: {result.search.provider} (mock={result.search.mock})",
        f"- Parser: {result.records[0].parser if result.records else 'n/a'}",
        f"- Documents: {len(result.records)} / {len(result.search.results)}",
        f"- Chunks: {result.total_chunks}",
        f"- Errors: {len(result.errors)}",
        "",
        "| URL | raw chars | cleaned chars | chunks |",
        "|---|---:|---:|---:|",
    ]
    for record in result.records:
        lines.append(f"| {record.url} | {record.raw_chars} | {record.cleaned_chars} | {len(record.chunks)} |")
    if result.errors:
        lines += ["", "## Errors", ""] + [f"- {e}" for e in result.errors]

    (result.run_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
