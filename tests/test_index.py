from types import SimpleNamespace

import pytest

from vector_index.table import (
    MERGE_BATCH_SIZE,
    ChunksTable,
    DocumentsTable,
    create_documents_table_statement,
    create_table_statement,
    documents_merge_statement,
    load_chunks,
    load_documents,
    merge_statement,
    sql_quote,
)
from vector_index.vector_index import VectorSearchManager, qualified_index
from web_ingestion.config import Settings


class FakeStatementExecution:
    def __init__(self, state: str = "SUCCEEDED"):
        self.statements: list[str] = []
        self.state = state

    def execute_statement(self, **kwargs):
        self.statements.append(kwargs["statement"])
        status = SimpleNamespace(state=SimpleNamespace(name=self.state), error="boom", sql_state="42000")
        return SimpleNamespace(status=status)


class FakeIndex:
    def __init__(self):
        self.synced = 0
        self.waited_with: list[dict] = []

    def sync(self):
        self.synced += 1

    def wait_until_ready(self, **kwargs):
        self.waited_with.append(kwargs)


class FakeVSC:
    def __init__(self, endpoint_exists: bool = True, index_exists: bool = False):
        self._endpoint_exists = endpoint_exists
        self._index_exists = index_exists
        self.endpoint_creates: list[str] = []
        self.index_creates: list[dict] = []
        self.index = FakeIndex()

    def endpoint_exists(self, name):
        return self._endpoint_exists

    def create_endpoint_and_wait(self, name, endpoint_type="STANDARD", **kwargs):
        self.endpoint_creates.append(name)
        self._endpoint_exists = True

    def index_exists(self, endpoint_name=None, index_name=None):
        return self._index_exists

    def create_delta_sync_index(self, **kwargs):
        self.index_creates.append(kwargs)
        return self.index

    def get_index(self, endpoint_name=None, index_name=None):
        return self.index


def _settings(tmp_path, **overrides) -> Settings:
    overrides.setdefault("databricks_host", "")
    overrides.setdefault("databricks_warehouse_id", "")
    overrides.setdefault("databricks_catalog", "main")
    overrides.setdefault("databricks_schema", "web_ingest")
    overrides.setdefault("databricks_table", "web_chunks")
    overrides.setdefault("databricks_documents_table", "web_documents")
    overrides.setdefault("databricks_index_name", "web_chunks_index")
    return Settings(tavily_api_key="", output_dir=tmp_path, **overrides)


def _dbx_settings(**overrides) -> Settings:
    """Databricks names pinned so the tests do not depend on the local .env."""
    defaults = {
        "databricks_host": "",
        "databricks_warehouse_id": "",
        "databricks_catalog": "main",
        "databricks_schema": "web_ingest",
        "databricks_table": "web_chunks",
        "databricks_documents_table": "web_documents",
        "databricks_endpoint_name": "vector-search-web-endpoint",
        "databricks_index_name": "web_chunks_index",
        "databricks_embedding_model": "databricks-gte-large-en",
    }
    defaults.update(overrides)
    return Settings(tavily_api_key="", **defaults)


def _write_documents(tmp_path, count=2, run_id="20261007-120000"):
    run_dir = tmp_path / "runs" / run_id / "processed"
    run_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        (
            f'{{"url": "https://x/{i}", "title": "T{i}", "parser": "trafilatura", "raw_chars": 100, '
            f'"cleaned_chars": 90, "chunks": [{{"id": "c"}}, {{"id": "d"}}], '
            f'"metadata": {{"parse_seconds": 0.01, "description": "a page"}}}}'
        )
        for i in range(count)
    ]
    path = run_dir / "documents.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_sql_quote_doubles_quotes_and_drops_nulls():
    assert sql_quote("it's") == "'it''s'"
    assert sql_quote("a\x00b") == "'ab'"
    assert sql_quote(42) == "'42'"


def test_merge_statement_upserts_on_id():
    settings = _dbx_settings()
    rows = [{"id": "a::0", "doc_id": "a", "url": "https://x", "title": "t", "index": 0, "text": "hi"}]
    statement = merge_statement(settings, rows, "2026-10-07 12:00:00")

    assert statement.startswith(f"MERGE INTO {settings.databricks_catalog}.")
    assert "ON target.id = source.id" in statement
    assert "WHEN MATCHED THEN UPDATE SET" in statement
    assert "WHEN NOT MATCHED THEN INSERT" in statement
    assert "'hi'" in statement


def test_create_table_statement_enables_change_data_feed():
    statement = create_table_statement(_dbx_settings())
    assert "CREATE TABLE IF NOT EXISTS" in statement
    assert "USING DELTA" in statement
    assert "delta.enableChangeDataFeed = true" in statement
    assert "id STRING NOT NULL" in statement
    assert "text STRING" in statement


def test_create_documents_table_statement():
    statement = create_documents_table_statement(_dbx_settings())
    assert "CREATE TABLE IF NOT EXISTS main.web_ingest.web_documents" in statement
    assert "USING DELTA" in statement
    assert "delta.enableChangeDataFeed = true" in statement
    assert "doc_id STRING NOT NULL" in statement
    assert "metadata_json STRING" in statement
    assert "text STRING" not in statement


