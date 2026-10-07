import logging
from pathlib import Path

import httpx

from ..config import FIXTURES_DIR, Settings
from ..models import FetchedDocument

logger = logging.getLogger(__name__)


class HttpFetcher:
    """Downloads a URL into a FetchedDocument.

    Mock-mode results carry a `fixture_path`; those are read from disk instead
    of the network so the pipeline is fully testable offline.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch(self, url: str, fixture_path: str | None = None) -> FetchedDocument:
        if fixture_path:
            return self._fetch_fixture(url, fixture_path)
        if url.startswith("fixture:"):
            return self._fetch_fixture(url, self._resolve_fixture_ref(url.split(":", 1)[1]))

        logger.info("Fetching %s", url)
        with httpx.Client(
            timeout=self.settings.fetch_timeout,
            follow_redirects=True,
            headers={"User-Agent": self.settings.user_agent},
        ) as client:
            response = client.get(url)
            response.raise_for_status()

            content = response.content
            if len(content) > self.settings.max_fetch_bytes:
                logger.warning("Truncating %s from %d to %d bytes", url, len(content), self.settings.max_fetch_bytes)
                content = content[: self.settings.max_fetch_bytes]

            content_type = response.headers.get("content-type", "text/html").split(";")[0].strip()
            return FetchedDocument(
                url=str(response.url),
                content_type=content_type,
                status_code=response.status_code,
                content=content,
                is_pdf=content_type == "application/pdf" or content[:5] == b"%PDF-",
            )

    def _fetch_fixture(self, url: str, fixture_path: str) -> FetchedDocument:
        path = FIXTURES_DIR / fixture_path
        if not path.exists():
            raise FileNotFoundError(f"Fixture not found: {path}")
        content = path.read_bytes()
        is_pdf = path.suffix.lower() == ".pdf" or content[:5] == b"%PDF-"
        return FetchedDocument(
            url=url,
            content_type="application/pdf" if is_pdf else "text/html",
            content=content,
            is_pdf=is_pdf,
        )

    def _resolve_fixture_ref(self, ref: str) -> str:
        """Map `fixture:<name>` to a pages/<name>.html file (or use a path as-is)."""
        if "/" in ref or ref.endswith((".html", ".pdf")):
            return ref
        candidates = sorted((FIXTURES_DIR / "pages").glob(f"{ref}.*"))
        if candidates:
            return str(candidates[0].relative_to(FIXTURES_DIR))
        raise FileNotFoundError(f"No fixture page named {ref!r}")


def save_raw(doc: FetchedDocument, out_dir: Path) -> Path:
    """Persist the raw payload so every later step is reproducible."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = ".pdf" if doc.is_pdf else ".html"
    slug = _slugify(doc.url)
    path = out_dir / f"{slug}{ext}"
    path.write_bytes(doc.content)
    return path


def _slugify(value: str, max_len: int = 60) -> str:
    keep = [c if c.isalnum() else "-" for c in value]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-").lower()[:max_len] or "page"
