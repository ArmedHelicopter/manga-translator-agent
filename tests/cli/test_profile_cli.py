from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from mga.cli.main import main
from mga.memory.entities import CharacterState
from mga.memory.state import StateManager


def _read_profile(project_dir: Path, character_id: str) -> dict:
    path = project_dir / "memory" / "state" / "characters" / f"{character_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_profile_edit_creates_character_profile(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "profile",
            "edit",
            str(tmp_path),
            "akari",
            "--name-jp",
            "雨宮灯",
            "--name-zh",
            "雨宫灯",
            "--archetype",
            "protagonist",
            "--speech-pattern",
            "polite=soft formal endings",
            "--tone",
            "default=calm",
            "--translation-note",
            "addressing=uses surnames",
            "--catchphrase",
            "大丈夫です",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Profile saved: akari" in result.output
    profile = _read_profile(tmp_path, "akari")
    assert profile["name_jp"] == "雨宮灯"
    assert profile["name_zh"] == "雨宫灯"
    assert profile["archetype"] == "protagonist"
    assert profile["speech_patterns"] == {"polite": "soft formal endings"}
    assert profile["tone_spectrum"] == {"default": "calm"}
    assert profile["translation_notes"] == {"addressing": "uses surnames"}
    assert profile["catchphrases"] == ["大丈夫です"]


def test_profile_edit_updates_existing_profile_without_duplicate_catchphrase(tmp_path: Path) -> None:
    runner = CliRunner()
    first = runner.invoke(
        main,
        [
            "profile",
            "edit",
            str(tmp_path),
            "ren",
            "--name-jp",
            "蓮",
            "--catchphrase",
            "知らない",
        ],
    )
    assert first.exit_code == 0, first.output

    second = runner.invoke(
        main,
        [
            "profile",
            "edit",
            str(tmp_path),
            "ren",
            "--name-zh",
            "莲",
            "--speech-pattern",
            "rough=short blunt lines",
            "--catchphrase",
            "知らない",
        ],
    )

    assert second.exit_code == 0, second.output
    profile = _read_profile(tmp_path, "ren")
    assert profile["name_jp"] == "蓮"
    assert profile["name_zh"] == "莲"
    assert profile["speech_patterns"] == {"rough": "short blunt lines"}
    assert profile["catchphrases"] == ["知らない"]


def test_profile_edit_rejects_invalid_key_value_option(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "profile",
            "edit",
            str(tmp_path),
            "ren",
            "--speech-pattern",
            "missing-separator",
        ],
    )

    assert result.exit_code != 0
    assert "--speech-pattern must use key=value" in result.output


def test_profile_list_defaults_to_current_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=str(tmp_path)):
        StateManager.upsert_character(
            Path("."),
            CharacterState(
                character_id="akari",
                name_jp="Akari",
                name_zh="Deng",
                archetype="protagonist",
            ),
        )

        result = runner.invoke(main, ["profile", "list"])

        assert result.exit_code == 0, result.output
        assert "akari: Akari / Deng" in result.output


def test_profile_export_writes_toml_profile(tmp_path: Path) -> None:
    runner = CliRunner()
    edit = runner.invoke(
        main,
        [
            "profile",
            "edit",
            str(tmp_path),
            "akari",
            "--name-jp",
            "Akari",
            "--name-zh",
            "Deng",
            "--speech-pattern",
            "default=polite",
            "--catchphrase",
            "I understand",
        ],
    )
    assert edit.exit_code == 0, edit.output

    result = runner.invoke(main, ["profile", "export", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Profiles exported: 1 profiles" in result.output
    profile_toml = (tmp_path / "character_profiles" / "akari.toml").read_text(
        encoding="utf-8"
    )
    assert 'character_id = "akari"' in profile_toml
    assert 'name_jp = "Akari"' in profile_toml
    assert 'default = "polite"' in profile_toml
    assert '"I understand"' in profile_toml


def test_profile_import_reads_toml_profile(tmp_path: Path) -> None:
    runner = CliRunner()
    profile_dir = tmp_path / "character_profiles" / "glass_and_blade"
    profile_dir.mkdir(parents=True)
    (profile_dir / "akari.toml").write_text(
        """
character_id = "akari"
name_jp = "Akari"
name_zh = "Deng"
archetype = "protagonist"
catchphrases = ["I understand"]

[speech_patterns]
default = "polite"

[tone_spectrum]
default = "quiet"

[translation_notes]
addressing = "uses surnames"
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(main, ["profile", "import", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Profiles imported: 1 profiles" in result.output
    profile = _read_profile(tmp_path, "akari")
    assert profile["name_jp"] == "Akari"
    assert profile["name_zh"] == "Deng"
    assert profile["archetype"] == "protagonist"
    assert profile["speech_patterns"] == {"default": "polite"}
    assert profile["catchphrases"] == ["I understand"]
    assert profile["tone_spectrum"] == {"default": "quiet"}
    assert profile["translation_notes"] == {"addressing": "uses surnames"}
