"""Write `chunks.jsonl` + `documents.jsonl` into Unity Catalog Delta tables.

Two tables per run:

* chunks    - `id` (primary key), `text` (embedding source), url/title/...
              The vector index is a DELTA_SYNC index over this table, so the
              table is the contract. Change Data Feed must be on so the
              TRIGGERED pipeline can pick up inserts/updates incrementally.
* documents - one row per ingested page: parser, char counts, parse metadata.
              Joined to chunks on `doc_id` for provenance / filtering.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from web_ingestion.config import Settings, get_settings

from .client import workspace_client

logger = logging.getLogger(__name__)

CHUNK_COLUMNS = (
    "id",
    "doc_id",
    "url",
    "title",
    "chunk_index",
    "text",
    "char_count",
    "approx_tokens",
    "ingest_ts",
)
DOCUMENT_COLUMNS = (
    "doc_id",
    "url",
    "title",
    "parser",
    "raw_chars",
    "cleaned_chars",
    "chunk_count",
    "metadata_json",
    "ingest_ts",
)
MERGE_BATCH_SIZE = 100


def qualified_table(settings: Settings) -> str:
    return f"{settings.databricks_catalog}.{settings.databricks_schema}.{settings.databricks_table}"


def qualified_documents_table(settings: Settings) -> str:
    return f"{settings.databricks_catalog}.{settings.databricks_schema}.{settings.databricks_documents_table}"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.strip():
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{lineno}: expected a JSON object")
            rows.append(row)
    return rows


def load_chunks(path: Path) -> list[dict[str, Any]]:
    """Read a chunks.jsonl file (one JSON object per line)."""
    rows = _read_jsonl(path)
    for offset, row in enumerate(rows, start=1):
        if not row.get("id") or "text" not in row:
            raise ValueError(f"{path}: chunk #{offset} needs at least an 'id' and 'text'")
    return rows


def load_documents(path: Path) -> list[dict[str, Any]]:
    """Read documents.jsonl and add the `doc_id` the chunks table is keyed on."""
    from web_ingestion.pipeline import slugify

    rows = _read_jsonl(path)
    for offset, row in enumerate(rows, start=1):
        if not row.get("url"):
            raise ValueError(f"{path}: document #{offset} needs a 'url'")
        row["doc_id"] = slugify(row["url"])
        row["chunk_count"] = len(row.get("chunks") or [])
        row["metadata_json"] = json.dumps(row.get("metadata") or {}, ensure_ascii=False, default=str)
    return rows


def sql_quote(value: Any) -> str:
    """Single-quoted SQL string literal for our own data (doubles quotes)."""
    text = str(value).replace("\x00", "")
    return "'" + text.replace("'", "''") + "'"


def create_schema_statement(settings: Settings) -> str:
    return f"CREATE SCHEMA IF NOT EXISTS {settings.databricks_catalog}.{settings.databricks_schema}"


def create_table_statement(settings: Settings) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {qualified_table(settings)} (\n"
        "  id STRING NOT NULL,\n"
        "  doc_id STRING,\n"
        "  url STRING,\n"
        "  title STRING,\n"
        "  chunk_index INT,\n"
        "  text STRING,\n"
        "  char_count INT,\n"
        "  approx_tokens INT,\n"
        "  ingest_ts TIMESTAMP\n"
        ")\n"
        "USING DELTA\n"
        "TBLPROPERTIES (delta.enableChangeDataFeed = true)"
    )


def create_documents_table_statement(settings: Settings) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {qualified_documents_table(settings)} (\n"
        "  doc_id STRING NOT NULL,\n"
        "  url STRING,\n"
        "  title STRING,\n"
        "  parser STRING,\n"
        "  raw_chars INT,\n"
        "  cleaned_chars INT,\n"
        "  chunk_count INT,\n"
        "  metadata_json STRING,\n"
        "  ingest_ts TIMESTAMP\n"
        ")\n"
        "USING DELTA\n"
        "TBLPROPERTIES (delta.enableChangeDataFeed = true)"
    )


def enable_cdf_statement(table_name: str) -> str:
    return f"ALTER TABLE {table_name} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)"


def _chunk_values_row(row: dict[str, Any], ingest_ts: str) -> str:
    return (
        f"({sql_quote(row['id'])}, {sql_quote(row.get('doc_id', ''))}, {sql_quote(row.get('url', ''))}, "
        f"{sql_quote(row.get('title', ''))}, {int(row.get('index', 0))}, {sql_quote(row.get('text', ''))}, "
        f"{int(row.get('char_count', 0))}, {int(row.get('approx_tokens', 0))}, TIMESTAMP '{ingest_ts}')"
    )


def merge_statement(settings: Settings, rows: list[dict[str, Any]], ingest_ts: str) -> str:
    values = ",\n    ".join(_chunk_values_row(row, ingest_ts) for row in rows)
    return (
        f"MERGE INTO {qualified_table(settings)} AS target\n"
        "USING (\n"
        "  SELECT * FROM VALUES\n"
        f"    {values}\n"
        f") AS source ({', '.join(CHUNK_COLUMNS)})\n"
        "ON target.id = source.id\n"
        "WHEN MATCHED THEN UPDATE SET doc_id = source.doc_id, url = source.url, title = source.title, "
        "chunk_index = source.chunk_index, text = source.text, char_count = source.char_count, "
        "approx_tokens = source.approx_tokens\n"
        "WHEN NOT MATCHED THEN INSERT (id, doc_id, url, title, chunk_index, text, char_count, approx_tokens, ingest_ts) "
        "VALUES (source.id, source.doc_id, source.url, source.title, source.chunk_index, source.text, "
        "source.char_count, source.approx_tokens, source.ingest_ts)"
    )


def _document_values_row(row: dict[str, Any], ingest_ts: str) -> str:
    return (
        f"({sql_quote(row['doc_id'])}, {sql_quote(row.get('url', ''))}, {sql_quote(row.get('title', ''))}, "
        f"{sql_quote(row.get('parser', ''))}, {int(row.get('raw_chars', 0))}, {int(row.get('cleaned_chars', 0))}, "
        f"{int(row.get('chunk_count', 0))}, {sql_quote(row.get('metadata_json', '{}'))}, TIMESTAMP '{ingest_ts}')"
    )


def documents_merge_statement(settings: Settings, rows: list[dict[str, Any]], ingest_ts: str) -> str:
    values = ",\n    ".join(_document_values_row(row, ingest_ts) for row in rows)
    return (
        f"MERGE INTO {qualified_documents_table(settings)} AS target\n"
        "USING (\n"
        "  SELECT * FROM VALUES\n"
        f"    {values}\n"
        f") AS source ({', '.join(DOCUMENT_COLUMNS)})\n"
        "ON target.doc_id = source.doc_id\n"
        "WHEN MATCHED THEN UPDATE SET url = source.url, title = source.title, parser = source.parser, "
        "raw_chars = source.raw_chars, cleaned_chars = source.cleaned_chars, chunk_count = source.chunk_count, "
        "metadata_json = source.metadata_json\n"
        "WHEN NOT MATCHED THEN INSERT (doc_id, url, title, parser, raw_chars, cleaned_chars, chunk_count, "
        "metadata_json, ingest_ts) VALUES (source.doc_id, source.url, source.title, source.parser, "
        "source.raw_chars, source.cleaned_chars, source.chunk_count, source.metadata_json, source.ingest_ts)"
    )


class _DeltaTable:
    """Shared DDL/DML plumbing: schema guard, CDF, batched MERGE."""

    table_attr = ""
    filename = ""

    def __init__(self, settings: Settings | None = None, client: Any = None) -> None:
        self.settings = settings or get_settings()
        self.client = client
        self.table_name = f"{self.settings.databricks_catalog}.{self.settings.databricks_schema}.{getattr(self.settings, self.table_attr)}"
        self.warehouse_id = self.settings.databricks_warehouse_id

    def _client(self) -> Any:
        if self.client is None:
            self.client = workspace_client(self.settings)
        return self.client

    def execute(self, statement: str) -> None:
        self._execute(statement)

    def query(self, statement: str) -> list[dict[str, Any]]:
        """Run a SELECT and return one dict per row (inline disposition)."""
        response = self._execute(statement)
        result = getattr(response, "result", None)
        manifest = getattr(result, "manifest", None)
        columns = [column.name for column in (getattr(manifest, "schema", None) or [])]
        data = getattr(result, "data_array", None) or []
        return [dict(zip(columns, values)) for values in data]

    def _execute(self, statement: str) -> Any:
        from databricks.sdk.service.sql import Disposition, ExecuteStatementRequestOnWaitTimeout

        logger.debug("SQL: %s", statement[:200].replace("\n", " "))
        response = self._client().statement_execution.execute_statement(
            warehouse_id=self.warehouse_id,
            statement=statement,
            wait_timeout="60s",
            on_wait_timeout=ExecuteStatementRequestOnWaitTimeout.CANCEL,
            disposition=Disposition.INLINE,
        )
        status = response.status
        state = getattr(status.state, "name", str(status.state))
        if state != "SUCCEEDED":
            raise RuntimeError(f"statement {state}: {status.error or 'no detail'} (sql_state={status.sql_state})")
        return response

    def ensure(self) -> None:
        """Schema + table + Change Data Feed, all guarded so re-runs are safe."""
        self.execute(create_schema_statement(self.settings))
        self.execute(self._create_sql())
        self.execute(enable_cdf_statement(self.table_name))

    def merge(self, rows: list[dict[str, Any]]) -> int:
        """Upsert rows on the table's key, batched to keep statements small."""
        if not rows:
            return 0
        ingest_ts = datetime.now(UTC).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
        written = 0
        for start in range(0, len(rows), MERGE_BATCH_SIZE):
            batch = rows[start : start + MERGE_BATCH_SIZE]
            self.execute(self._merge_sql(batch, ingest_ts))
            written += len(batch)
        return written

    def _create_sql(self) -> str:
        raise NotImplementedError

    def _merge_sql(self, rows: list[dict[str, Any]], ingest_ts: str) -> str:
        raise NotImplementedError


class ChunksTable(_DeltaTable):
    """`web_chunks`: id / text + per-chunk metadata (the index source table)."""

    table_attr = "databricks_table"
    filename = "chunks.jsonl"

    def _create_sql(self) -> str:
        return create_table_statement(self.settings)

    def _merge_sql(self, rows: list[dict[str, Any]], ingest_ts: str) -> str:
        return merge_statement(self.settings, rows, ingest_ts)


class DocumentsTable(_DeltaTable):
    """`web_documents`: one row per ingested page, with its parse metadata."""

    table_attr = "databricks_documents_table"
    filename = "documents.jsonl"

    def _create_sql(self) -> str:
        return create_documents_table_statement(self.settings)

    def _merge_sql(self, rows: list[dict[str, Any]], ingest_ts: str) -> str:
        return documents_merge_statement(self.settings, rows, ingest_ts)
