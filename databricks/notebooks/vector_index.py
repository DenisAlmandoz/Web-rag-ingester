# Databricks notebook source
# ruff: noqa
"""Job 2 entry point: create/sync the delta-sync vector index with embeddings.

Widgets (base_parameters) come from the bundle job definition:
  catalog, schema, chunks_table, documents_table,
  vs_endpoint_name, vs_index_name, embedding_model
"""
import logging
import os

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _widget(name: str, default: str = "") -> str:
    try:
        from databricks.sdk.runtime import dbutils  # type: ignore[import-not-found]

        return dbutils.widgets.get(name) or default
    except Exception:
        return default

# COMMAND ----------

os.environ["DATABRICKS_HOST"] = _widget("databricks_host", "")

# COMMAND ----------

from web_ingestion.config import Settings  # noqa: E402
from web_ingestion.databricks.vector_index import VectorSearchManager  # noqa: E402

settings = Settings(
    databricks_catalog=_widget("catalog", "main"),
    databricks_schema=_widget("schema", "web_ingest"),
    databricks_table=_widget("chunks_table", "web_chunks"),
    databricks_documents_table=_widget("documents_table", "web_documents"),
    databricks_endpoint_name=_widget("vs_endpoint_name", "vector-search-web-endpoint"),
    databricks_index_name=_widget("vs_index_name", "web_chunks_index"),
    databricks_embedding_model=_widget("embedding_model", "databricks-gte-large-en"),
)

manager = VectorSearchManager(settings)
index = manager.sync_index(wait=True)

print(f"index {manager.index_name} ready (endpoint={manager.endpoint_name}, embedding={manager.embedding_model})")