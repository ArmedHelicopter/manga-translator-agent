"""Tests for mga.format.novel_epub — NovelEPUBAdapter."""

import zipfile
from pathlib import Path

from mga.format.novel_epub import NovelEPUBAdapter, _extract_text_from_xhtml, _split_into_chunks


def _make_simple_epub(tmp_path: Path) -> Path:
    """Create a minimal valid EPUB with one chapter."""
    epub_path = tmp_path / "test.epub"
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""")
        zf.writestr("OEBPS/content.opf", """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>Test</dc:title>
  <dc:language>ja</dc:language>
  <dc:identifier id="uid">test-epub</dc:identifier>
</metadata>
<manifest>
  <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine>
  <itemref idref="ch1"/>
</spine>
</package>""")
        zf.writestr("OEBPS/chapter1.xhtml", """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter 1</title></head>
<body>
<h1>第一章</h1>
<p>太郎が学校に行った。</p>
<p>花子は家で本を読んでいた。</p>
</body>
</html>""")
    return epub_path


def test_extract_text_from_xhtml():
    xhtml = b'<html><body><p>Hello</p><p>World</p></body></html>'
    text = _extract_text_from_xhtml(xhtml)
    assert "Hello" in text
    assert "World" in text


def test_extract_text_skips_script():
    xhtml = b'<html><body><script>var x=1;</script><p>Visible text</p></body></html>'
    text = _extract_text_from_xhtml(xhtml)
    assert "Visible text" in text
    assert "var x" not in text


def test_split_into_chunks():
    text = "Line 1\n\nLine 2\n\nLine 3"
    # Each line is ~6 chars; max_chars=8 forces each into its own chunk
    chunks = _split_into_chunks(text, max_chars=8)
    assert len(chunks) >= 2


def test_extract_epub(tmp_path):
    epub_path = _make_simple_epub(tmp_path)
    adapter = NovelEPUBAdapter()
    pages = list(adapter.extract(epub_path))
    assert len(pages) >= 1
    assert pages[0].metadata["mode"] == "novel"
    assert "xhtml_entry" in pages[0].metadata


def test_extract_nonexistent_epub():
    adapter = NovelEPUBAdapter()
    try:
        list(adapter.extract(Path("/nonexistent.epub")))
        assert False, "Should have raised"
    except FileNotFoundError:
        pass


def test_repack_epub_fallback(tmp_path):
    """Test repack when original EPUB path is unavailable (fallback mode)."""
    from mga.models import TranslatedPage

    adapter = NovelEPUBAdapter()
    output = tmp_path / "output.epub"
    pages = [
        TranslatedPage(index=0, page_json={
            "translated_text": "太郎去了学校。",
            "chapter_title": "第一章",
            "xhtml_entry": "OEBPS/chapter1.xhtml",
            "chunk_index": 0,
        }),
    ]
    adapter.repack(iter(pages), output)
    assert output.exists()
    with zipfile.ZipFile(output) as zf:
        assert "mimetype" in zf.namelist()
        assert any("content.opf" in n for n in zf.namelist())
