"""Memory management commands for CLI."""

from __future__ import annotations

from pathlib import Path

import click


@click.group(name="memory")
def memory_group():
    """Memory/wiki management commands."""
    pass


@memory_group.command("init")
@click.argument("project_dir", type=click.Path(path_type=Path), default=".")
def memory_init(project_dir: Path):
    """Initialize memory/wiki structure in project directory."""
    from mga.memory.state import StateManager
    p = project_dir
    StateManager.load(p)  # This ensures directories exist
    click.echo(f"Memory initialized at {p / 'memory' / 'state'}")


@memory_group.command("sync")
@click.argument("project_dir", type=click.Path(path_type=Path), default=".")
@click.option("--dry-run", is_flag=True, help="Show changes without applying")
@click.option(
    "--direction",
    type=click.Choice(["state-to-wiki", "wiki-to-state"]),
    default="state-to-wiki",
    show_default=True,
)
@click.option("--work", default=None, help="Optional work/series namespace")
def memory_sync(project_dir: Path, dry_run: bool, direction: str, work: str | None):
    """Sync memory state with wiki projections."""
    from mga.memory.sync import state_to_wiki, wiki_to_state

    if dry_run:
        click.echo("[DRY RUN] Would sync wiki ↔ state")
        return

    if direction == "wiki-to-state":
        wiki_to_state(Path(project_dir), work=work)
        scope = f" for work {work}" if work else ""
        click.echo(f"State synced from wiki{scope}")
        return

    state_to_wiki(Path(project_dir), work=work)
    scope = f" for work {work}" if work else ""
    click.echo(f"Wiki synced{scope}")


@memory_group.command("status")
@click.argument("project_dir", type=click.Path(path_type=Path), default=".")
def memory_status(project_dir: Path):
    """Show memory state summary."""
    from mga.memory import StateManager

    state_dir = project_dir / "memory" / "state"
    if not state_dir.exists():
        click.echo("Memory not initialized")
        return

    characters = StateManager.list_characters(project_dir)
    terms = StateManager.list_terms(project_dir)
    scenes = StateManager.list_scenes(project_dir)

    click.echo(f"Characters: {len(characters)}")
    click.echo(f"Terms: {len(terms)}")
    click.echo(f"Scenes: {len(scenes)}")


@memory_group.command("export")
@click.argument("project_dir", type=click.Path(path_type=Path), default=".")
@click.argument("output_dir", type=click.Path(path_type=Path))
def memory_export(project_dir: Path, output_dir: Path):
    """Export memory state as JSON."""
    import json

    from mga.memory import MemoryIndex

    index = MemoryIndex.load(project_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "memory_index.json"
    output_path.write_text(json.dumps(index.model_dump(), ensure_ascii=False, indent=2))
    click.echo(f"Exported: {output_path}")


@memory_group.command("import")
@click.argument("project_dir", type=click.Path(path_type=Path))
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
def memory_import(project_dir: Path, input_file: Path):
    """Import memory state from JSON."""
    import json

    from mga.memory import MemoryIndex

    data = json.loads(input_file.read_text(encoding="utf-8"))
    index = MemoryIndex(**data)
    index.save(project_dir)
    click.echo(f"Imported: {input_file}")


# Profile commands
_profile_group = click.Group(name="profile")
memory_group.add_command(_profile_group, name="profile")


@_profile_group.command("list")
@click.argument("project_dir", type=click.Path(path_type=Path))
def profile_list(project_dir: Path):
    """List all character profiles."""
    from mga.memory import load_all_profiles

    profiles = load_all_profiles(project_dir)
    for profile in profiles:
        name = profile.get("name_zh") or profile.get("name_jp", "unknown")
        arch = profile.get("archetype", "unknown")
        click.echo(f"  {name} [{arch}]")


@_profile_group.command("show")
@click.argument("project_dir", type=click.Path(path_type=Path))
@click.argument("character_id")
def profile_show(project_dir: Path, character_id: str):
    """Show detailed profile for a character."""
    import json

    from mga.memory import load_character_profile

    profile = load_character_profile(project_dir, character_id)
    if profile is None:
        click.echo(f"Profile not found: {character_id}", err=True)
        raise SystemExit(1)
    click.echo(json.dumps(profile, ensure_ascii=False, indent=2))


@_profile_group.command("export")
@click.argument("project_dir", type=click.Path(path_type=Path))
@click.argument("output_dir", type=click.Path(path_type=Path))
def profile_export(project_dir: Path, output_dir: Path):
    """Export all profiles to a directory."""
    from mga.memory import load_all_profiles

    import shutil

    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = project_dir / "character_profiles"

    count = 0
    if source_dir.exists():
        for src in sorted(source_dir.rglob("*.toml")):
            rel = src.relative_to(source_dir)
            dst = output_dir / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            count += 1

    click.echo(f"Exported {count} profiles: {output_dir}")


# Term commands
_term_group = click.Group(name="term")
memory_group.add_command(_term_group, name="term")


@_term_group.command("list")
@click.argument("project_dir", type=click.Path(path_type=Path))
@click.option("--work", help="Filter by work ID")
def term_list(project_dir: Path, work: str | None):
    """List terminology database entries."""
    from mga.memory import StateManager

    terms = StateManager.list_terms(project_dir)
    if work:
        terms = [t for t in terms if t.work_id == work]

    for term in terms:
        grade = term.grade.value if hasattr(term.grade, 'value') else term.grade
        click.echo(f"  {term.source} → {term.target} [{grade}]")


@_term_group.command("add")
@click.argument("project_dir", type=click.Path(path_type=Path))
@click.argument("source")
@click.argument("target")
@click.option("--work", default="default", help="Work ID")
@click.option("--grade", type=int, default=3, help="Term grade (1-7)")
def term_add(project_dir: Path, source: str, target: str, work: str, grade: int):
    """Add a terminology entry."""
    from mga.memory.entities import TermState
    from mga.memory.state import StateManager
    from mga.cultural import TermGrade

    grade_map = {1: TermGrade.G1_UNIVERSAL, 2: TermGrade.G2_STANDARD,
                 3: TermGrade.G3_CONTEXT, 4: TermGrade.G4_CULTURAL,
                 5: TermGrade.G5_NEOLOGISM, 6: TermGrade.G6_SPECIFIC,
                 7: TermGrade.G7_FICTIONAL}
    term_grade = grade_map.get(grade, TermGrade.G3_CONTEXT)

    term = TermState(source=source, target=target, work_id=work, grade=term_grade)
    StateManager.upsert_term(project_dir, term)
    click.echo(f"Added: {source} → {target}")


@_term_group.command("import")
@click.argument("project_dir", type=click.Path(path_type=Path))
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
def term_import(project_dir: Path, input_file: Path):
    """Import terms from CSV/JSON file."""
    import json

    from mga.memory.state import StateManager

    data = json.loads(input_file.read_text(encoding="utf-8"))
    count = 0
    for entry in data:
        from mga.memory.entities import TermState
        from mga.memory.state import StateManager

        term = TermState(**entry)
        StateManager.upsert_term(project_dir, term)
        count += 1

    click.echo(f"Imported {count} terms: {input_file}")


@_term_group.command("export")
@click.argument("project_dir", type=click.Path(path_type=Path))
@click.argument("output_file", type=click.Path(path_type=Path))
def term_export(project_dir: Path, output_file: Path):
    """Export terms to JSON file."""
    import json

    from mga.memory import StateManager

    terms = StateManager.list_terms(project_dir)
    data = [t.model_dump() for t in terms]
    output_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"Exported {len(terms)} terms: {output_file}")