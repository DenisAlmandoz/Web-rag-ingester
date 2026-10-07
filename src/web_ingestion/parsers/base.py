import time
from typing import Protocol

from ..models import FetchedDocument, ParsedDocument


class Parser(Protocol):
    name: str
    supports_pdf: bool
    supports_html: bool

    def parse(self, doc: FetchedDocument) -> ParsedDocument: ...


def timed_parse(parser, doc: FetchedDocument) -> ParsedDocument:
    """Run a parser and stamp wall-clock time + shared metadata on the result."""
    start = time.perf_counter()
    parsed = parser.parse(doc)
    parsed.parse_seconds = time.perf_counter() - start
    parsed.url = doc.url
    parsed.parser = parser.name
    return parsed
