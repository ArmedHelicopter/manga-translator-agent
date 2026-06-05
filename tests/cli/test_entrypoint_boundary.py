from __future__ import annotations

from importlib import metadata


def test_installed_console_script_points_to_product_cli() -> None:
    entry_points = metadata.distribution("manga-translate-agent").entry_points
    scripts = {
        entry_point.name: entry_point.value
        for entry_point in entry_points
        if entry_point.group == "console_scripts"
    }

    assert scripts["manga-translate"] == "mga.cli.main:main"


def test_compatibility_cli_remains_separate_from_product_entrypoint() -> None:
    from manga_translate.cli import main as compat_main
    from mga.cli.main import translate as product_main

    assert product_main.name == "translate"
    assert compat_main.name == "main"
    assert product_main is not compat_main
