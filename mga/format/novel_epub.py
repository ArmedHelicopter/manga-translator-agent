"""Novel EPUB adapter — extracts text from EPUB chapters, preserves full structure."""

from __future__ import annotations

import re
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterator

from ..models.format import PageRef, TranslatedPage
from .base import FormatAdapter


class _TextExtractor(HTMLParser):
    """Extract visible text from XHTML, collapsing whitespace."""

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._skip = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False
        if tag in ("p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = "".join(self._parts)
        lines = [line.strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def _extract_text_from_xhtml(xhtml_bytes: bytes) -> str:
    """Parse XHTML and return visible text."""
    try:
        content = xhtml_bytes.decode("utf-8")
    except UnicodeDecodeError:
        content = xhtml_bytes.decode("latin-1")
    extractor = _TextExtractor()
    extractor.feed(content)
    return extractor.get_text()


def _find_opf_path(zf: zipfile.ZipFile) -> str | None:
    """Find the OPF manifest path from META-INF/container.xml."""
    container_entry = "META-INF/container.xml"
    if container_entry not in zf.namelist():
        return None
    container_xml = zf.read(container_entry).decode("utf-8")
    match = re.search(r'full-path="([^"]+\.opf)"', container_xml)
    return match.group(1) if match else None


def _parse_opf_spine(zf: zipfile.ZipFile, opf_path: str) -> list[str]:
    """Parse OPF manifest and return ordered list of XHTML chapter entries."""
    opf_dir = str(Path(opf_path).parent)
    opf_xml = zf.read(opf_path).decode("utf-8")

    # Extract item id->href mapping
    items: dict[str, str] = {}
    for m in re.finditer(r'<item\s+id="([^"]+)"[^>]+href="([^"]+)"', opf_xml):
        items[m.group(1)] = m.group(2)

    # Extract spine order
    spine_refs: list[str] = []
    for m in re.finditer(r'<itemref\s+idref="([^"]+)"', opf_xml):
        ref = m.group(1)
        if ref in items:
            href = items[ref]
            full_path = f"{opf_dir}/{href}" if opf_dir != "." else href
            spine_refs.append(full_path)

    return spine_refs


def _split_into_chunks(text: str, max_chars: int = 500) -> list[str]:
    """Split text into chunks at paragraph/sentence boundaries."""
    paragraphs = text.split("\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 1 <= max_chars:
            current = f"{current}\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            if len(para) <= max_chars:
                current = para
            else:
                # Split long paragraph at sentence boundaries
                sentences = re.split(r"(?<=[。！？.!?])\s*", para)
                current = ""
                for sent in sentences:
                    if len(current) + len(sent) + 1 <= max_chars:
                        current = f"{current} {sent}" if current else sent
                    else:
                        if current:
                            chunks.append(current)
                        current = sent
    if current:
        chunks.append(current)
    return chunks if chunks else [""]


class NovelEPUBAdapter(FormatAdapter):
    """Adapter for translating text content in EPUB files.

    Extracts text from XHTML chapters, preserving the full EPUB structure
    for repacking with translated text.
    """

    def extract(self, input_path: Path) -> Iterator[PageRef]:
        if not input_path.is_file():
            raise FileNotFoundError(f"Input path is not a file: {input_path}")

        with zipfile.ZipFile(input_path, "r") as zf:
            opf_path = _find_opf_path(zf)
            if opf_path is None:
                # Fallback: find all .xhtml/.html files
                chapter_entries = sorted(
                    [n for n in zf.namelist() if Path(n).suffix in (".xhtml", ".html", ".htm")],
                )
            else:
                chapter_entries = _parse_opf_spine(zf, opf_path)

            idx = 0
            for entry in chapter_entries:
                if entry not in zf.namelist():
                    continue
                raw = zf.read(entry)
                text = _extract_text_from_xhtml(raw)
                if not text.strip():
                    continue

                # Extract chapter title from first heading or filename
                title = Path(entry).stem.replace("_", " ").replace("-", " ")
                for m in re.finditer(r"<h[1-6][^>]*>([^<]+)</h[1-6]>", raw.decode("utf-8", errors="replace")):
                    title = m.group(1).strip()
                    break

                chunks = _split_into_chunks(text)
                for chunk_idx, chunk in enumerate(chunks):
                    yield PageRef(
                        index=idx,
                        image_path="",
                        original_ref=entry,
                        metadata={
                            "chapter_text": chunk,
                            "chapter_title": title if chunk_idx == 0 else "",
                            "xhtml_entry": entry,
                            "chunk_index": chunk_idx,
                            "total_chunks": len(chunks),
                            "mode": "novel",
                        },
                    )
                    idx += 1

    def repack(self, pages: Iterator[TranslatedPage], output_path: Path) -> None:
        """Repack translated text back into EPUB structure."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sorted_pages = sorted(pages, key=lambda p: p.index)
        if not sorted_pages:
            return

        # Group translations by xhtml_entry
        by_entry: dict[str, list[TranslatedPage]] = {}
        for tpage in sorted_pages:
            entry = (tpage.page_json or {}).get("xhtml_entry", "")
            by_entry.setdefault(entry, []).append(tpage)

        # We need the original EPUB to preserve structure
        # The original path should be in metadata
        original_path = (sorted_pages[0].page_json or {}).get("original_epub_path", "")
        if not original_path or not Path(original_path).exists():
            # Fallback: write as plain text EPUB-like ZIP
            self._write_fallback(sorted_pages, output_path)
            return

        with zipfile.ZipFile(original_path, "r") as zin:
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename in by_entry:
                        # Replace text content in this XHTML
                        xhtml = data.decode("utf-8", errors="replace")
                        translations = sorted(by_entry[item.filename], key=lambda p: (p.page_json or {}).get("chunk_index", 0))
                        new_text = "\n\n".join(
                            (tp.page_json or {}).get("translated_text", "")
                            for tp in translations
                        )
                        # Replace body content while preserving structure
                        xhtml = self._replace_body_text(xhtml, new_text)
                        data = xhtml.encode("utf-8")
                    zout.writestr(item, data)

    def _replace_body_text(self, xhtml: str, new_text: str) -> str:
        """Replace visible text in XHTML body while preserving tags."""
        body_match = re.search(r"(<body[^>]*>)(.*?)(</body>)", xhtml, re.DOTALL)
        if not body_match:
            return xhtml

        body_start, _old_body, body_end = body_match.groups()
        # Wrap new text in paragraphs
        paragraphs = "\n".join(f"<p>{line}</p>" for line in new_text.split("\n") if line.strip())
        return xhtml[:body_match.start()] + body_start + paragraphs + body_end + xhtml[body_match.end():]

    def _write_fallback(self, pages: list[TranslatedPage], output_path: Path) -> None:
        """Write translated text as a simple EPUB-like ZIP when original is unavailable."""
        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # mimetype must be first and uncompressed
            zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

            # Simple OPF
            manifest_items = []
            spine_refs = []
            for i, page in enumerate(pages):
                entry_name = f"text/ch{i:04d}.xhtml"
                text = (page.page_json or {}).get("translated_text", "")
                title = (page.page_json or {}).get("chapter_title", f"Chapter {i + 1}")
                xhtml = (
                    '<?xml version="1.0" encoding="utf-8"?>\n'
                    '<!DOCTYPE html>\n'
                    '<html xmlns="http://www.w3.org/1999/xhtml">\n'
                    '<head><title>{title}</title></head>\n'
                    '<body>\n'
                    '<h1>{title}</h1>\n'
                    '{body}\n'
                    '</body></html>'
                ).format(
                    title=title,
                    body="\n".join(f"<p>{line}</p>" for line in text.split("\n") if line.strip()),
                )
                zf.writestr(entry_name, xhtml)
                item_id = f"ch{i}"
                manifest_items.append(f'<item id="{item_id}" href="{entry_name}" media-type="application/xhtml+xml"/>')
                spine_refs.append(f'<itemref idref="{item_id}"/>')

            opf = (
                '<?xml version="1.0" encoding="utf-8"?>\n'
                '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">\n'
                '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
                '  <dc:title>Translated</dc:title>\n'
                '  <dc:language>zh</dc:language>\n'
                '  <dc:identifier id="uid">mga-translated</dc:identifier>\n'
                '</metadata>\n'
                '<manifest>\n{items}\n</manifest>\n'
                '<spine>\n{spine}\n</spine>\n'
                '</package>'
            ).format(
                items="\n".join(manifest_items),
                spine="\n".join(spine_refs),
            )
            zf.writestr("OEBPS/content.opf", opf)

            # Container
            container = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
                '  <rootfiles>\n'
                '    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>\n'
                '  </rootfiles>\n'
                '</container>'
            )
            zf.writestr("META-INF/container.xml", container)
