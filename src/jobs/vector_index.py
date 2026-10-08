"""Job 2 ETL: chunks Delta table uploaded into a Databricks Vector Search index.

`VectorIndexConfig` holds the job parameters (Databricks widgets / bundle
`base_parameters`), `VectorIndex` runs extract -> transform -> load:

    extract   SELECT * FROM the chunks Delta table (SQL warehouse)
    transform keep the rows that satisfy the index contract (id + text)
    load      create endpoint/index if needed, then delta-sync + wait
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from vector_index import ChunksTable, VectorSearchManager
from web_ingestion.config import Settings

from .widgets import widget

logger = logging.getLogger(__name__)


class VectorIndexConfig(BaseModel):
    """Job 2 parameters. `from_widgets()` reads the bundle `base_parameters`."""

    catalog: str = "main"
    schema_name: str = "web_ingest"
    chunks_table: str = "web_chunks"
    documents_table: str = "web_documents"
    vs_endpoint_name: str = "vector-search-web-endpoint"
    vs_index_name: str = "web_chunks_index"
    embedding_model: str = "databricks-gte-large-en"
    databricks_host: str = ""
    databricks_warehouse_id: str = ""

    @classmethod
    def from_widgets(cls) -> VectorIndexConfig:
        fields = cls.model_fields
        return cls(
            catalog=widget("catalog", fields["catalog"].default),
            schema_name=widget("schema", fields["schema_name"].default),
            chunks_table=widget("chunks_table", fields["chunks_table"].default),
            documents_table=widget("documents_table", fields["documents_table"].default),
            vs_endpoint_name=widget("vs_endpoint_name", fields["vs_endpoint_name"].default),
            vs_index_name=widget("vs_index_name", fields["vs_index_name"].default),
            embedding_model=widget("embedding_model", fields["embedding_model"].default),
            databricks_host=widget("databricks_host", fields["databricks_host"].default),
            databricks_warehouse_id=widget("databricks_warehouse_id", fields["databricks_warehouse_id"].default),
        )

    def to_settings(self) -> Settings:
        """Build Settings; empty values fall back to env vars / .env."""
        kwargs: dict[str, Any] = {
            "databricks_catalog": self.catalog,
            "databricks_schema": self.schema_name,
            "databricks_table": self.chunks_table,
            "databricks_documents_table": self.documents_table,
            "databricks_endpoint_name": self.vs_endpoint_name,
            "databricks_index_name": self.vs_index_name,
            "databricks_embedding_model": self.embedding_model,
        }
        if self.databricks_host:
            kwargs["databricks_host"] = self.databricks_host
        if self.databricks_warehouse_id:
            kwargs["databricks_warehouse_id"] = self.databricks_warehouse_id
        return Settings(**kwargs)


class VectorIndex:
    """ETL for job 2: chunks Delta table -> delta-sync vector index (server-side embeddings)."""

    def __init__(self, config: VectorIndexConfig | None = None, *, client: Any = None, vsc: Any = None) -> None:
        self.config = config or VectorIndexConfig.from_widgets()
        self.settings = self.config.to_settings()
        self.client = client  # WorkspaceClient for SQL execution (None -> built on demand)
        self.vsc = vsc  # VectorSearchClient (None -> built on demand)

    def extract(self) -> list[dict[str, Any]]:
        """Read the current chunk rows the index will be built from."""
        table = ChunksTable(self.settings, client=self.client)
        rows = table.query(f"SELECT * FROM {table.table_name}")
        print(f"extracted {len(rows)} chunk rows from {table.table_name}")
        return rows

    def transform(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep only rows that satisfy the index contract: a non-empty id and text."""
        valid = [row for row in rows if row.get("id") and row.get("text")]
        dropped = len(rows) - len(valid)
        if dropped:
            logger.warning("dropped %d chunk rows without id/text", dropped)
        if not valid:
            logger.warning("chunks table is empty - the index will sync with no rows")
        return valid

    def load(self, rows: list[dict[str, Any]]) -> Any:
        """Create the endpoint/index if missing, then delta-sync and wait until ready."""
        manager = VectorSearchManager(self.settings, client=self.vsc)
        index = manager.sync_index(wait=True)
        print(
            f"index {manager.index_name} ready from {len(rows)} chunk rows "
            f"(endpoint={manager.endpoint_name}, embedding={manager.embedding_model})"
        )
        return index

    def run(self) -> Any:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        return self.load(self.transform(self.extract()))
