from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from mga.cli.main import main


def _read_scene(project_dir: Path, scene_id: str) -> dict:
    path = project_dir / "memory" / "state" / "scenes" / f"{scene_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_scene_edit_creates_scene_context(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "scene",
            "edit",
            str(tmp_path),
            "ch1_p3_glass_room",
            "--chapter",
            "1",
            "--page",
            "3",
            "--description",
            "Akari confronts Ren in the glass room",
            "--mood",
            "tense",
            "--narrative-summary",
            "Ren hides what happened in the previous chapter",
            "--relationship-change",
            "Akari stops trusting Ren",
            "--key-dialogue",
            "Tell me the truth.",
            "--future-impact",
            "Akari investigates alone next chapter",
            "--character",
            "akari",
            "--character",
            "ren",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Scene saved: ch1_p3_glass_room" in result.output
    scene = _read_scene(tmp_path, "ch1_p3_glass_room")
    assert scene == {
        "scene_id": "ch1_p3_glass_room",
        "chapter": 1,
        "page": 3,
        "scene_description": "Akari confronts Ren in the glass room",
        "characters": ["akari", "ren"],
        "mood": "tense",
        "narrative_summary": "Ren hides what happened in the previous chapter",
        "relationship_changes": ["Akari stops trusting Ren"],
        "key_dialogue": ["Tell me the truth."],
        "future_impact": "Akari investigates alone next chapter",
    }


def test_scene_edit_updates_existing_scene_without_duplicate_characters(tmp_path: Path) -> None:
    runner = CliRunner()
    first = runner.invoke(
        main,
        [
            "scene",
            "edit",
            str(tmp_path),
            "ch2_p1",
            "--chapter",
            "2",
            "--page",
            "1",
            "--character",
            "akari",
            "--relationship-change",
            "Akari doubts Ren",
            "--key-dialogue",
            "You lied.",
        ],
    )
    assert first.exit_code == 0, first.output

    second = runner.invoke(
        main,
        [
            "scene",
            "edit",
            str(tmp_path),
            "ch2_p1",
            "--mood",
            "quiet",
            "--character",
            "akari",
            "--character",
            "ren",
            "--relationship-change",
            "Akari doubts Ren",
            "--relationship-change",
            "Ren apologizes",
            "--key-dialogue",
            "You lied.",
            "--key-dialogue",
            "I am sorry.",
            "--future-impact",
            "Their alliance is fragile",
        ],
    )

    assert second.exit_code == 0, second.output
    scene = _read_scene(tmp_path, "ch2_p1")
    assert scene["chapter"] == 2
    assert scene["page"] == 1
    assert scene["mood"] == "quiet"
    assert scene["characters"] == ["akari", "ren"]
    assert scene["relationship_changes"] == [
        "Akari doubts Ren",
        "Ren apologizes",
    ]
    assert scene["key_dialogue"] == ["You lied.", "I am sorry."]
    assert scene["future_impact"] == "Their alliance is fragile"


def test_scene_list_prints_recorded_scenes(tmp_path: Path) -> None:
    runner = CliRunner()
    add_result = runner.invoke(
        main,
        [
            "scene",
            "edit",
            str(tmp_path),
            "ch3_p4",
            "--chapter",
            "3",
            "--page",
            "4",
            "--description",
            "Bridge aftermath",
            "--mood",
            "somber",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(main, ["scene", "list", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "ch3_p4: ch3 p4" in result.output
    assert "somber" in result.output
