"""Baseline HTML -> text parser using BeautifulSoup.

Zero heavy dependencies. Strategy:
  1. drop <script>/<style>/<nav>/<header>/<footer>/<aside>/<form>/<svg>
  2. prefer <article>/<main> when present (page body, not page chrome)
  3. keep block-level boundaries as newlines so paragraphs survive
  4. keep <title> and meta description as document metadata
"""

import re

from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag

from ..models import FetchedDocument, ParsedDocument

DROP_TAGS = {"script", "style", "noscript", "svg", "iframe", "form", "button", "input"}
BLOCK_TAGS = {
    "p", "div", "section", "article", "main", "li", "ul", "ol", "table", "tr",
    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "br", "hr",
}
SKIP_CONTENT_TAGS = {"nav", "header", "footer", "aside", "form"}


class BaselineParser:
    name = "baseline"
    supports_pdf = False
    supports_html = True

    def parse(self, doc: FetchedDocument) -> ParsedDocument:
        if doc.is_pdf:
            return ParsedDocument(
                url=doc.url,
                parser=self.name,
                warnings=[f"{self.name} parser cannot read PDFs; install the docling extra"],
            )

        soup = BeautifulSoup(doc.text, "lxml")

        title = doc.title_hint
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        description = ""
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and isinstance(meta, Tag):
            description = str(meta.get("content", "")).strip()

        for tag in soup(DROP_TAGS):
            tag.decompose()

        root = soup.find("article") or soup.find("main") or soup.body or soup
        raw = self._walk(root)
        text = self._normalize(raw)

        structure = []
        if isinstance(root, Tag):
            structure = [
                {"level": int(h.name[1]), "title": h.get_text(" ", strip=True)}
                for h in root.find_all(["h1", "h2", "h3"])
                if h.get_text(strip=True)
            ][:50]

        return ParsedDocument(
            url=doc.url,
            parser=self.name,
            text=text,
            title=title or doc.title_hint,
            metadata={"description": description},
            structure=structure,
        )

    def _walk(self, node) -> str:
        if isinstance(node, NavigableString):
            return str(node)
        if not isinstance(node, Tag):
            return ""
        if node.name in SKIP_CONTENT_TAGS:
            return ""
        inner = "".join(self._walk(child) for child in node.children)
        if node.name in BLOCK_TAGS:
            return f"\n{inner}\n"
        return inner

    @staticmethod
    def _normalize(raw: str) -> str:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
        joined = "\n".join(lines)
        joined = re.sub(r" +\n", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return joined.strip()
