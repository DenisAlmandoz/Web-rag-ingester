"""Paragraph-aware character chunking with overlap (no tokenizer needed)."""

import re

from ..models import Chunk


def chunk_text(
    text: str,
    *,
    doc_id: str,
    url: str,
    title: str,
    chunk_size: int = 1200,
    overlap: int = 200,
) -> list[Chunk]:
    if not text.strip():
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    overlap = max(0, min(overlap, chunk_size // 2))

    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]

    chunks: list[Chunk] = []
    current = ""
    index = 0

    def emit(body: str) -> None:
        nonlocal index
        chunks.append(
            Chunk(
                id=f"{doc_id}::{index}",
                doc_id=doc_id,
                url=url,
                title=title,
                index=index,
                text=body,
                char_count=len(body),
                approx_tokens=max(1, len(body) // 4),
            )
        )
        index += 1

    for para in paragraphs:
        # A single paragraph longer than the window gets split with overlap
        if len(para) > chunk_size:
            if current.strip():
                emit(current.strip())
                current = ""
            start = 0
            while start < len(para):
                end = min(start + chunk_size, len(para))
                emit(para[start:end])
                if end == len(para):
                    break
                start = max(end - overlap, start + 1)
            continue

        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n{para}".strip() if current else para
            continue

        if current.strip():
            emit(current.strip())
        tail = chunks[-1].text[-overlap:] if (overlap and chunks) else ""
        current = f"{tail}\n{para}" if tail and len(tail) + 1 + len(para) <= chunk_size else para

    if current.strip():
        emit(current.strip())

    return chunks
