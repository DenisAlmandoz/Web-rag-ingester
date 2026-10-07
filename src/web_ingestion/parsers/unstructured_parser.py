"""Unstructured parser (optional extra): element-level partitioning.

`partition` returns typed elements (Title, NarrativeText, Table, ListItem...),
which gives richer structure than flat text.
"""

import io

from ..models import FetchedDocument, ParsedDocument

ELEMENT_LEVELS = {"Title": 1, "Header": 1, "SubTitle": 2, "Heading": 2, "ListItem": 3}


class UnstructuredParser:
    name = "unstructured"
    supports_pdf = True
    supports_html = True

    def __init__(self, strategy: str = "auto"):
        from unstructured.partition.auto import partition

        self._partition = partition
        self.strategy = strategy

    def parse(self, doc: FetchedDocument) -> ParsedDocument:
        source = io.BytesIO(doc.content)
        suffix = ".pdf" if doc.is_pdf else ".html"

        elements = self._partition(
            file=source,
            content_type="application/pdf" if doc.is_pdf else "text/html",
            strategy=self.strategy,
            metadata_filename=f"page{suffix}",
        )

        parts: list[str] = []
        structure: list[dict] = []
        counts: dict[str, int] = {}

        for el in elements:
            kind = type(el).__name__
            counts[kind] = counts.get(kind, 0) + 1
            text = (getattr(el, "text", "") or "").strip()
            if not text:
                continue
            parts.append(text)
            if kind in ELEMENT_LEVELS:
                structure.append({"level": ELEMENT_LEVELS[kind], "title": text})

        title = next((s["title"] for s in structure if s["level"] == 1), doc.title_hint)
        return ParsedDocument(
            url=doc.url,
            parser=self.name,
            text="\n\n".join(parts),
            title=title,
            metadata={"element_counts": counts, "elements": len(elements)},
            structure=structure[:50],
        )
