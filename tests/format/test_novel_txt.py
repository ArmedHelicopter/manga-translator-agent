"""Tests for mga.format.novel_txt — NovelTXTAdapter."""

from pathlib import Path

from mga.format.novel_txt import NovelTXTAdapter, _split_into_chunks


def test_split_single_paragraph():
    chunks = _split_into_chunks("Hello world", max_chars=100)
    assert chunks == ["Hello world"]


def test_split_multiple_paragraphs():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    # Each paragraph is ~17 chars; max_chars=20 forces each into its own chunk
    chunks = _split_into_chunks(text, max_chars=20)
    assert len(chunks) == 3


def test_split_long_paragraph_at_sentence_boundary():
    # Paragraph > max_chars, split at sentence boundary
    text = "This is sentence one. This is sentence two. This is sentence three."
    chunks = _split_into_chunks(text, max_chars=30)
    assert len(chunks) >= 2
    # Each chunk should be <= max_chars (approximately, sentences aren't splittable)
    for chunk in chunks:
        assert len(chunk) <= 60  # Allow some slack for unsplitable sentences


def test_split_empty_text():
    chunks = _split_into_chunks("", max_chars=100)
    assert chunks == [""]


def test_extract_txt_file(tmp_path):
    txt = tmp_path / "novel.txt"
    txt.write_text("Chapter 1\n\nFirst paragraph.\n\nSecond paragraph.", encoding="utf-8")

    adapter = NovelTXTAdapter()
    pages = list(adapter.extract(txt))
    assert len(pages) >= 1
    assert pages[0].metadata["mode"] == "novel"
    assert "Chapter 1" in pages[0].metadata["chapter_text"]


def test_extract_nonexistent_file():
    adapter = NovelTXTAdapter()
    try:
        list(adapter.extract(Path("/nonexistent.txt")))
        assert False, "Should have raised"
    except FileNotFoundError:
        pass


def test_repack_txt(tmp_path):
    from mga.models import TranslatedPage

    adapter = NovelTXTAdapter()
    output = tmp_path / "translated.txt"
    pages = [
        TranslatedPage(index=0, page_json={"translated_text": "翻译第一段"}),
        TranslatedPage(index=1, page_json={"translated_text": "翻译第二段"}),
    ]
    adapter.repack(iter(pages), output)
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert "翻译第一段" in content
    assert "翻译第二段" in content


def test_extract_large_txt_splits(tmp_path):
    txt = tmp_path / "long.txt"
    # Create a file with many long paragraphs
    paragraphs = ["这是一个段落。" * 50 for _ in range(5)]
    txt.write_text("\n\n".join(paragraphs), encoding="utf-8")

    adapter = NovelTXTAdapter()
    pages = list(adapter.extract(txt))
    # 5 paragraphs of ~250 chars each, max_chars=500 -> at least 3 chunks
    assert len(pages) >= 3
