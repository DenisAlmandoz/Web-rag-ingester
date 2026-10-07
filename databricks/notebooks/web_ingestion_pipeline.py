# Databricks notebook source
# ruff: noqa
"""Job 1 entry point: search -> fetch -> parse -> clean -> chunk -> Delta tables.

Widgets (base_parameters) come from the bundle job definition:
  query, parser, max_results, catalog, schema,
  databricks_host, databricks_warehouse_id, tavily_api_key
"""
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _widget(name: str, default: str = "") -> str:
    try:
        from databricks.sdk.runtime import dbutils  # type: ignore[import-not-found]

        return dbutils.widgets.get(name) or default
    except Exception:
        return default

# COMMAND ----------

query = _widget("query", "attention is all you need transformer architecture explained")
parser = _widget("parser", "baseline")
max_results = int(_widget("max_results", "5") or 5)
catalog = _widget("catalog", "main")
schema = _widget("schema", "web_ingest")

os.environ["DATABRICKS_HOST"] = _widget("databricks_host", "")
os.environ["DATABRICKS_WAREHOUSE_ID"] = _widget("databricks_warehouse_id", "")
os.environ["TAVILY_API_KEY"] = _widget("tavily_api_key", "")
os.environ["OUTPUT_DIR"] = "/local_disk0/web-ingestion"

# COMMAND ----------

from web_ingestion.config import Settings  # noqa: E402
from web_ingestion.pipeline import run_pipeline  # noqa: E402

settings = Settings(
    tavily_api_key=os.environ.get("TAVILY_API_KEY", ""),
    databricks_host=os.environ.get("DATABRICKS_HOST", ""),
    databricks_warehouse_id=os.environ.get("DATABRICKS_WAREHOUSE_ID", ""),
    databricks_catalog=catalog,
    databricks_schema=schema,
    output_dir=Path("/local_disk0/web-ingestion"),
)

result = run_pipeline(query, parser_name=parser, max_results=max_results, settings=settings)
print(f"run {result.run_id}: {len(result.records)}/{len(result.search.results)} docs, {result.total_chunks} chunks")

# COMMAND ----------

from web_ingestion.databricks.table import ChunksTable, DocumentsTable, load_chunks, load_documents  # noqa: E402

chunks_file = result.run_dir / "processed" / "chunks.jsonl"
documents_file = result.run_dir / "processed" / "documents.jsonl"

chunks = ChunksTable(settings)
chunks.ensure()
n_chunks = chunks.merge(load_chunks(chunks_file))
print(f"wrote {n_chunks} chunks -> {chunks.table_name}")

documents = DocumentsTable(settings)
documents.ensure()
n_docs = documents.merge(load_documents(documents_file)) if documents_file.exists() else 0
print(f"wrote {n_docs} documents -> {documents.table_name}")