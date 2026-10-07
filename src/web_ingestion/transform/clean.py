"""Text cleaning: turn raw parser output into stable, RAG-friendly text."""

import re
import unicodedata

BOILERPLATE_PATTERNS = [
    r"^\s*(cookie|cookies) (policy|notice|consent)s?\b.*$",
    r"^\s*accept (all )?cookies\b.*$",
    r"^\s*(subscribe|sign up) to (our|the) (newsletter|mailing list)\b.*$",
    r"^\s*(all|follow) rights reserved\b.*$",
    r"^\s*copyright\s+©?\s*\d{4}.*$",
    r"^\s*(skip to (main )?content|back to top|share (this|on)|tweet this)\b.*$",
    r"^\s*(log ?in|sign ?in|create an account|toggle (dark )?mode)\b.*$",
    r"^\s*(advertisement|sponsored (content|post))\b.*$",
    r"^\s*read more:\s*$",
]
_BOILERPLATE_RE = [re.compile(p, re.IGNORECASE) for p in BOILERPLATE_PATTERNS]

_URL_RE = re.compile(r"https?://\S+")
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")
_INLINE_NEWLINE_RE = re.compile(r"(?<![.!?:;])\n(?=\S)")


def clean_text(text: str, *, join_soft_wraps: bool = True, strip_urls: bool = False) -> str:
    """Normalize whitespace, drop boilerplate lines, stabilize unicode."""
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\xa0", " ")

    lines = []
    for line in text.split("\n"):
        line = _MULTI_SPACE_RE.sub(" ", line).strip()
        if not line:
            lines.append("")
            continue
        if _is_boilerplate(line):
            continue
        if strip_urls and _URL_RE.fullmatch(line):
            continue
        lines.append(line)

    cleaned = "\n".join(lines)
    if join_soft_wraps:
        # A newline not after sentence punctuation usually means a wrapped line
        cleaned = _INLINE_NEWLINE_RE.sub(" ", cleaned)

    cleaned = _MULTI_NEWLINE_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def dedupe_lines(text: str) -> str:
    """Remove repeated lines (menus, footers) while keeping order."""
    seen: set[str] = set()
    out = []
    for line in text.split("\n"):
        key = line.lower()
        if key and key in seen:
            continue
        seen.add(key)
        out.append(line)
    return "\n".join(out)


def _is_boilerplate(line: str) -> bool:
    if len(line) < 3:
        return False
    return any(pattern.search(line) for pattern in _BOILERPLATE_RE)
