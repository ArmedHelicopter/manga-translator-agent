"""Fixture-level proof for cross-page character style memory."""

from pathlib import Path

from tests.support.character_memory_demo import run_character_memory_demo


FIXTURE = Path("tests/fixtures/json/character_memory/demo_cross_page_style.json")


def test_later_prompt_includes_style_learned_from_earlier_page(tmp_path):
    result = run_character_memory_demo(FIXTURE, tmp_path)

    first_trace = result.trace_for("p001-b001")
    later_trace = result.trace_for("p002-b001")

    assert "角色档案" not in first_trace.prompt
    assert "角色档案" in later_trace.prompt
    assert "礼貌、克制、句尾偏正式" in later_trace.prompt
    assert "中文译文使用礼貌克制表达" in later_trace.prompt


def test_different_speakers_keep_separate_memory_and_style(tmp_path):
    result = run_character_memory_demo(FIXTURE, tmp_path)

    akari_trace = result.trace_for("p003-b001")
    ren_trace = result.trace_for("p003-b002")

    assert "礼貌、克制、句尾偏正式" in akari_trace.prompt
    assert "粗鲁、直接、句尾偏口语" not in akari_trace.prompt
    assert "粗鲁、直接、句尾偏口语" in ren_trace.prompt
    assert "礼貌、克制、句尾偏正式" not in ren_trace.prompt

    assert akari_trace.translation == "请您稍等一下。"
    assert ren_trace.translation == "少废话，快点。"


def test_snapshots_are_emitted_after_each_page_with_evidence(tmp_path):
    result = run_character_memory_demo(FIXTURE, tmp_path)

    assert len(result.snapshots) == 6

    p001_akari = result.snapshot_for("p001", "akari")
    p003_akari = result.snapshot_for("p003", "akari")
    p003_ren = result.snapshot_for("p003", "ren")

    assert p001_akari.last_updated_page == "p001"
    assert p001_akari.evidence_lines == ("おはようございます。",)
    assert p003_akari.last_updated_page == "p003"
    assert p003_akari.evidence_lines == (
        "おはようございます。",
        "ありがとうございます。",
        "少しだけ待ってください。",
    )
    assert p003_akari.style_summary == "礼貌、克制、句尾偏正式"
    assert p003_ren.style_summary == "粗鲁、直接、句尾偏口语"


def test_snapshot_prompt_excerpt_makes_memory_auditable(tmp_path):
    result = run_character_memory_demo(FIXTURE, tmp_path)

    p002_akari = result.snapshot_for("p002", "akari")
    p002_ren = result.snapshot_for("p002", "ren")

    assert "Source: ありがとうございます。" in p002_akari.prompt_excerpt
    assert "礼貌、克制、句尾偏正式" in p002_akari.prompt_excerpt
    assert "Source: そんなの知るかよ。" in p002_ren.prompt_excerpt
    assert "粗鲁、直接、句尾偏口语" in p002_ren.prompt_excerpt
