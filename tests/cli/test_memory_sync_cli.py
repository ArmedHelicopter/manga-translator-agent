from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from mga.cli.main import main
from mga.memory.entities import SceneState, TermState
from mga.memory.state import StateManager
from mga.memory.wiki import WikiProjection, work_scoped_id


def test_memory_sync_defaults_to_state_to_wiki(tmp_path: Path) -> None:
    runner = CliRunner()
    StateManager.upsert_scene(
        tmp_path,
        SceneState(
            scene_id="ch1_p1",
            chapter=1,
            page=1,
            scene_description="Opening hallway",
        ),
    )

    result = runner.invoke(main, ["memory", "sync", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Wiki synced" in result.output
    assert (tmp_path / "memory" / "scenes" / "ch1_p1.md").exists()


def test_memory_init_and_sync_default_to_current_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=str(tmp_path)):
        result = runner.invoke(main, ["memory", "init"])

        assert result.exit_code == 0, result.output
        assert "Memory initialized" in result.output
        assert Path("memory/state").exists()

        StateManager.upsert_scene(
            Path("."),
            SceneState(
                scene_id="ch1_p1",
                chapter=1,
                page=1,
                scene_description="Opening hallway",
            ),
        )

        sync = runner.invoke(main, ["memory", "sync"])

        assert sync.exit_code == 0, sync.output
        assert "Wiki synced" in sync.output
        assert Path("memory/scenes/ch1_p1.md").exists()


def test_memory_sync_can_compile_wiki_to_state(tmp_path: Path) -> None:
    runner = CliRunner()
    scene_md = tmp_path / "memory" / "scenes" / "ch4_p2.md"
    scene_md.parent.mkdir(parents=True)
    scene_md.write_text(
        WikiProjection.generate_scene_page(
            SceneState(
                scene_id="ch4_p2",
                chapter=4,
                page=2,
                scene_description="Akari notices the hidden mark",
                mood="uneasy",
            )
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        main,
        ["memory", "sync", str(tmp_path), "--direction", "wiki-to-state"],
    )

    assert result.exit_code == 0, result.output
    assert "State synced from wiki" in result.output
    scene = StateManager.get_scene(tmp_path, "ch4_p2")
    assert scene is not None
    assert scene.scene_description == "Akari notices the hidden mark"
    assert scene.mood == "uneasy"


def test_memory_sync_work_option_writes_work_scoped_wiki(tmp_path: Path) -> None:
    runner = CliRunner()
    StateManager.upsert_term(
        tmp_path,
        TermState(
            term_id=work_scoped_id("Glass Blade", "glass_join"),
            term_jp="glass join",
            term_zh="glass mending",
        ),
    )

    result = runner.invoke(
        main,
        ["memory", "sync", str(tmp_path), "--work", "Glass Blade"],
    )

    assert result.exit_code == 0, result.output
    assert "Wiki synced for work Glass Blade" in result.output
    assert (tmp_path / "memory" / "terms" / "glass-blade" / "glass_join.md").exists()
