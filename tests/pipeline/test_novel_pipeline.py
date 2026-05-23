"""Tests for novel mode pipeline — end-to-end with monkeypatched provider."""

from pathlib import Path

from mga.models import ProjectConfig, TranslationCandidate
from mga.pipeline.orchestrator import PipelineOrchestrator


class FakeProvider:
    """Fake LLM provider that returns pre-defined translations."""

    def __init__(self, translations: dict[str, str] | None = None):
        self._translations = translations or {}
        self._call_count = 0

    def chat(self, messages, **kwargs):
        self._call_count += 1
        # Return a translation based on the source text in the prompt
        prompt = messages[0]["content"] if messages else ""
        for src, tgt in self._translations.items():
            if src in prompt:
                return tgt
        return "translated"


def _make_novel_txt(tmp_path: Path) -> Path:
    """Create a test TXT file."""
    txt = tmp_path / "novel.txt"
    txt.write_text("太郎は学校に行った。\n\n花子は家で本を読んだ。", encoding="utf-8")
    return txt


def test_novel_pipeline_stages():
    """Verify novel pipeline selects correct stages."""
    cfg = ProjectConfig(pipeline_mode="novel")
    orch = PipelineOrchestrator(config=cfg)
    names = [s.name for s in orch.stages]
    assert "vision" not in names
    assert "render" not in names
    assert "format" in names
    assert "translation" in names
    assert "qa" in names
    assert "output" in names


def test_novel_pipeline_end_to_end(tmp_path, monkeypatch):
    """Run novel pipeline on TXT file with fake provider."""
    txt = _make_novel_txt(tmp_path)
    output = tmp_path / "translated.txt"

    cfg = ProjectConfig(
        pipeline_mode="novel",
        input_format="txt",
        output_format="txt",
        source_lang="ja",
        target_lang="zh-CN",
        working_dir=str(tmp_path),
        output_dir=str(tmp_path / "output"),
    )

    fake = FakeProvider({
        "太郎は学校に行った。": "太郎去了学校。",
        "花子は家で本を読んだ。": "花子在家看书。",
    })

    # Patch get_provider in modules that import it at module level
    monkeypatch.setattr(
        "mga.pipeline.translation_stage.get_provider",
        lambda name, **kwargs: fake,
    )
    monkeypatch.setattr(
        "mga.pipeline.qa_stage.get_provider",
        lambda name, **kwargs: fake,
    )

    orch = PipelineOrchestrator(config=cfg)
    ctx = orch.run(str(txt), str(output), cfg)

    # Verify translations were produced
    assert len(ctx.translations) >= 1
    translated_texts = {t.text for t in ctx.translations}
    assert any("太郎" in t for t in translated_texts)

    # Verify output file was created
    assert output.exists()
    content = output.read_text(encoding="utf-8")
    assert len(content) > 0
