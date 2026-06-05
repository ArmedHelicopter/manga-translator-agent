from __future__ import annotations

import json
from pathlib import Path

from mga.models import Bubble, Page, PageImage, ProjectConfig, TranslationCandidate
from mga.pipeline.output_stage import OutputStage
from mga.pipeline.stages import PipelineContext


def test_repack_bilingual_uses_pdf_output_and_original_image_paths(
    monkeypatch,
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    rendered = output_dir / "page-0000.png"
    rendered.write_bytes(b"rendered")
    original = tmp_path / "original.png"
    original.write_bytes(b"original")
    captured = {}

    class FakeAdapter:
        def repack(self, pages, output_path):
            captured["pages"] = list(pages)
            captured["output_path"] = output_path

    monkeypatch.setattr("mga.format.get_adapter", lambda output_format: FakeAdapter())

    context = PipelineContext(
        pages=[
            Page(
                page_id="page_0000",
                page_index=0,
                image=PageImage(path=str(original)),
            )
        ],
    )

    OutputStage()._repack_to_format(
        output_dir,
        context,
        ProjectConfig(),
        "bilingual",
    )

    assert captured["output_path"] == output_dir / "output.pdf"
    assert captured["pages"][0].image_path == str(rendered)
    assert captured["pages"][0].page_json["original_image_path"] == str(original)


def test_repack_non_bilingual_keeps_format_extension(monkeypatch, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "page-0000.png").write_bytes(b"rendered")
    captured = {}

    class FakeAdapter:
        def repack(self, pages, output_path):
            captured["pages"] = list(pages)
            captured["output_path"] = output_path

    monkeypatch.setattr("mga.format.get_adapter", lambda output_format: FakeAdapter())

    OutputStage()._repack_to_format(
        output_dir,
        PipelineContext(),
        ProjectConfig(),
        "pdf",
    )

    assert captured["output_path"] == output_dir / "output.pdf"
    assert captured["pages"][0].page_json == {"source": "rendered"}


def test_report_format_writes_requested_json_file(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    context = PipelineContext(
        pages=[
            Page(
                page_id="page_0000",
                page_index=0,
                image=PageImage(path=str(tmp_path / "original.png")),
                bubbles=[Bubble(bubble_id="b1", source_text="原文")],
            )
        ],
        translations=[
            TranslationCandidate(
                bubble_id="b1",
                text="Translated",
                confidence=0.91,
                rationale="test",
            )
        ],
        project_config=ProjectConfig(
            output_dir=str(report_path),
            output_format="report",
            save_artifacts=True,
        ),
        metadata={"output_path": str(report_path)},
    )

    result = OutputStage().execute(context)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["total_translations"] == 1
    assert payload["entries"][0]["bubble_id"] == "b1"
    assert payload["entries"][0]["source_text"] == "原文"
    assert result.artifacts["output"]["output_dir"] == str(tmp_path)
    assert result.artifacts["output"]["report_output"] == str(report_path)


def test_report_format_writes_report_json_in_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    context = PipelineContext(
        translations=[TranslationCandidate(bubble_id="b1", text="Translated")],
        project_config=ProjectConfig(
            output_dir=str(output_dir),
            output_format="report",
            save_artifacts=False,
        ),
        metadata={"output_path": str(output_dir)},
    )

    OutputStage().execute(context)

    report_path = output_dir / "report.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["summary"]["total_translations"] == 1


def test_manga_output_writes_page_translation_history(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    context = PipelineContext(
        pages=[
            Page(
                page_id="ch011_p001",
                page_index=1,
                image=PageImage(path=str(tmp_path / "original.png")),
                bubbles=[
                    Bubble(
                        bubble_id="b1",
                        source_text="SOURCE",
                        speaker_id="akari",
                        reading_order=2,
                    ),
                    Bubble(
                        bubble_id="b2",
                        source_text="UNTRANSLATED",
                        reading_order=3,
                    ),
                ],
            )
        ],
        translations=[
            TranslationCandidate(
                bubble_id="b1",
                text="Translated",
                confidence=0.92,
                rationale="ok",
            )
        ],
        project_config=ProjectConfig(
            output_dir=str(output_dir),
            output_format="images",
            save_artifacts=False,
        ),
    )

    result = OutputStage().execute(context)

    history_path = output_dir / "translations" / "ch011_p001.json"
    payload = json.loads(history_path.read_text(encoding="utf-8"))
    assert payload["page_id"] == "ch011_p001"
    assert payload["page_index"] == 1
    assert payload["bubbles"][0]["bubble_id"] == "b1"
    assert payload["bubbles"][0]["source_text"] == "SOURCE"
    assert payload["bubbles"][0]["speaker_id"] == "akari"
    assert payload["translations"][0]["bubble_id"] == "b1"
    assert payload["translations"][0]["text"] == "Translated"
    assert "translations/ch011_p001.json" in result.artifacts["output"]["files_written"]
