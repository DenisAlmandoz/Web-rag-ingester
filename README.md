# Web Search Ingestion for RAG

A hands-on companion to `production-agentic-rag-course`: instead of ingesting arXiv
preprints, this project retrieves **arbitrary web content** via the [Tavily API](https://tavily.com)
and runs it through a transformation chain that makes it RAG-ready.

```
                        ┌─────────────┐
   "any query" ───────▶ │   SEARCH    │  Tavily (or offline mock)
                        └──────┬──────┘
                               ▼
                        ┌─────────────┐
   ranked URLs ───────▶ │   FETCH     │  httpx: redirects, timeouts, size cap, %PDF check
                        └──────┬──────┘
                               ▼
                        ┌─────────────┐
   raw bytes ─────────▶ │   PARSE     │  baseline (bs4) · trafilatura · docling · unstructured
                        └──────┬──────┘
                               ▼
                        ┌─────────────┐
   text ──────────────▶ │   CLEAN     │  unicode, wrappers, boilerplate lines, dedupe
                        └──────┬──────┘
                               ▼
                        ┌─────────────┐
   clean text ────────▶ │   CHUNK     │  paragraph-aware windows + overlap → JSONL
                        └──────┬──────┘
                               ▼
                        documents.jsonl + chunks.jsonl  (ready to embed/index)
```

## Quickstart (no API key needed)

```bash
uv sync --group dev        # core pipeline + dev tools (lightweight)
uv sync --extra trafilatura --extra unstructured   # optional parsers (recommended)
make demo                  # offline end-to-end run over bundled fixture pages
make compare               # baseline vs trafilatura vs unstructured side-by-side
make test                  # pytest suite
```

`demo` fetches fixture HTML pages from `fixtures/pages/`, runs baseline parsing,
cleans and chunks them, and writes a full run under `data/runs/<timestamp>/`.

## Going live with Tavily

1. Get a free key at https://app.tavily.com
2. `cp .env.example .env`, then put the key in `.env`
3. `make run "your query"` — or:

```bash
uv run web-ingest run "what is self-attention" --parser trafilatura
```

With a key set, search hits the real Tavily `/search` endpoint; without one, the
pipeline replays `fixtures/search_results.json` offline (see `--mock_mode` in
`web_ingestion/config.py`).

## Comparing parsers

Parsers live behind a lazy adapter interface (`web_ingestion/parsers/`), so the core
install runs fast and heavier parsers are opt-in:

| parser        | handles      | install                     |
|---------------|--------------|-----------------------------|
| `baseline`    | HTML         | built-in (beautifulsoup4)   |
| `trafilatura` | HTML         | `make install-trafilatura`  |
| `unstructured`| PDF + HTML   | `make install-unstructured` (spaCy model downloaded on first use) |
| `docling`     | PDF + HTML   | `make install-docling` — Linux/Docker or macOS 14+ |

Install all usable parsers on this machine with `make install-parsers`. Do **not**
run `uv sync --extra <one>` repeatedly to add parsers: uv replaces extras on each
sync, so pass them together (the Makefile targets handle this).

> **Why no docling here?** Docling pulls in `torch` and `docling-parse` (a C++
> extension). Current torch releases ship macOS 14+ arm64 wheels only, and
> `docling-parse` has to compile from source — which fails on this Mac's toolchain.
> It works fine in the course repo because that runs Docling inside a Linux Docker
> container. The `DoclingParser` adapter in this repo mirrors that container's
> `src/services/pdf_parser/docling.py`; on Linux/macOS 14+ just `make install-docling`.

Compare every installed parser on one page:

```bash
make compare
# or against a live URL:
uv run web-ingest compare https://en.wikipedia.org/wiki/Retrieval-augmented_generation
```

The diff (char counts before/after cleaning, structure items, parse time, preview) is
written to `data/comparisons/<slug>.md`. The notebook
`notebooks/01_parser_comparison.ipynb` walks through the same comparison
interactively and shows raw vs cleaned text side by side.

## Pushing chunks into a Databricks Vector Index

`web-ingest index` hands `chunks.jsonl` (plus `documents.jsonl`) off to Databricks
so retrieval can happen against a managed vector index. The pattern mirrors the
arxiv curator in `oreilly-mlops-with-databricks`:

```
documents.jsonl ─┐
                 ├─SQL warehouse─▶ catalog.schema.web_documents (per-page metadata)
chunks.jsonl ────┘
                 └─SQL warehouse─▶ catalog.schema.web_chunks (Delta, CDF on)
                                        │  delta sync (TRIGGERED)
                                        ▼
                              catalog.schema.web_chunks_index
                              embeddings from databricks-gte-large-en (server-side)
```

`web_chunks` is the index source: `id` (primary key), `text` (embedding source),
plus `url`, `title`, `doc_id`, `chunk_index`, `char_count`, `approx_tokens`,
`ingest_ts`. `web_documents` keeps one row per page (`doc_id`, `url`, `title`,
`parser`, `raw_chars`, `cleaned_chars`, `chunk_count`, `metadata_json`) joined to
the chunks on `doc_id`.

1. Install the SDK: `make install-databricks`
2. Fill in the `--- Databricks ---` block in `.env`:

```bash
DATABRICKS_HOST="https://xxxxxxxx.cloud.databricks.com"
DATABRICKS_CLIENT_ID=""            # service principal (CI/CD style auth)
DATABRICKS_CLIENT_SECRET=""
DATABRICKS_WAREHOUSE_ID=""         # SQL warehouse used to write the table
```

Leave the SPN pair empty to fall back to ambient auth (Databricks CLI / VS Code
extension / `~/.databrickscfg`).

3. Run it:

```bash
uv run web-ingest index --dry-run      # show plan, no calls
uv run web-ingest index                # write table + create index + sync
uv run web-ingest index --wait         # ...and block until the index is ready
uv run web-ingest index --run 20261007-144442   # a specific run
uv run web-ingest index --no-sync      # table only
```

Everything is guarded, so re-runs are safe: `CREATE SCHEMA/TABLE IF NOT EXISTS`,
Change Data Feed enabled via `ALTER TABLE`, `MERGE` on `id`, and exists-checks on
the endpoint/index before `create_delta_sync_index` + `sync()`.

> **Embeddings are generated by Databricks**, from the `text` column — nothing
> embeds locally, and the Delta Sync pipeline owns index freshness. The table is
> the contract: `id` (primary key), `text` (embedding source), plus `url`,
> `title`, `doc_id`, `chunk_index` for filtered retrieval.

The service principal needs `CAN CREATE TABLE` on the schema and permission to
manage the vector search endpoint.

## Output layout of one run

```
data/runs/<timestamp>/
    search_results.json          what the provider returned
    raw/<slug>.html              untouched payloads (reproducibility)
    parsed/<parser>/<slug>.json  parser output before cleaning
    processed/documents.jsonl    cleaned text + metadata (one JSON object per doc)
    processed/chunks.jsonl       chunks ready to embed (id, text, url, title)
    report.md                    human-readable summary
```

## CLI

```
web-ingest parsers                     list installed parsers
web-ingest search "query"              print Tavily/mock results
web-ingest run "query" [--parser X]    full pipeline
web-ingest run --urls URL1 URL2 ...    skip search, ingest URLs directly
web-ingest compare URL [--fixture p]   parser side-by-side
web-ingest demo                        offline run over fixtures
web-ingest index [--dry-run|--no-sync|--wait]   push chunks to a Databricks vector index
```

## Testing / lint

```bash
make test       # pytest (offline, no network)
make lint       # ruff check
make format     # ruff format
```

Tests in `tests/` exercise cleaning rules, chunk boundaries/overlap, mock search,
baseline extraction and the full pipeline in mock mode — no API key or network needed.