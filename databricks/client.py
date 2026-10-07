"""Shared Databricks auth for the `index` command.

Settings are loaded from `.env` by pydantic, but the Databricks SDK only reads
`os.environ`, so mirror the service-principal values onto the environment first.
When they are absent the SDK falls back to its normal chain (`~/.databrickscfg`,
`databricks` CLI, VS Code extension).
"""

from __future__ import annotations

import os

from ..web_ingestion.config import Settings


def configure_env(settings: Settings) -> None:
    for key, value in (
        ("DATABRICKS_HOST", settings.databricks_host),
        ("DATABRICKS_CLIENT_ID", settings.databricks_client_id),
        ("DATABRICKS_CLIENT_SECRET", settings.databricks_client_secret),
    ):
        if value:
            os.environ[key] = value


def workspace_client(settings: Settings):
    configure_env(settings)
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient()
