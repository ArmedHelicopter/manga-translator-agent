"""Profile commands for CLI."""

from __future__ import annotations

from pathlib import Path

import click


@click.group(name="profile")
def profile_group():
    """Character profile commands."""
    pass


@profile_group.command("list")
@click.argument("project_dir", required=False, type=click.Path(path_type=Path), default=Path("."))
@click.option("--work", default=None, help="Filter by work namespace")
def profile_list(project_dir: Path, work: str | None):
    """List all character profiles."""
    from mga.memory.profile_loader import load_all_profiles

    profiles = load_all_profiles(project_dir, work=work)
    if not profiles:
        click.echo("No profiles found.")
        return
    for character_id, profile in sorted(profiles.items()):
        name_jp = profile.name_jp or ""
        name_zh = profile.name_zh or ""
        name_part = f"{name_jp} / {name_zh}" if name_jp and name_zh else (name_jp or name_zh)
        click.echo(f"  {character_id}: {name_part}")


@profile_group.command("show")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("character_id")
def profile_show(project_dir: Path, character_id: str):
    """Show full profile for a character."""
    from mga.memory.profile_loader import load_character_profile

    profile = load_character_profile(project_dir, character_id)
    if not profile:
        raise click.ClickException(f"No profile for {character_id}")
    import json
    click.echo(json.dumps(profile, ensure_ascii=False, indent=2))


@profile_group.command("edit")
@click.argument("project_dir", type=click.Path(path_type=Path))
@click.argument("character_id")
@click.option("--name-jp", default=None)
@click.option("--name-zh", default=None)
@click.option("--archetype", default=None)
@click.option("--catchphrase", multiple=True, help="Add catchphrase (repeatable)")
@click.option("--speech-pattern", "speech_patterns", multiple=True, help="key=value pair")
@click.option("--tone", "tone_spectrum", multiple=True, help="key=value pair")
@click.option("--translation-note", "translation_notes_opt", multiple=True, help="key=value pair")
@click.option("--note", "notes", multiple=True, help="key=value pair (alias for --translation-note)")
@click.option("--work", default=None, help="Work namespace for profile")
def profile_edit(
    project_dir: Path,
    character_id: str,
    name_jp: str | None,
    name_zh: str | None,
    archetype: str | None,
    catchphrase: tuple[str, ...],
    speech_patterns: tuple[str, ...],
    tone_spectrum: tuple[str, ...],
    translation_notes_opt: tuple[str, ...],
    notes: tuple[str, ...],
    work: str | None,
):
    """Create or update a character profile."""
    from mga.memory.entities import CharacterState
    from mga.memory.state import StateManager

    char_state = StateManager.get_character(project_dir, character_id) or CharacterState(character_id=character_id)
    updates: dict = {}
    if name_jp is not None:
        updates["name_jp"] = name_jp
    if name_zh is not None:
        updates["name_zh"] = name_zh
    if archetype is not None:
        updates["archetype"] = archetype
    if catchphrase:
        existing = list(char_state.catchphrases) if char_state.catchphrases else []
        for cp in catchphrase:
            if cp not in existing:
                existing.append(cp)
        updates["catchphrases"] = existing
    if speech_patterns:
        for pair in speech_patterns:
            if "=" not in pair:
                raise click.ClickException("--speech-pattern must use key=value")
            k, v = pair.split("=", 1)
            k, v = k.strip(), v.strip()
            if not k:
                raise click.ClickException("--speech-pattern key cannot be empty")
            existing_sp = dict(char_state.speech_patterns) if char_state.speech_patterns else {}
            existing_sp[k] = v
            updates["speech_patterns"] = existing_sp
    if tone_spectrum:
        for pair in tone_spectrum:
            if "=" not in pair:
                raise click.ClickException("--tone must use key=value")
            k, v = pair.split("=", 1)
            k, v = k.strip(), v.strip()
            if not k:
                raise click.ClickException("--tone key cannot be empty")
            existing_tone = dict(char_state.tone_spectrum) if char_state.tone_spectrum else {}
            existing_tone[k] = v
            updates["tone_spectrum"] = existing_tone
    # Combine --translation-note and --note
    all_notes = list(translation_notes_opt) + list(notes)
    if all_notes:
        for pair in all_notes:
            if "=" not in pair:
                raise click.ClickException("--translation-note must use key=value")
            k, v = pair.split("=", 1)
            k, v = k.strip(), v.strip()
            if not k:
                raise click.ClickException("--translation-note key cannot be empty")
            existing_notes = dict(char_state.translation_notes) if char_state.translation_notes else {}
            existing_notes[k] = v
            updates["translation_notes"] = existing_notes

    for field, value in updates.items():
        setattr(char_state, field, value)

    StateManager.upsert_character(project_dir, char_state)
    click.echo(f"Profile saved: {character_id}")


@profile_group.command("export")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("character_id", required=False)
@click.option("--work", default=None, help="Filter by work namespace")
def profile_export(project_dir: Path, character_id: str | None, work: str | None):
    """Export character profile(s) to TOML. Without character_id, exports all."""
    import toml

    from mga.memory.profile_loader import load_all_profiles, load_character_profile

    if character_id:
        profile = load_character_profile(project_dir, character_id)
        if not profile:
            raise click.ClickException(f"No profile for {character_id}")
        # Write to character_profiles dir
        out_dir = project_dir / "character_profiles"
        if work:
            out_dir = out_dir / work
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / f"{character_id}.toml"
        out_file.write_text(toml.dumps(profile.model_dump()), encoding="utf-8")
        click.echo(f"Profile exported: {out_file}")
    else:
        profiles = load_all_profiles(project_dir)
        count = 0
        for char_id, profile in profiles.items():
            out_dir = project_dir / "character_profiles"
            if work:
                out_dir = out_dir / work
            out_dir.mkdir(parents=True, exist_ok=True)
            out_file = out_dir / f"{char_id}.toml"
            out_file.write_text(toml.dumps(profile.model_dump()), encoding="utf-8")
            count += 1
        click.echo(f"Profiles exported: {count} profiles")


@profile_group.command("import")
@click.argument("project_dir", type=click.Path(path_type=Path))
@click.argument("input_file", required=False, type=click.Path(path_type=Path))
def profile_import(project_dir: Path, input_file: Path | None):
    """Import character profile(s) from TOML. Without INPUT_FILE, imports from PROJECT_DIR."""
    import toml

    from mga.memory.entities import CharacterState
    from mga.memory.state import StateManager

    # Default: import from project_dir itself
    if input_file is None:
        input_file = project_dir

    # Single file import
    if input_file.is_file():
        data = toml.loads(input_file.read_text(encoding="utf-8"))
        char_state = CharacterState(**data)
        StateManager.upsert_character(project_dir, char_state)
        click.echo(f"Profile imported: {char_state.character_id}")
        return

    # Directory import (batch)
    if not input_file.is_dir():
        raise click.ClickException(f"Input path must be a file or directory: {input_file}")
    count = 0
    for toml_file in input_file.rglob("*.toml"):
        try:
            data = toml.loads(toml_file.read_text(encoding="utf-8"))
            char_state = CharacterState(**data)
            StateManager.upsert_character(project_dir, char_state)
            count += 1
        except Exception as e:
            click.echo(f"Warning: skipped {toml_file}: {e}", err=True)
    click.echo(f"Profiles imported: {count} profiles")


# Also expose as top-level commands
profile = profile_group