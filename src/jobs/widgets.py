"""Databricks notebook widgets (bundle `base_parameters`) for the job classes."""

from __future__ import annotations

import os

# Set on every Databricks cluster/job runtime. Importing databricks.sdk.runtime
# materializes the runtime user namespace and can hang outside a cluster, so only
# attempt it when we are actually running on Databricks.
ON_DATABRICKS = bool(os.environ.get("DATABRICKS_RUNTIME_VERSION"))


def widget(name: str, default: str = "") -> str:
    """Read a job widget; falls back to `default` outside a Databricks job (tests, local runs)."""
    if not ON_DATABRICKS:
        return default
    try:
        from databricks.sdk.runtime import dbutils  # type: ignore[import-not-found]

        return dbutils.widgets.get(name) or default
    except Exception:  # noqa: BLE001 - widget may be unset or dbutils unavailable
        return default
