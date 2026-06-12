"""Distill CLI commands for exporting/importing community formats."""

from __future__ import annotations

from pathlib import Path

import click

from mga.distill import (
    CharacterCardExporter,
    LorebookExporter,
    CharacterCardImporter,
    LorebookImporter,
)


@click.group(name="distill")
def distill_group():
    """Knowledge distillation commands - export/import community formats."""
    pass


# ── Export commands ────────────────────────────────────────────────────────────


@distill_group.command("export")
@click.argument("project_dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--format",
    "export_format",
    type=click.Choice(["character-card", "lorebook", "all"]),
    default="all",
    help="Export format",
)
@click.option("-o", "--output-dir", type=click.Path(path_type=Path), required=True)
@click.option("--file-format", type=click.Choice(["json", "toml"]), default="json")
def distill_export(project_dir: Path, export_format: str, output_dir: Path, file_format: str):
    """Export memory to community formats.

    PROJECT_DIR: Project directory containing memory/ state
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    if export_format in ("character-card", "all"):
        _export_character_cards(project_dir, output_dir, file_format)

    if export_format in ("lorebook", "all"):
        _export_lorebook(project_dir, output_dir, file_format)

    click.echo(f"Export complete: {output_dir}")


def _export_character_cards(project_dir: Path, output_dir: Path, file_format: str):
    """Export character cards."""
    cards_dir = output_dir / "character_cards"
    exporter = CharacterCardExporter(project_dir)

    saved = exporter.save(cards_dir, format=file_format)
    click.echo(f"  Character cards: {len(saved)} files")


def _export_lorebook(project_dir: Path, output_dir: Path, file_format: str):
    """Export lorebook."""
    lorebook_path = output_dir / f"lorebook.{file_format}"
    exporter = LorebookExporter(project_dir)
    exporter.save(lorebook_path, format=file_format)
    click.echo(f"  Lorebook: {lorebook_path}")


# ── Import commands ────────────────────────────────────────────────────────────


@distill_group.command("import")
@click.argument("project_dir", type=click.Path(path_type=Path))
@click.argument("input_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "import_format",
    type=click.Choice(["character-card", "lorebook", "auto"]),
    default="auto",
    help="Input format (auto-detect from file)",
)
def distill_import(project_dir: Path, input_path: Path, import_format: str):
    """Import community formats into memory.

    PROJECT_DIR: Target project directory
    INPUT_PATH: Character card file, lorebook file, or directory
    """
    if import_format == "auto":
        import_format = _detect_format(input_path)

    if import_format == "character-card":
        _import_character_cards(project_dir, input_path)
    elif import_format == "lorebook":
        _import_lorebook(project_dir, input_path)
    else:
        raise click.ClickException(f"Unknown format: {import_format}")


def _detect_format(input_path: Path) -> str:
    """Auto-detect format from file content."""
    import json

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
        # Lorebook has 'entries' array
        if "entries" in data:
            return "lorebook"
        # Character card has 'name' and 'description'
        if "name" in data and "description" in data:
            return "character-card"
    except json.JSONDecodeError:
        pass

    # Check by file pattern
    if input_path.name.endswith(".json"):
        # Try to parse as character card
        try:
            data = json.loads(input_path.read_text(encoding="utf-8"))
            if "name" in data:
                return "character-card"
        except Exception:
            pass

    return "lorebook"  # Default


def _import_character_cards(project_dir: Path, input_path: Path):
    """Import character cards."""
    importer = CharacterCardImporter(project_dir)

    if input_path.is_dir():
        profiles = importer.import_directory(input_path)
        click.echo(f"Imported {len(profiles)} character cards")
    else:
        profile = importer.import_card(input_path)
        click.echo(f"Imported: {profile.name_zh or profile.character_id}")


def _import_lorebook(project_dir: Path, input_path: Path):
    """Import lorebook."""
    importer = LorebookImporter(project_dir)
    stats = importer.import_file(input_path)

    parts = []
    if stats["characters"]:
        parts.append(f"{stats['characters']} characters")
    if stats["terms"]:
        parts.append(f"{stats['terms']} terms")
    if stats["scenes"]:
        parts.append(f"{stats['scenes']} scenes")

    click.echo(f"Imported: {', '.join(parts) if parts else 'nothing'}")


# ── Info commands ──────────────────────────────────────────────────────────────


@distill_group.command("info")
@click.argument("project_dir", type=click.Path(path_type=Path), default=".")
@click.option("--format", type=click.Choice(["character-card", "lorebook"]), default=None)
def distill_info(project_dir: Path, format: str | None):
    """Show export information for project."""
    from mga.memory.service import MemoryService

    memory = MemoryService(project_dir)
    memory.initialize()

    stats = memory.get_stats()

    click.echo("Memory Statistics:")
    click.echo(f"  Characters: {stats['characters']}")
    click.echo(f"  Terms: {stats['terms']}")
    click.echo(f"  Scenes: {stats['scenes']}")
    click.echo(f"  Translation Memory: {stats['translation_memory']}")

    if format is None or format == "character-card":
        click.echo("\nCharacter Card Export:")
        click.echo(f"  Characters with profiles: {stats['characters']}")
        click.echo(f"  Output: <output_dir>/character_cards/*.json")

    if format is None or format == "lorebook":
        click.echo("\nLorebook Export:")
        click.echo(f"  Characters: {stats['characters']}")
        click.echo(f"  Terms: {stats['terms']}")
        click.echo(f"  Scenes: {stats['scenes']}")
        click.echo(f"  Output: <output_dir>/lorebook.json")