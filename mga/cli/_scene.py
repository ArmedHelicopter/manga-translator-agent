"""Scene management CLI commands."""

from __future__ import annotations

from pathlib import Path

import click

from mga.memory.entities import SceneState
from mga.memory.state import StateManager


@click.group(name="scene")
def scene_group():
    """Manage scene context memory (description, mood, characters)."""
    pass


@scene_group.command(name="edit")
@click.argument("project_dir", type=click.Path(path_type=Path), default=Path("."))
@click.argument("scene_id")
@click.option("--chapter", type=int, default=None)
@click.option("--page", type=int, default=None)
@click.option("--description", "scene_description", default=None)
@click.option("--mood", default=None)
@click.option("--summary", "narrative_summary", default=None, help="Narrative summary")
@click.option("--narrative-summary", "narrative_summary", default=None, help="Narrative summary")
@click.option("--characters", default=None, help="Comma-separated character IDs")
@click.option("--character", "characters_extra", multiple=True, default=(), help="Add a character (can be repeated)")
@click.option("--key-dialogue", "key_dialogue", default=None, help="Comma-separated lines")
@click.option("--relationship-change", "relationship_changes", multiple=True, default=(), help="Add a relationship change (can be repeated)")
@click.option("--future-impact", "future_impact", default=None)
def scene_edit(
    project_dir: Path,
    scene_id: str,
    chapter: int | None,
    page: int | None,
    scene_description: str | None,
    mood: str | None,
    narrative_summary: str | None,
    characters: str | None,
    characters_extra: tuple[str, ...],
    key_dialogue: str | None,
    relationship_changes: tuple[str, ...],
    future_impact: str | None,
):
    """Create or update a scene context entry."""
    existing = StateManager.get_scene(project_dir, scene_id)
    scene = existing or SceneState(scene_id=scene_id)

    if chapter is not None:
        scene.chapter = chapter
    if page is not None:
        scene.page = page
    if scene_description is not None:
        scene.scene_description = scene_description
    if mood is not None:
        scene.mood = mood
    if narrative_summary is not None:
        scene.narrative_summary = narrative_summary
    if characters is not None:
        scene.characters = [c.strip() for c in characters.split(",") if c.strip()]
    if characters_extra:
        seen = set(scene.characters)
        scene.characters = scene.characters + [c for c in characters_extra if c not in seen]
    if relationship_changes:
        scene.relationship_changes = list(relationship_changes)
    if key_dialogue is not None:
        scene.key_dialogue = [d.strip() for d in key_dialogue.split("|") if d.strip()]
    if future_impact is not None:
        scene.future_impact = future_impact

    StateManager.upsert_scene(project_dir, scene)
    click.echo(f"Scene saved: {scene_id}")


@scene_group.command(name="list")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path), default=Path("."))
def scene_list(project_dir: Path):
    """List all recorded scenes."""
    scenes = StateManager.list_scenes(project_dir)
    if not scenes:
        click.echo("No scenes recorded.")
        return
    for s in scenes:
        loc = f"ch{s.chapter} p{s.page}" if s.chapter else s.scene_id
        click.echo(f"  {s.scene_id}: {loc} ({s.mood}) {s.scene_description}")