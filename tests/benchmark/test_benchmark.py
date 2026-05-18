from __future__ import annotations

import json
from pathlib import Path
import sys

from manga_translate.artifacts import ArtifactStore
from manga_translate.benchmark import run_external_translation_benchmark
from manga_translate.benchmark.external import (
    resolve_manga_image_translator_repo,
    run_manga_image_translator_baseline,
)
from manga_translate.benchmark.evaluate import (
    run_extraction_benchmark,
    run_translation_benchmark,
    select_sample_pages,
)
from manga_translate.models import BoundingBox, Bubble, Page, PageImage, TranslationCandidate, Utterance
from manga_translate.runtime.external import (
    _build_external_child_env,
    _normalize_external_text_blocks,
    _parse_saved_text_blocks,
)


class FakeBenchmarkProvider:
    def vision_extract(self, page: Page, store=None):
        enriched = page.model_copy(
            update={
                "bubbles": [
                    Bubble(
                        bubble_id="bubble-1",
                        bbox=BoundingBox(x=0, y=0, width=10, height=10),
                        source_text="こんにちは",
                        reading_order=0,
                    )
                ],
                "scene_summary": "benchmark page",
            }
        )
        return enriched, {"provider": "fake", "model": "fake", "latency_ms": 1}

    def translate(self, page: Page, utterances: list[Utterance], store=None):
        return (
            [
                TranslationCandidate(
                    bubble_id=utterance.bubble_id,
                    text="你好",
                    rationale="structured benchmark",
                    confidence=0.95,
                )
                for utterance in utterances
            ],
            {"provider": "fake", "model": "fake", "latency_ms": 1},
        )

    def direct_translate_page(self, page: Page, store=None):
        return (
            [
                TranslationCandidate(
                    bubble_id="bubble-1",
                    text="你好",
                    rationale="direct benchmark",
                    confidence=0.9,
                )
            ],
            {"provider": "fake", "model": "fake", "latency_ms": 1},
        )


def test_run_extraction_benchmark_writes_report(monkeypatch, tmp_path: Path) -> None:
    page = Page(
        page_id="page-0001",
        page_index=0,
        image=PageImage(
            path=str(Path("tests/fixtures/images/source/sample-page-01.png").resolve()),
            width=160,
            height=220,
        ),
    )
    store = ArtifactStore(tmp_path / "output")

    def fake_ocr(image_path: Path, output_dir: Path, page_id: str, spec_name: str):
        txt_path = output_dir / spec_name / f"{page_id}.txt"
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text("OCR TEXT\n", encoding="utf-8")

        class Result:
            pass

        result = Result()
        result.page_id = page_id
        result.text = "OCR TEXT"
        result.raw_path = str(txt_path)
        result.line_count = 1
        result.character_count = 8
        return result

    monkeypatch.setattr("manga_translate.benchmark.evaluate._run_tesseract_ocr", fake_ocr)
    monkeypatch.setattr(
        "manga_translate.benchmark.evaluate._run_ocr_spec",
        lambda image_path, ocr_dir, page_id, spec_name: fake_ocr(image_path, ocr_dir, page_id, spec_name),
    )
    summary = run_extraction_benchmark(
        pages=[page],
        provider=FakeBenchmarkProvider(),
        store=store,
        ocr_specs=["tesseract_jpn"],
    )

    report = json.loads((tmp_path / "output" / "benchmark" / "extraction-report.json").read_text("utf-8"))
    assert summary["page_count"] == 1
    assert report["comparisons"][0]["vision_structured"]["bubble_count"] == 1
    assert report["comparisons"][0]["vision_structured"]["joined_text"] == "こんにちは"
    assert report["comparisons"][0]["ocr"]["tesseract_jpn"]["joined_text"] == "OCR TEXT"
    assert report["annotation_template"] == "benchmark/annotations.extraction.template.json"


def test_run_translation_benchmark_writes_report(tmp_path: Path) -> None:
    page = Page(
        page_id="page-0001",
        page_index=0,
        image=PageImage(
            path=str(Path("tests/fixtures/images/source/sample-page-01.png").resolve()),
            width=160,
            height=220,
        ),
    )
    store = ArtifactStore(tmp_path / "output")
    summary = run_translation_benchmark(
        pages=[page],
        provider=FakeBenchmarkProvider(),
        store=store,
        vision_modes=["structured", "direct"],
    )

    report = json.loads((tmp_path / "output" / "benchmark" / "translation-report.json").read_text("utf-8"))
    assert summary["page_count"] == 1
    assert report["comparisons"][0]["vision"]["structured"]["unit_count"] == 1
    assert report["comparisons"][0]["vision"]["structured"]["joined_text"] == "你好"
    assert report["comparisons"][0]["vision"]["direct"]["joined_text"] == "你好"
    assert report["annotation_template"] == "benchmark/annotations.translation.template.json"


