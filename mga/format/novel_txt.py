"""Novel TXT adapter — extracts and translates plain text files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from ..models.format import PageRef, TranslatedPage
from .base import FormatAdapter


def _split_into_chunks(text: str, max_chars: int = 500) -> list[str]:
    """Split text into chunks: first by double-newline, then by sentence if too long."""
    # Split into paragraphs by double-newline
    raw_paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    current = ""

    for para in raw_paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}" if current else para
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


class NovelTXTAdapter(FormatAdapter):
    """Adapter for translating plain text (.txt) files.

    Splits text into manageable chunks, translates each, and reassembles.
    """

    def extract(self, input_path: Path) -> Iterator[PageRef]:
        if not input_path.is_file():
            raise FileNotFoundError(f"Input path is not a file: {input_path}")

        text = input_path.read_text(encoding="utf-8")
        chunks = _split_into_chunks(text)

        for idx, chunk in enumerate(chunks):
            yield PageRef(
                index=idx,
                image_path="",
                original_ref=input_path.name,
                metadata={
                    "chapter_text": chunk,
                    "chapter_title": "",
                    "chunk_index": idx,
                    "total_chunks": len(chunks),
                    "mode": "novel",
                },
            )

    def repack(self, pages: Iterator[TranslatedPage], output_path: Path) -> None:
        """Write translated chunks as a single text file."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sorted_pages = sorted(pages, key=lambda p: p.index)
        parts = [
            (tp.page_json or {}).get("translated_text", "")
            for tp in sorted_pages
        ]
        output_path.write_text("\n\n".join(parts), encoding="utf-8")