def test_documents_merge_upserts_on_doc_id():
    settings = _dbx_settings()
    rows = [{"doc_id": "a", "url": "https://x", "title": "t", "parser": "baseline", "metadata_json": "{}"}]
    statement = documents_merge_statement(settings, rows, "2026-10-07 12:00:00")

    assert statement.startswith("MERGE INTO main.web_ingest.web_documents")
    assert "ON target.doc_id = source.doc_id" in statement
    assert "WHEN MATCHED THEN UPDATE SET" in statement
    assert "WHEN NOT MATCHED THEN INSERT" in statement
    assert "metadata_json" in statement


def test_load_documents_adds_doc_id_counts_and_metadata_json(tmp_path):
    path = _write_documents(tmp_path)
    rows = load_documents(path)

    assert len(rows) == 2
    assert rows[0]["doc_id"] == "https-x-0"
    assert rows[0]["chunk_count"] == 2
    assert '"parse_seconds": 0.01' in rows[0]["metadata_json"]


def test_load_documents_requires_url(tmp_path):
    path = tmp_path / "documents.jsonl"
    path.write_text('{"title": "no url"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="url"):
        load_documents(path)


def test_documents_table_ensure_and_merge(tmp_path):
    fake = FakeStatementExecution()
    table = DocumentsTable(_settings(tmp_path), client=SimpleNamespace(statement_execution=fake))

    table.ensure()
    rows = load_documents(_write_documents(tmp_path))
    assert table.merge(rows) == 2

    assert fake.statements[1].startswith("CREATE TABLE IF NOT EXISTS main.web_ingest.web_documents")
    assert fake.statements[2].startswith("ALTER TABLE")
    assert fake.statements[3].startswith("MERGE INTO main.web_ingest.web_documents")


def test_merge_is_batched(tmp_path):
    settings = _settings(tmp_path)
    fake = FakeStatementExecution()
    table = ChunksTable(settings, client=SimpleNamespace(statement_execution=fake))
    rows = [{"id": f"d{i}", "text": "x"} for i in range(MERGE_BATCH_SIZE + 50)]

    assert table.merge(rows) == MERGE_BATCH_SIZE + 50
    assert len(fake.statements) == 2
    assert fake.statements[0].startswith("MERGE INTO")


def test_merge_empty_is_noop(tmp_path):
    table = ChunksTable(_settings(tmp_path), client=SimpleNamespace(statement_execution=FakeStatementExecution()))
    assert table.merge([]) == 0


def test_ensure_runs_schema_table_and_cdf(tmp_path):
    settings = _settings(tmp_path)
    fake = FakeStatementExecution()
    table = ChunksTable(settings, client=SimpleNamespace(statement_execution=fake))

    table.ensure()

    assert len(fake.statements) == 3
    assert fake.statements[0].startswith("CREATE SCHEMA IF NOT EXISTS")
    assert fake.statements[1].startswith("CREATE TABLE IF NOT EXISTS")
    assert fake.statements[2].startswith("ALTER TABLE")
    assert "delta.enableChangeDataFeed = true" in fake.statements[2]


def test_failed_statement_raises(tmp_path):
    table = ChunksTable(
        _settings(tmp_path), client=SimpleNamespace(statement_execution=FakeStatementExecution(state="FAILED"))
    )
    with pytest.raises(RuntimeError, match="FAILED"):
        table.ensure()


def test_load_chunks_rejects_rows_without_text(tmp_path):
    path = tmp_path / "chunks.jsonl"
    path.write_text('{"id": "a"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="id"):
        load_chunks(path)


def test_qualified_index_defaults_to_catalog_schema(tmp_path):
    assert qualified_index(_settings(tmp_path)) == "main.web_ingest.web_chunks_index"
    custom = _settings(tmp_path, databricks_index_name="other.schema.idx")
    assert qualified_index(custom) == "other.schema.idx"


def test_manager_creates_endpoint_and_index():
    vsc = FakeVSC(endpoint_exists=False, index_exists=False)
    manager = VectorSearchManager(_dbx_settings(), client=vsc)

    index = manager.sync_index()

    assert vsc.endpoint_creates == ["vector-search-web-endpoint"]
    assert len(vsc.index_creates) == 1
    kwargs = vsc.index_creates[0]
    assert kwargs["primary_key"] == "id"
    assert kwargs["embedding_source_column"] == "text"
    assert kwargs["embedding_model_endpoint_name"] == "databricks-gte-large-en"
    assert kwargs["pipeline_type"] == "TRIGGERED"
    assert kwargs["source_table_name"] == "main.web_ingest.web_chunks"
    assert index.synced == 1
    assert index.waited_with == []


def test_manager_reuses_existing_index_and_waits():
    vsc = FakeVSC(endpoint_exists=True, index_exists=True)
    manager = VectorSearchManager(_dbx_settings(), client=vsc)

    manager.sync_index(wait=True)

    assert vsc.endpoint_creates == []
    assert vsc.index_creates == []
    assert vsc.index.synced == 1
    assert vsc.index.waited_with == [{"wait_for_updates": True}]
