"""Docling parser (optional extra): PDF *and* HTML -> structured text.

Same idea as in the course repo: keep sections, raw text, table/figure counts.
"""

import tempfile
from pathlib import Path

from ..models import FetchedDocument, ParsedDocument


class DoclingParser:
    name = "docling"
    supports_pdf = True
    supports_html = True

    def __init__(self, max_pages: int = 30, do_ocr: bool = False, do_table_structure: bool = True):
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption

        pipeline_options = PdfPipelineOptions(do_table_structure=do_table_structure, do_ocr=do_ocr)
        self._converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )
        self.max_pages = max_pages
        self._input_format = InputFormat

    def parse(self, doc: FetchedDocument) -> ParsedDocument:
        suffix = ".pdf" if doc.is_pdf else ".html"
        warnings: list[str] = []

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(doc.content)
            tmp_path = Path(tmp.name)

        try:
            result = self._converter.convert(str(tmp_path), max_num_pages=self.max_pages)
            ddoc = result.document

            sections = []
            for element in ddoc.texts:
                label = getattr(element, "label", "")
                if str(label).lower() in {"title", "section_header"}:
                    sections.append({"level": 1, "title": element.text.strip()})

            tables = len(list(ddoc.tables))
            figures = len(list(getattr(ddoc, "figures", []) or []))
            metadata = {"tables": tables, "figures": figures}

            text = ddoc.export_to_text()
            if not text.strip():
                warnings.append("docling returned empty text")

            title = ""
            if ddoc.name:
                title = str(ddoc.name)
            elif sections:
                title = sections[0]["title"]

            return ParsedDocument(
                url=doc.url,
                parser=self.name,
                text=text,
                title=title or doc.title_hint,
                metadata=metadata,
                structure=sections[:50],
                warnings=warnings,
            )
        finally:
            tmp_path.unlink(missing_ok=True)
