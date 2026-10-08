# Databricks notebook source
from jobs import WebIngestion, WebIngestionConfig

# Prefer the direct lookup: `{{secrets/...}}` references in base_parameters are
# resolved by the Jobs service and may silently pass through the literal string
# for environment-based tasks. dbutils.secrets.get raises loudly if it fails.
try:
    tavily_api_key = dbutils.secrets.get(scope="web-ingest", key="tavily_api_key")
except Exception as exc:  # noqa: BLE001 - scope/key may be missing in a fresh workspace
    print(f"Ignoring tavily secret lookup failure: {exc}")
    tavily_api_key = None

config = WebIngestionConfig.from_widgets()
if not config.tavily_api_key or config.tavily_api_key.startswith("{{secrets/"):
    config.tavily_api_key = tavily_api_key or config.tavily_api_key

WebIngestion(config).run()