def test_select_sample_pages_window_and_random() -> None:
    pages = [
        Page(
            page_id=f"page-{index:04d}",
            page_index=index,
            image=PageImage(path=f"/tmp/{index}.png", width=100, height=100),
        )
        for index in range(10)
    ]
    window = select_sample_pages(pages, max_pages=3, start_index=2, sample_strategy="window")
    random_pages = select_sample_pages(pages, max_pages=3, sample_strategy="random", seed=7)
    assert [page.page_index for page in window] == [2, 3, 4]
    assert len(random_pages) == 3


def test_resolve_manga_image_translator_repo_prefers_explicit_path(tmp_path: Path) -> None:
    repo = tmp_path / "mit"
    (repo / "manga_translator").mkdir(parents=True)
    (repo / "manga_translator" / "__main__.py").write_text("", encoding="utf-8")
    assert resolve_manga_image_translator_repo(repo) == repo


def test_run_manga_image_translator_baseline_writes_summary(monkeypatch, tmp_path: Path) -> None:
    repo = tmp_path / "mit"
    (repo / "manga_translator").mkdir(parents=True)
    (repo / "manga_translator" / "__main__.py").write_text("", encoding="utf-8")
    (repo / "README.md").write_text("# test\n", encoding="utf-8")

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "001.png").write_text("fake-image", encoding="utf-8")
    (input_dir / "002.jpg").write_text("fake-image", encoding="utf-8")

    output_dir = tmp_path / "output"

    class Completed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(command, cwd, env, capture_output, text, check):
        assert command[:4] == [str(Path(sys.executable)), "-m", "manga_translator", "local"]
        assert "-i" in command
        assert command[command.index("-i") + 1] == str(input_dir.resolve())
        assert "-o" in command
        assert "--save-text-file" in command
        assert "--config-file" in command
        assert env["LD_LIBRARY_PATH"].startswith("/usr/lib/x86_64-linux-gnu:")
        assert env["LD_PRELOAD"].startswith("/usr/lib/x86_64-linux-gnu/libstdc++.so.6")
        assert "CONDA_PREFIX" not in env
        assert "PYTHONPATH" not in env
        assert env["OPENAI_API_KEY"] == "test-key"
        assert env["OPENAI_API_BASE"] == "https://example.test/v1"
        assert env["OPENAI_MODEL"] == "gpt-test-mini"
        assert cwd == repo
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "001.png").write_text("rendered", encoding="utf-8")
        saved_text_path = Path(command[command.index("--save-text-file") + 1])
        config_path = Path(command[command.index("--config-file") + 1])
        config_payload = json.loads(config_path.read_text(encoding="utf-8"))
        assert config_payload["translator"]["target_lang"] == "CHS"
        assert config_payload["translator"]["translator"] == "chatgpt"
        saved_text_path.write_text(
            "\n".join(
                [
                    f"[{(input_dir / '001.png').resolve()}]",
                    "",
                    "-- 1 --",
                    "text:  原文一",
                    "trans:  译文一",
                    "coords: [1, 2, 3, 4]",
                    "",
                    f"[{(input_dir / '002.jpg').resolve()}]",
                    "",
                    "-- 1 --",
                    "text:  原文二",
                    "trans:  译文二",
                    "coords: [5, 6, 7, 8]",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return Completed()

    monkeypatch.setattr("manga_translate.runtime.external.subprocess.run", fake_run)
    monkeypatch.setattr("manga_translate.runtime.external.load_image_metadata", lambda path: (100, 200, None))
    summary = run_manga_image_translator_baseline(
        repo_dir=repo,
        input_dir=input_dir,
        output_dir=output_dir,
        openai_settings={
            "api_key": "test-key",
            "base_url": "https://example.test/v1",
            "text_model": "gpt-test-mini",
        },
    )

    summary_path = output_dir / "external-baseline-summary.json"
    assert summary["input_count"] == 2
    assert summary["parsed_page_count"] == 2
    assert summary["rendered_images"] == ["001.png"]
    assert summary["saved_text_artifact"] == str(output_dir / "external-baseline-text.txt")
    assert summary["normalized_text_artifact"] == str(output_dir / "external-baseline-text-normalized.json")
    assert summary["config_artifact"] == str(output_dir / "external-runtime-config.json")
    assert summary["python_executable"] == str(Path(sys.executable))
    assert summary["openai_base_url"] == "https://example.test/v1"
    assert summary["openai_model"] == "gpt-test-mini"
    assert summary["openai_api_key_present"] is True
    assert summary["runtime_env"]["sanitized_conda"] is True
    assert summary["runtime_env"]["pythonpath_removed"] is True
    assert summary["runtime_env"]["pythonhome_removed"] is True
    assert summary["runtime_env"]["ld_library_path_present"] is True
    assert summary["runtime_env"]["ld_preload_present"] is True
    assert summary_path.exists()


def test_parse_saved_text_blocks_supports_multiline_text() -> None:
    raw_text = "\n".join(
        [
            "[/tmp/page-1.png]",
            "",
            "-- 1 --",
            "text:  第一行",
            "第二行",
            "trans:  译文第一行",
            "译文第二行",
            "coords: [1, 2, 3, 4]",
            "",
        ]
    )

    blocks = _parse_saved_text_blocks(raw_text)

    assert len(blocks) == 1
    assert blocks[0]["regions"][0]["text"] == "第一行\n第二行"
    assert blocks[0]["regions"][0]["translation"] == "译文第一行\n译文第二行"


def test_build_external_child_env_strips_conda_and_python_overrides(monkeypatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/home/exusiai/anaconda3/bin:/bin")
    monkeypatch.setenv("LD_LIBRARY_PATH", "/home/exusiai/anaconda3/lib:/usr/local/cuda/lib64")
    monkeypatch.setenv("LD_PRELOAD", "/tmp/custom-preload.so")
    monkeypatch.setenv("PYTHONPATH", "src")
    monkeypatch.setenv("PYTHONHOME", "/tmp/python-home")
    monkeypatch.setenv("CONDA_PREFIX", "/home/exusiai/anaconda3")

    env = _build_external_child_env()

    assert env["PATH"] == "/usr/bin:/bin"
    assert env["LD_LIBRARY_PATH"].startswith("/usr/lib/x86_64-linux-gnu:")
    assert "/home/exusiai/anaconda3/lib" not in env["LD_LIBRARY_PATH"]
    assert env["LD_PRELOAD"].startswith("/usr/lib/x86_64-linux-gnu/libstdc++.so.6:")
    assert "PYTHONPATH" not in env
    assert "PYTHONHOME" not in env
    assert "CONDA_PREFIX" not in env


def test_normalize_external_text_blocks_writes_page_level_json(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    page1 = input_dir / "001.png"
    page2 = input_dir / "002.jpg"
    page1.write_text("fake-image", encoding="utf-8")
    page2.write_text("fake-image", encoding="utf-8")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    normalized = _normalize_external_text_blocks(
        [
            {
                "image_path": str(page1.resolve()),
                "regions": [
                    {"text": "原文一", "translation": "译文一", "coords": []},
                    {"text": "原文二", "translation": "译文二", "coords": []},
                ],
            }
        ],
        input_dir=input_dir,
        output_dir=output_dir,
    )

    assert normalized == [
        {
            "page_id": "page-0001",
            "image_path": str(page1.resolve()),
            "source_text_joined": "原文一\n原文二",
            "translated_text_joined": "译文一\n译文二",
            "region_count": 2,
        }
    ]
    normalized_path = output_dir / "external-baseline-text-normalized.json"
    assert normalized_path.exists()


def test_run_external_translation_benchmark_writes_report(tmp_path: Path) -> None:
    page = Page(
        page_id="page-0001",
        page_index=0,
        image=PageImage(
            path=str(Path("tests/fixtures/images/source/sample-page-01.png").resolve()),
            width=160,
            height=220,
        ),
    )
    store = ArtifactStore(tmp_path / "output")
    internal_report = run_translation_benchmark(
        pages=[page],
        provider=FakeBenchmarkProvider(),
        store=store,
        vision_modes=["structured", "direct"],
    )

    summary = run_external_translation_benchmark(
        pages=[page],
        internal_translation_report=internal_report,
        external_pages=[
            {
                "page_id": "page-0001",
                "image_path": str(Path(page.image.path).resolve()),
                "source_text_joined": "こんにちは",
                "translated_text_joined": "外部你好",
                "region_count": 1,
            }
        ],
        store=store,
    )

    report_path = tmp_path / "output" / "benchmark" / "external-translation-report.json"
    report = json.loads(report_path.read_text("utf-8"))
    assert summary["page_count"] == 1
    assert report["external_name"] == "manga_image_translator"
    assert report["comparisons"][0]["vision"]["structured"]["joined_text"] == "你好"
    assert report["comparisons"][0]["external"]["manga_image_translator"]["joined_text"] == "外部你好"
