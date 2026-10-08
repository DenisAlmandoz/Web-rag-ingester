"""Sentence-aware chunking with overlap (no tokenizer needed).

Text is split into paragraphs, then into sentences. Sentences are packed into
window-sized chunks, so a chunk boundary never cuts mid-sentence. The only
exception is a single sentence longer than the whole budget: it is split on
word boundaries as a best effort. Every chunk is self-contained: the page
title is prepended (as a heading) so each vector embedding carries context.
"""

import re

from ..models import Chunk

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'#(])")


def split_sentences(text: str) -> list[str]:
    """Paragraphs -> sentences. Joining with a single space keeps them usable."""
    sentences: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        for part in _SENTENCE_SPLIT.split(block):
            part = part.strip()
            if part:
                sentences.append(part)
    return sentences


def chunk_text(
    text: str,
    *,
    doc_id: str,
    url: str,
    title: str,
    chunk_size: int = 1200,
    overlap: int = 200,
    prefix_heading: bool = True,
) -> list[Chunk]:
    if not text.strip():
        return []
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    overlap = max(0, min(overlap, chunk_size // 2))

    heading = f"# {title}\n\n" if (prefix_heading and title) else ""
    budget = max(10, chunk_size - len(heading))

    sentences = split_sentences(text)
    chunks: list[Chunk] = []
    index = 0

    def emit(body: str) -> None:
        """Append one chunk carrying the title heading for embedding context."""
        nonlocal index
        text_body = heading + body
        chunks.append(
            Chunk(
                id=f"{doc_id}::{index}",
                doc_id=doc_id,
                url=url,
                title=title,
                index=index,
                text=text_body,
                char_count=len(text_body),
                approx_tokens=max(1, len(text_body) // 4),
            )
        )
        index += 1

    def emit_word_split(sentence: str) -> None:
        """Degenerate case: a sentence longer than the budget. Split on word
        boundaries only, carrying the previous window's tail as overlap."""
        window = max(1, budget - overlap - 1)
        segments: list[str] = []
        current = ""
        for word in sentence.split():
            candidate = f"{current} {word}" if current else word
            if len(candidate) <= window:
                current = candidate
            else:
                if current:
                    segments.append(current)
                current = word
        if current:
            segments.append(current)
        tail = ""
        for segment in segments:
            body = f"{tail} {segment}" if tail else segment
            emit(body)
            tail = body[-overlap:]
            cut = tail.find(" ")
            if cut > 0:
                tail = tail[cut + 1 :]

    def carry_text(body_sentences: list[str]) -> str:
        """Trailing whole sentences of a finished chunk, re-used at the head of
        the next chunk so the overlap region never starts mid-sentence."""
        kept: list[str] = []
        length = 0
        for sentence in reversed(body_sentences):
            if kept and length + len(sentence) >= overlap:
                kept.append(sentence)
                break
            kept.append(sentence)
            length += len(sentence)
        return " ".join(reversed(kept)) if kept else ""

    body_sentences: list[str] = []
    i = 0
    while i < len(sentences):
        sentence = sentences[i]
        if not body_sentences:
            if len(heading) + len(sentence) <= chunk_size:
                body_sentences.append(sentence)
                i += 1
                continue
            emit_word_split(sentence)
            i += 1
            continue

        candidate = f"{' '.join(body_sentences)} {sentence}"
        if len(heading) + len(candidate) <= chunk_size:
            body_sentences.append(sentence)
            i += 1
            continue

        emit(" ".join(body_sentences))
        carry = carry_text(body_sentences)
        if len(heading) + len(sentence) > chunk_size:
            body_sentences = []
            continue
        if carry and len(heading) + len(carry) + 1 + len(sentence) <= chunk_size:
            body_sentences = [carry, sentence]
        else:
            body_sentences = [sentence]
        i += 1

    if body_sentences:
        emit(" ".join(body_sentences))

    return chunks