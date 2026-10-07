from ..models import ParserName
from .availability import available_parsers, unavailable_reason
from .base import Parser, timed_parse

__all__ = ["Parser", "available_parsers", "get_parser", "timed_parse", "unavailable_reason"]


def get_parser(name: ParserName | str, **kwargs) -> Parser | None:
    """Instantiate a parser by name; returns None if its extra is not installed."""
    if unavailable_reason(name):
        return None

    if name == "baseline":
        from .baseline import BaselineParser

        return BaselineParser(**kwargs)
    if name == "trafilatura":
        from .trafilatura_parser import TrafilaturaParser

        return TrafilaturaParser(**kwargs)
    if name == "docling":
        from .docling_parser import DoclingParser

        return DoclingParser(**kwargs)
    if name == "unstructured":
        from .unstructured_parser import UnstructuredParser

        return UnstructuredParser(**kwargs)
    raise ValueError(f"Unknown parser: {name}. Choose from {list(available_parsers())}")
