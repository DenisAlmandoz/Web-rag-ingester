"""Optional parser adapters.

Each adapter imports its library lazily so the core pipeline installs and
runs without heavyweight extras. `unavailable_reason()` explains what to run.
"""

from __future__ import annotations

import importlib


def _module_available(name: str) -> bool:
    try:
        importlib.import_module(name)
        return True
    except Exception:  # noqa: BLE001 - import may fail for many reasons; we only care if it succeeds
        return False


AVAILABLE = {
    "baseline": ("web_ingestion.parsers.baseline", "built in (beautifulsoup4)"),
    "trafilatura": ("trafilatura", "uv sync --extra trafilatura"),
    "docling": ("docling", "uv sync --extra docling  (heavy: downloads models)"),
    "unstructured": ("unstructured", "uv sync --extra unstructured"),
}


def available_parsers() -> dict[str, bool]:
    return {name: _module_available(module) for name, (module, _) in AVAILABLE.items()}


def unavailable_reason(name: str) -> str | None:
    module, hint = AVAILABLE[name]
    if _module_available(module):
        return None
    return f"{name} is not installed -> run: {hint}"
