"""Delta-sync vector index over the chunks table.

Ported from `oreilly-mlops-with-databricks/llmops/src/arxiv_curator/vector_search.py`:
endpoint exists-guard -> create, index exists-guard -> create_delta_sync_index,
wait until the index finished provisioning, then `sync()`. Embeddings are
computed server-side by the Delta Sync pipeline from `embedding_source_column`,
so nothing embeds locally.
"""

from __future__ import annotations

import logging
from typing import Any

from web_ingestion.config import Settings, get_settings

from .client import configure_env

logger = logging.getLogger(__name__)


def qualified_index(settings: Settings) -> str:
    index_name = settings.databricks_index_name
    if "." in index_name:
        return index_name
    return f"{settings.databricks_catalog}.{settings.databricks_schema}.{index_name}"


class VectorSearchManager:
    """Sets up and syncs the vector search endpoint + delta-sync index."""

    def __init__(self, settings: Settings | None = None, client: Any = None) -> None:
        self.settings = settings or get_settings()
        self.client = client
        self.endpoint_name = self.settings.databricks_endpoint_name
        self.embedding_model = self.settings.databricks_embedding_model
        self.source_table = (
            f"{self.settings.databricks_catalog}.{self.settings.databricks_schema}.{self.settings.databricks_table}"
        )
        self.index_name = qualified_index(self.settings)

    def _vsc(self) -> Any:
        if self.client is None:
            configure_env(self.settings)
            from databricks.vector_search.client import VectorSearchClient

            self.client = VectorSearchClient()
        return self.client

    def create_endpoint_if_not_exists(self) -> None:
        vsc = self._vsc()
        if vsc.endpoint_exists(self.endpoint_name):
            logger.info("Vector search endpoint already exists: %s", self.endpoint_name)
            return
        logger.info("Creating vector search endpoint: %s", self.endpoint_name)
        vsc.create_endpoint_and_wait(name=self.endpoint_name, endpoint_type="STANDARD")

    def create_or_get_index(self) -> Any:
        vsc = self._vsc()
        self.create_endpoint_if_not_exists()

        if vsc.index_exists(endpoint_name=self.endpoint_name, index_name=self.index_name):
            logger.info("Vector search index already exists: %s", self.index_name)
            return vsc.get_index(endpoint_name=self.endpoint_name, index_name=self.index_name)

        logger.info("Creating vector search index: %s", self.index_name)
        return vsc.create_delta_sync_index(
            endpoint_name=self.endpoint_name,
            index_name=self.index_name,
            source_table_name=self.source_table,
            pipeline_type="TRIGGERED",
            primary_key="id",
            embedding_source_column="text",
            embedding_model_endpoint_name=self.embedding_model,
        )

    def sync_index(self, *, wait: bool = False) -> Any:
        """Bring the index up to date with the source table (then optionally block).

        A freshly-created delta-sync index starts in PROVISIONING; wait until it is
        ONLINE so the first sync() call never races the provisioning step.
        """
        index = self.create_or_get_index()
        logger.info("Waiting for vector search index to be ready: %s", self.index_name)
        index.wait_until_ready()
        logger.info("Syncing vector search index: %s", self.index_name)
        index.sync()
        if wait:
            index.wait_until_ready(wait_for_updates=True)
        return index
