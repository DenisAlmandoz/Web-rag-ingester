from types import SimpleNamespace

from jobs import VectorIndex, VectorIndexConfig, WebIngestion, WebIngestionConfig
from jobs import vector_index as vector_index_module
from jobs import web_ingestion as web_ingestion_module
from jobs.widgets import widget


class FakeStatementExecution:
    """Returns rows for SELECTs, plain success for DDL/DML."""

    def __init__(self, columns=None, rows=None):
        self.columns = columns or []
        self.rows = rows or []
        self.statements = []

    def execute_statement(self, **kwargs):
        self.statements.append(kwargs["statement"])
        status = SimpleNamespace(state=SimpleNamespace(name="SUCCEEDED"), error=None, sql_state=None)
        if kwargs["statement"].lstrip().upper().startswith("SELECT"):
            manifest = SimpleNamespace(schema=[SimpleNamespace(name=name) for name in self.columns])
            result = SimpleNamespace(manifest=manifest, data_array=[list(row) for row in self.rows])
            return SimpleNamespace(status=status, result=result)
        return SimpleNamespace(status=status)


class FakeIndex:
    def __init__(self):
        self.synced = 0
        self.waited_with = []

    def sync(self):
        self.synced += 1

    def wait_until_ready(self, **kwargs):
        self.waited_with.append(kwargs)


class FakeVSC:
    def __init__(self):
        self.index = FakeIndex()
        self.endpoint_creates = []
        self.index_creates = []

    def endpoint_exists(self, name):
        return True

    def create_endpoint_and_wait(self, name, **kwargs):
        self.endpoint_creates.append(name)

    def index_exists(self, endpoint_name=None, index_name=None):
        return False

    def get_index(self, endpoint_name=None, index_name=None):
        return self.index

    def create_delta_sync_index(self, **kwargs):
        self.index_creates.append(kwargs)
        return self.index


def _widgets(values):
    return lambda name, default="": values.get(name, default)


def test_widget_returns_default_outside_databricks():
    assert widget("definitely_not_a_widget", "fallback") == "fallback"


def test_web_ingestion_config_defaults():
    settings = WebIngestionConfig().to_settings()

    assert settings.databricks_catalog == "main"
    assert settings.databricks_schema == "web_ingest"
    assert str(settings.output_dir).endswith("web-ingestion")


def test_web_ingestion_config_from_widgets(monkeypatch):
    monkeypatch.setattr(
        web_ingestion_module,
        "widget",
        _widgets(
            {
                "query": "chunking strategies",
                "parser": "baseline",
                "max_results": "7",
                "catalog": "prod",
                "schema": "ingest",
                "databricks_host": "https://host",
                "databricks_warehouse_id": "wh123",
                "tavily_api_key": "secret",
                "output_dir": "/tmp/runs",
            }
        ),
    )

    config = WebIngestionConfig.from_widgets()
    settings = config.to_settings()

    assert config.query == "chunking strategies"
    assert config.max_results == 7
    assert config.schema_name == "ingest"
    assert settings.databricks_catalog == "prod"
    assert settings.databricks_warehouse_id == "wh123"
    assert settings.tavily_api_key == "secret"
    assert str(settings.output_dir) == "/tmp/runs"


def test_web_ingestion_extract_and_transform(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    job = WebIngestion(WebIngestionConfig(query="attention is all you need", output_dir=tmp_path))

    assert job.settings.tavily_api_key == ""

    result = job.extract()
    data = job.transform(result)

    assert data.run_id == result.run_id
    assert len(data.documents) == len(result.records) > 0
    assert len(data.chunks) == result.total_chunks > 0
    assert all(row.get("id") and row.get("text") for row in data.chunks)


def test_web_ingestion_run_merges_delta_tables(tmp_path, monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "")
    fake = FakeStatementExecution()
    config = WebIngestionConfig(query="attention is all you need", output_dir=tmp_path)
    job = WebIngestion(config, client=SimpleNamespace(statement_execution=fake))

    written = job.run()

    assert written > 0
    merges = [s for s in fake.statements if s.startswith("MERGE INTO")]
    assert len(merges) == 2
    assert any(".web_chunks " in s for s in merges)
    assert any(".web_documents " in s for s in merges)
    assert any(s.startswith("CREATE TABLE IF NOT EXISTS") for s in fake.statements)
    assert not any(s.lstrip().upper().startswith("SELECT") for s in fake.statements)


def test_vector_index_config_defaults():
    settings = VectorIndexConfig().to_settings()

    assert settings.databricks_catalog == "main"
    assert settings.databricks_table == "web_chunks"
    assert settings.databricks_endpoint_name == "vector-search-web-endpoint"
    assert settings.databricks_index_name == "web_chunks_index"
    assert settings.databricks_embedding_model == "databricks-gte-large-en"


def test_vector_index_config_from_widgets(monkeypatch):
    monkeypatch.setattr(
        vector_index_module,
        "widget",
        _widgets(
            {
                "catalog": "prod",
                "schema": "ingest",
                "chunks_table": "chunks",
                "vs_endpoint_name": "ep",
                "vs_index_name": "idx",
                "embedding_model": "model",
                "databricks_host": "https://host",
                "databricks_warehouse_id": "wh123",
            }
        ),
    )

    config = VectorIndexConfig.from_widgets()
    settings = config.to_settings()

    assert config.catalog == "prod"
    assert config.chunks_table == "chunks"
    assert settings.databricks_endpoint_name == "ep"
    assert settings.databricks_index_name == "idx"
    assert settings.databricks_host == "https://host"
    assert settings.databricks_warehouse_id == "wh123"


def test_vector_index_transform_keeps_index_contract_rows():
    job = VectorIndex(VectorIndexConfig())
    rows = [
        {"id": "a::0", "text": "hello"},
        {"id": "b::0", "text": ""},
        {"id": "", "text": "orphan"},
        {"text": "missing id"},
        {"id": "c::0"},
        {"id": "d::0", "text": "world"},
    ]

    assert job.transform(rows) == [
        {"id": "a::0", "text": "hello"},
        {"id": "d::0", "text": "world"},
    ]


def test_vector_index_run_extracts_and_syncs_index():
    fake = FakeStatementExecution(
        columns=["id", "text", "url"],
        rows=[["a::0", "hello", "https://x"], ["b::0", "", "https://y"], ["c::0", "world", "https://z"]],
    )
    vsc = FakeVSC()
    config = VectorIndexConfig(databricks_host="https://host", databricks_warehouse_id="wh123")
    job = VectorIndex(config, client=SimpleNamespace(statement_execution=fake), vsc=vsc)

    index = job.run()

    selects = [s for s in fake.statements if s.startswith("SELECT * FROM")]
    assert selects == ["SELECT * FROM main.web_ingest.web_chunks"]

    assert len(vsc.index_creates) == 1
    kwargs = vsc.index_creates[0]
    assert kwargs["primary_key"] == "id"
    assert kwargs["embedding_source_column"] == "text"
    assert kwargs["pipeline_type"] == "TRIGGERED"
    assert kwargs["source_table_name"] == "main.web_ingest.web_chunks"
    assert kwargs["embedding_model_endpoint_name"] == "databricks-gte-large-en"

    assert index.synced == 1
    assert index.waited_with == [{}, {"wait_for_updates": True}]
