"""Trafilatura parser: focused on main-content extraction from HTML."""

from ..models import FetchedDocument, ParsedDocument


class TrafilaturaParser:
    name = "trafilatura"
    supports_pdf = False
    supports_html = True

    def __init__(self):
        import trafilatura

        self._trafilatura = trafilatura

    def parse(self, doc: FetchedDocument) -> ParsedDocument:
        if doc.is_pdf:
            return ParsedDocument(
                url=doc.url,
                parser=self.name,
                warnings=[f"{self.name} parser targets HTML; use docling/unstructured for PDFs"],
            )

        html = doc.text
        # Markdown output keeps headings/lists/tables as lightweight structure
        markdown = self._trafilatura.extract(
            html,
            output_format="markdown",
            include_comments=False,
            include_tables=True,
            favor_precision=True,
            url=doc.url,
        )
        plain = self._trafilatura.extract(html, include_comments=False, favor_precision=True, url=doc.url) or ""
        metadata = {}
        meta = self._trafilatura.bare_extraction(html, with_metadata=True, url=doc.url)
        if meta:
            raw_meta = getattr(meta, "as_dict", None)
            if callable(raw_meta):
                raw_meta = raw_meta()
            elif isinstance(meta, dict):
                raw_meta = meta
            else:
                raw_meta = {}
            for k, v in raw_meta.items():
                if isinstance(v, (str, int, float, bool)) and v not in ("", None):
                    metadata[k] = v

        warnings = []
        text = markdown or plain
        if not text:
            warnings.append("trafilatura found no main content")

        return ParsedDocument(
            url=doc.url,
            parser=self.name,
            text=text or "",
            title=str(metadata.get("title") or doc.title_hint or ""),
            metadata=metadata,
            structure=[{"level": 1, "title": t} for t in _headings(text or "")],
            warnings=warnings,
        )


def _headings(markdown: str) -> list[str]:
    return [line.lstrip("# ").strip() for line in markdown.splitlines() if line.startswith("#")]
