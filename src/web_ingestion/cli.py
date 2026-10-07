"""Command line entry point: `web-ingest <command>`."""

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import FIXTURES_DIR, get_settings
from .databricks import (
    ChunksTable,
    DocumentsTable,
    VectorSearchManager,
    load_chunks,
    load_documents,
    qualified_documents_table,
    qualified_index,
    qualified_table,
    resolve_chunks_file,
)
from .parsers import available_parsers, unavailable_reason
from .pipeline import compare_parsers, run_pipeline, write_comparison


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="web-ingest", description="Web search ingestion pipeline for RAG")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p_parsers = sub.add_parser("parsers", help="show which parsers are installed")
    p_parsers.set_defaults(func=cmd_parsers)

    p_search = sub.add_parser("search", help="run a Tavily search and print results")
    p_search.add_argument("query")
    p_search.add_argument("--max", type=int, default=None)
    p_search.set_defaults(func=cmd_search)

    p_run = sub.add_parser("run", help="full pipeline: search -> fetch -> parse -> clean -> chunk")
    p_run.add_argument("query", nargs="?", default="attention is all you need")
    p_run.add_argument("--parser", default=None, help="baseline | trafilatura | docling | unstructured")
    p_run.add_argument("--max", type=int, default=None)
    p_run.add_argument("--urls", nargs="*", default=None, help="skip search, ingest these URLs directly")
    p_run.set_defaults(func=cmd_run)

    p_compare = sub.add_parser("compare", help="parse one page with every installed parser")
    p_compare.add_argument("url")
    p_compare.add_argument("--fixture", default=None, help="read the page from fixtures/ instead of the network")
    p_compare.set_defaults(func=cmd_compare)

    p_demo = sub.add_parser("demo", help="offline end-to-end run using bundled fixtures")
    p_demo.add_argument("--parser", default=None)
    p_demo.set_defaults(func=cmd_demo)

    p_index = sub.add_parser("index", help="push chunks.jsonl into a Databricks Delta table + vector index")
    p_index.add_argument("--run", default=None, help="run id under data/runs (default: latest run)")
    p_index.add_argument("--chunks", default=None, help="path to a chunks.jsonl (overrides --run)")
    p_index.add_argument("--dry-run", action="store_true", help="print the plan only, no Databricks calls")
    p_index.add_argument("--no-sync", action="store_true", help="write the Delta table but skip the index sync")
    p_index.add_argument("--wait", action="store_true", help="block until the index reports ready")
    p_index.set_defaults(func=cmd_index)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


def cmd_parsers(args) -> int:
    for name, installed in available_parsers().items():
        status = "installed" if installed else f"MISSING ({unavailable_reason(name)})"
        print(f"{name:15s} {status}")
    return 0


def cmd_search(args) -> int:
    from .search import get_search_client

    settings = get_settings()
    client = get_search_client(settings)
    response = client.search(args.query, max_results=args.max)
    print(f"provider={response.provider} mock={response.mock} results={len(response.results)}")
    for i, item in enumerate(response.results, 1):
        print(f"{i}. {item.title}\n   {item.url}  (score={item.score:.3f})")
        print(f"   {item.content[:160]}")
    return 0


def cmd_run(args) -> int:
    try:
        result = run_pipeline(args.query, parser_name=args.parser, max_results=args.max, urls=args.urls)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
    _print_summary(result)
    return 0 if not result.errors else 2


def cmd_demo(args) -> int:
    settings = get_settings()
    if not settings.mock_mode:
        print("note: TAVILY_API_KEY is set; demo still uses fixtures (no network)")
    fixture_query = json.loads((FIXTURES_DIR / "search_results.json").read_text(encoding="utf-8")).get("query", "demo")
    result = run_pipeline(fixture_query, parser_name=args.parser, settings=settings)
    _print_summary(result)
    return 0 if not result.errors else 2


def cmd_index(args) -> int:
    settings = get_settings()
    try:
        chunks_file = resolve_chunks_file(settings, run_id=args.run, chunks_path=args.chunks)
        rows = load_chunks(chunks_file)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    documents_file = chunks_file.with_name("documents.jsonl")
    document_rows: list[dict] = []
    note = ""
    if not documents_file.exists():
        note = f"note: {documents_file} missing - only the chunks table will be written"
    else:
        try:
            document_rows = load_documents(documents_file)
        except ValueError as exc:
            note = f"note: document metadata unreadable ({exc}) - only the chunks table will be written"
    if note:
        print(note)

    print(f"chunks    {chunks_file} ({len(rows)} rows)")
    print(f"documents {documents_file} ({len(document_rows)} rows)" if document_rows else "documents -")
    print(f"table     {qualified_table(settings)}")
    print(f"table     {qualified_documents_table(settings)}")
    print(
        f"index     {qualified_index(settings)} "
        f"(endpoint={settings.databricks_endpoint_name}, embedding={settings.databricks_embedding_model})"
    )
    if args.dry_run:
        print("dry run: no Databricks calls made")
        return 0

    if not settings.databricks_ready:
        print(
            "error: Databricks is not configured - set DATABRICKS_HOST and DATABRICKS_WAREHOUSE_ID in .env",
            file=sys.stderr,
        )
        return 1

    try:
        table = ChunksTable(settings)
        table.ensure()
        written = table.merge(rows)
        print(f"wrote     {written} rows -> {table.table_name}")
        if document_rows:
            documents = DocumentsTable(settings)
            documents.ensure()
            doc_written = documents.merge(document_rows)
            print(f"wrote     {doc_written} rows -> {documents.table_name}")
    except Exception as exc:  # noqa: BLE001
        print(f"error: table write failed: {exc}", file=sys.stderr)
        return 1

    if args.no_sync:
        print("skipped index sync (--no-sync)")
        return 0

    try:
        manager = VectorSearchManager(settings)
        manager.sync_index(wait=args.wait)
    except Exception as exc:  # noqa: BLE001
        print(f"error: index sync failed: {exc}", file=sys.stderr)
        return 1
    print(f"synced    {manager.index_name}" + (" (ready)" if args.wait else ""))
    return 0


def cmd_compare(args) -> int:
    comparison = compare_parsers(args.url, fixture_path=args.fixture)
    out = Path(get_settings().output_dir) / "comparisons" / f"{_slug(args.url)}.md"
    write_comparison(comparison, out)
    for name, info in comparison["parsers"].items():
        if not info.get("installed"):
            print(f"{name:15s} not installed")
        else:
            print(
                f"{name:15s} raw={info['raw_chars']:>7} cleaned={info['cleaned_chars']:>7} "
                f"structure={info['structure']:>3} time={info['parse_seconds']:.2f}s"
            )
    print(f"\nfull comparison written to {out}")
    return 0


def _print_summary(result) -> None:
    print(
        f"\nrun {result.run_id}: {len(result.records)}/{len(result.search.results)} docs, {result.total_chunks} chunks"
    )
    for record in result.records:
        print(f"  {record.url}\n    {record.raw_chars} -> {record.cleaned_chars} chars, {len(record.chunks)} chunks")
    for error in result.errors:
        print(f"  ERROR {error}")
    print(f"outputs: {result.run_dir}")


def _slug(value: str) -> str:
    from .pipeline import slugify

    return slugify(value)


if __name__ == "__main__":
    raise SystemExit(main())
