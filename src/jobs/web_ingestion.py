"""Job 1 ETL: web search ingestion stored in Unity Catalog Delta tables.

`WebIngestionConfig` holds the job parameters (Databricks widgets / bundle
`base_parameters`), `WebIngestion` runs extract -> transform -> load:

    extract   search -> fetch -> parse (`run_pipeline`)
    transform processed chunks.jsonl / documents.jsonl -> table rows
    load      ensure + MERGE the chunks and documents Delta tables
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from vector_index import ChunksTable, DocumentsTable, load_chunks, load_documents
from web_ingestion.config import Settings
from web_ingestion.pipeline import RunResult, run_pipeline

from .widgets import widget

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "web-ingestion"


class WebIngestionConfig(BaseModel):
    """Job 1 parameters. `from_widgets()` reads the bundle `base_parameters`."""

    query: str = "attention is all you need transformer architecture explained"
    parser: str = "baseline"
    max_results: int = 5
    catalog: str = "main"
    schema_name: str = "web_ingest"
    databricks_host: str = ""
    databricks_warehouse_id: str = ""
    tavily_api_key: str = ""
    output_dir: Path = DEFAULT_OUTPUT_DIR

    @classmethod
    def from_widgets(cls) -> WebIngestionConfig:
        fields = cls.model_fields
        return cls(
            query=widget("query", fields["query"].default),
            parser=widget("parser", fields["parser"].default),
            max_results=int(widget("max_results", str(fields["max_results"].default))),
            catalog=widget("catalog", fields["catalog"].default),
            schema_name=widget("schema", fields["schema_name"].default),
            databricks_host=widget("databricks_host", fields["databricks_host"].default),
            databricks_warehouse_id=widget("databricks_warehouse_id", fields["databricks_warehouse_id"].default),
            tavily_api_key=widget("tavily_api_key", fields["tavily_api_key"].default),
            output_dir=Path(widget("output_dir", str(fields["output_dir"].default))),
        )

    def to_settings(self) -> Settings:
        """Build pipeline Settings; empty values fall back to env vars / .env."""
        kwargs: dict[str, Any] = {
            "databricks_catalog": self.catalog,
            "databricks_schema": self.schema_name,
            "output_dir": self.output_dir,
        }
        if self.tavily_api_key:
            kwargs["tavily_api_key"] = self.tavily_api_key
        if self.databricks_host:
            kwargs["databricks_host"] = self.databricks_host
        if self.databricks_warehouse_id:
            kwargs["databricks_warehouse_id"] = self.databricks_warehouse_id
        return Settings(**kwargs)


@dataclass
class IngestedRun:
    """transform() output: rows ready for the two Delta tables."""

    run_id: str
    chunks: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)


class WebIngestion:
    """ETL for job 1: search/fetch/parse -> clean/chunk -> Delta tables."""

    def __init__(self, config: WebIngestionConfig | None = None, *, client: Any = None) -> None:
        self.config = config or WebIngestionConfig.from_widgets()
        self.settings = self.config.to_settings()
        self.client = client

    def extract(self) -> RunResult:
        """search -> fetch -> parse each result into its own local run directory."""
        result = run_pipeline(
            self.config.query,
            settings=self.settings,
            parser_name=self.config.parser,
            max_results=self.config.max_results,
        )
        print(
            f"run {result.run_id}: {len(result.records)}/{len(result.search.results)} docs, {result.total_chunks} chunks"
        )
        return result

    def transform(self, result: RunResult) -> IngestedRun:
        """Read the cleaned run outputs as Delta-ready chunk/document rows."""
        chunks_file = result.run_dir / "processed" / "chunks.jsonl"
        documents_file = result.run_dir / "processed" / "documents.jsonl"
        data = IngestedRun(
            run_id=result.run_id,
            chunks=load_chunks(chunks_file),
            documents=load_documents(documents_file) if documents_file.exists() else [],
        )
        logger.info("run %s: %d chunk rows, %d document rows", data.run_id, len(data.chunks), len(data.documents))
        return data

    def load(self, data: IngestedRun) -> int:
        """Upsert the rows into the chunks/documents Delta tables (idempotent MERGE)."""
        chunks_table = ChunksTable(self.settings, client=self.client)
        chunks_table.ensure()
        written = chunks_table.merge(data.chunks)
        print(f"wrote {written} chunks -> {chunks_table.table_name}")

        documents_table = DocumentsTable(self.settings, client=self.client)
        documents_table.ensure()
        written_documents = documents_table.merge(data.documents)
        print(f"wrote {written_documents} documents -> {documents_table.table_name}")
        return written

    def run(self) -> int:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
        return self.load(self.transform(self.extract()))
