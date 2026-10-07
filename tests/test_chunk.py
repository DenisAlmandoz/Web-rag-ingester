from web_ingestion.transform.chunk import chunk_text


def make_chunks(text, **kwargs):
    defaults = {"doc_id": "doc", "url": "https://x.test", "title": "T", "chunk_size": 200, "overlap": 40}
    defaults.update(kwargs)
    return chunk_text(text, **defaults)


def test_empty_text_gives_no_chunks():
    assert make_chunks("") == []


def test_short_text_is_single_chunk():
    chunks = make_chunks("Just one short paragraph.")
    assert len(chunks) == 1
    assert chunks[0].index == 0
    assert chunks[0].id == "doc::0"


def test_chunks_respect_size_budget():
    paragraphs = [f"Paragraph number {i} with a bit of filler text to make it non trivial." for i in range(40)]
    chunks = make_chunks("\n\n".join(paragraphs), chunk_size=300, overlap=60)
    assert len(chunks) > 3
    assert all(c.char_count <= 300 for c in chunks)


def test_chunk_ids_are_sequential_and_unique():
    paragraphs = [f"Paragraph {i}." for i in range(30)]
    chunks = make_chunks("\n\n".join(paragraphs), chunk_size=150, overlap=30)
    ids = [c.id for c in chunks]
    assert len(ids) == len(set(ids))
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_overlap_carries_tail_context():
    paragraphs = [("Sentence about retrieval quality. " * 3).strip() for _ in range(10)]
    chunks = make_chunks("\n\n".join(paragraphs), chunk_size=250, overlap=80)
    assert len(chunks) >= 2
    # tail of chunk N should reappear at the head of chunk N+1
    tail = chunks[0].text[-40:]
    assert tail in chunks[1].text


def test_oversized_paragraph_is_split():
    huge = "word " * 500
    chunks = make_chunks(huge, chunk_size=200, overlap=40)
    assert len(chunks) > 5
    assert all(c.char_count <= 200 for c in chunks)
