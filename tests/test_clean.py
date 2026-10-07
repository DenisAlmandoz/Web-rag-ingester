from web_ingestion.transform.clean import clean_text, dedupe_lines


def test_collapses_whitespace_and_wraps():
    raw = "Line one   with    spaces\nand a soft wrapped line"
    out = clean_text(raw)
    assert "  " not in out
    assert "line one with spaces and a soft wrapped line" in out.lower()


def test_drops_boilerplate_lines():
    raw = (
        "Real content sentence.\n"
        "Accept all cookies to continue.\n"
        "Copyright © 2026 Example. All rights reserved.\n"
        "Subscribe to our newsletter\n"
        "Skip to main content\n"
        "Another real sentence."
    )
    out = clean_text(raw)
    assert "Real content sentence." in out
    assert "Another real sentence." in out
    assert "cookies" not in out.lower()
    assert "copyright" not in out.lower()
    assert "newsletter" not in out.lower()


def test_normalizes_unicode_and_nbsp():
    out = clean_text("caf\xa0xa\u00a0here")
    assert "\xa0" not in out
    assert "caf" in out


def test_keeps_sentence_newlines_but_collapses_blank_runs():
    raw = "First sentence.\nSecond sentence.\n\n\n\n\nThird sentence."
    out = clean_text(raw)
    assert "\n\n\n" not in out
    assert "First sentence.\nSecond sentence." in out


def test_dedupe_lines_removes_repeats():
    raw = "Docs\nIngestion\nDocs\nReal\nReal"
    out = dedupe_lines(raw)
    assert out.splitlines().count("Docs") == 1
    assert out.splitlines().count("Real") == 1


def test_empty_input():
    assert clean_text("") == ""
