"""MGA CLI entrypoint -- Click commands for translation, benchmark, memory, and review."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click

logger = logging.getLogger("mga.cli")


def _seed_memory(
    learn_dir: Path,
    project_dir: Path,
    mode: str = "auto",
    provider=None,
) -> None:
    """Run the LearningEngine to extract and seed memory from *learn_dir*."""
    from mga.learning.engine import LearningEngine

    engine = LearningEngine(project_dir, provider=provider)
    result = engine.learn(learn_dir, mode=mode)
    click.echo(
        f"Learning complete: {len(result.characters)} characters, "
        f"{len(result.terms)} terms"
    )


def _export_learned_profiles(project_dir: Path, output_profiles: Path) -> int:
    """Copy learned character profile TOML files to an explicit output directory."""
    import shutil

    source_dir = project_dir / "character_profiles"
    output_profiles.mkdir(parents=True, exist_ok=True)
    count = 0
    for source_path in sorted(source_dir.rglob("*.toml")) if source_dir.exists() else []:
        relative_path = source_path.relative_to(source_dir)
        target_path = output_profiles / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, target_path)
        count += 1
    return count


def _resolve_provider(cfg, stage: str = "vision"):
    route = cfg.provider_routes.get(stage)
    name = route.primary.provider if route and route.primary.provider else "openai"
    return name, cfg.provider_settings.get(name, {})


def _resolve_stage_provider(cfg, stage: str = "vision"):
    from mga.providers import ProviderCascade, ProviderCascadeAdapter, get_provider

    cascade = ProviderCascade(cfg, stage)
    if not cascade.candidates:
        raise click.ClickException(f"No provider configured for stage '{stage}'.")

    errors: list[dict[str, str]] = []
    providers = []
    for candidate in cascade.candidates:
        try:
            providers.append((candidate, get_provider(candidate.provider, **(candidate.settings or {}))))
        except Exception as exc:  # noqa: BLE001 - benchmark fallback should continue through candidates.
            errors.append({
                "role": candidate.role,
                "provider": candidate.provider,
                "error": str(exc),
                "type": type(exc).__name__,
            })
    if len(providers) == 1:
        return providers[0][1]
    if providers:
        return ProviderCascadeAdapter(cascade, providers)
    raise click.ClickException(f"Provider unavailable for stage '{stage}': {errors}")


def _resolve_translation_provider(cfg) -> tuple[str, dict]:
    """Resolve provider/settings for translation stage with compatibility keys."""
    route = cfg.provider_routes.get("translation") or cfg.provider_routes.get("translate")
    if route and route.primary.provider:
        name = route.primary.provider
        settings = dict(cfg.provider_settings.get(name, {}))
        if route.primary.model and "model" not in settings:
            settings["model"] = route.primary.model
        return name, settings
    return "openai", dict(cfg.provider_settings.get("openai", {}))


def _resolve_learning_provider(cfg):
    from mga.providers import ProviderCascade, ProviderCascadeAdapter

    stage = "vision" if cfg.pipeline_mode == "manga" else "translation"
    cascade = ProviderCascade(cfg, stage)
    if not cascade.candidates:
        return None
    from mga.providers import get_provider

    errors: list[dict[str, str]] = []
    providers = []
    for candidate in cascade.candidates:
        try:
            providers.append((candidate, get_provider(candidate.provider, **(candidate.settings or {}))))
        except Exception as exc:  # noqa: BLE001 - continue through configured fallback candidates.
            errors.append({
                "role": candidate.role,
                "provider": candidate.provider,
                "error": str(exc),
                "type": type(exc).__name__,
            })
    if not providers:
        raise click.ClickException(f"Learning provider unavailable: {errors}")
    if len(providers) == 1:
        return providers[0][1]
    return ProviderCascadeAdapter(cascade, providers)


def _check_translation_provider_connectivity(cfg) -> None:
    """Run a lightweight provider connectivity check before starting pipeline."""
    from mga.providers import ProviderCascade

    cascade = ProviderCascade(cfg, "translation")
    try:
        _raw, candidate = cascade.call_chat(
            [{"role": "user", "content": "Reply with OK."}],
            temperature=0.0,
            max_tokens=8,
        )
    except Exception as exc:
        raise click.ClickException(
            f"Provider pre-check failed: {exc}; cascade_errors={cascade.errors}"
        ) from exc
    logger.info("Provider pre-check succeeded with %s", candidate.provider)


def _check_vision_provider_capability(cfg, auto_vision_model: bool = False) -> None:
    """Probe the vision-stage cascade with a 1px image; fail fast on rejection.

    With *auto_vision_model* set, a primary route whose model rejects images is
    switched (in-memory) to a vision-capable sibling model on the same
    provider/key instead of aborting.
    """
    from mga.providers.cascade import resolve_provider_candidates
    from mga.providers.factory import create_provider
    from mga.providers.vision_probe import (
        discover_vision_models,
        is_image_rejection_error,
        probe_vision,
    )

    candidates = list(resolve_provider_candidates(cfg, "vision"))
    if not candidates:
        return

    probe_errors: list[str] = []
    rejected: list = []
    for candidate in candidates:
        try:
            provider = create_provider(candidate.provider, candidate.settings or {})
        except Exception as exc:  # noqa: BLE001 - connectivity issues surface later in cascade.
            probe_errors.append(f"{candidate.role}/{candidate.provider}: {exc}")
            continue
        ok, err = probe_vision(provider)
        if ok:
            logger.info(
                "Vision pre-check succeeded with %s (%s)",
                candidate.provider,
                getattr(provider, "model_name", ""),
            )
            return
        probe_errors.append(f"{candidate.role}/{candidate.provider}: {err}")
        if is_image_rejection_error(err):
            rejected.append(candidate)

    if not rejected:
        # No candidate explicitly rejected images — likely transient/auth issues.
        # Leave it to the pipeline cascade rather than blocking the run here.
        logger.warning("Vision pre-check inconclusive: %s", probe_errors)
        return

    candidate = rejected[0]
    settings = dict(candidate.settings or {})
    configured_model = str(
        settings.get("vision_model") or settings.get("model") or candidate.model or ""
    )
    click.echo(
        f"Vision pre-check: model '{configured_model}' on provider "
        f"'{candidate.provider}' rejects image input.",
        err=True,
    )
    click.echo("Vision pre-check: probing sibling models on the same provider/key...", err=True)
    suggestions = discover_vision_models(
        candidate.provider, settings, current_model=configured_model
    )

    if auto_vision_model and suggestions:
        chosen = suggestions[0]
        stage_cfg = cfg.provider_routes.get("vision")
        if stage_cfg is not None and stage_cfg.primary.provider == candidate.provider:
            stage_cfg.primary.model = chosen
        provider_settings = dict(cfg.provider_settings.get(candidate.provider, {}))
        provider_settings["vision_model"] = chosen
        cfg.provider_settings[candidate.provider] = provider_settings
        click.echo(
            f"Vision pre-check: auto-switched vision model to '{chosen}' "
            f"(--auto-vision-model). Update your config to make this permanent.",
            err=True,
        )
        return

    lines = [
        f"Vision pre-check failed: model '{configured_model}' on provider "
        f"'{candidate.provider}' does not accept image input, so vision "
        "enrichment would silently add 0 bubbles.",
    ]
    if suggestions:
        lines.append(
            f"Vision-capable models available with the same API key: {', '.join(suggestions)}."
        )
        lines.append(
            f"Fix: set vision_model = \"{suggestions[0]}\" under "
            f"[providers.{candidate.provider}] in your config, or rerun with "
            "--auto-vision-model to switch automatically for this run."
        )
    else:
        lines.append(
            "No vision-capable sibling model was found on this provider. "
            "Configure a vision-capable provider for [stages.vision] "
            "(e.g. openai/gpt-4o, gemini, openrouter) or use --auto-vision-model "
            "after adding one."
        )
    raise click.ClickException("\n".join(lines))


_NOVEL_EXTENSIONS = {".epub", ".txt", ".mobi"}
_MANGA_FILE_EXTENSIONS = {".pdf", ".epub", ".cbz", ".cbr", ".mobi"}
_AUTO_MANGA_FILE_EXTENSIONS = {".pdf", ".cbz", ".cbr"}


def _detect_mode(input_path: str, mode: str | None) -> tuple[str, str]:
    """Detect pipeline mode and input format from file extension.

    Returns (pipeline_mode, input_format).
    """
    if mode == "novel":
        return "novel", Path(input_path).suffix.lstrip(".").lower()
    if mode == "manga":
        ext = Path(input_path).suffix.lower()
        if ext in _MANGA_FILE_EXTENSIONS:
            return "manga", ext.lstrip(".")
        return "manga", "images"
    # Auto-detect: novel extensions -> novel mode
    ext = Path(input_path).suffix.lower()
    if ext in _NOVEL_EXTENSIONS:
        return "novel", ext.lstrip(".")
    if ext in _AUTO_MANGA_FILE_EXTENSIONS:
        return "manga", ext.lstrip(".")
    return "manga", "images"


def _parse_key_value_options(values: tuple[str, ...], option_name: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise click.ClickException(f"{option_name} must use key=value: {value}")
        key, item_value = value.split("=", 1)
        key = key.strip()
        if not key:
            raise click.ClickException(f"{option_name} key cannot be empty: {value}")
        parsed[key] = item_value.strip()
    return parsed


def _stringify_profile_mapping(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    parsed: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, list):
            parsed[str(key)] = ", ".join(str(item) for item in value)
        else:
            parsed[str(key)] = str(value)
    return parsed


def _profile_catchphrases(raw: object) -> list[str]:
    if isinstance(raw, dict):
        raw = raw.get("patterns", [])
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str) and raw:
        return [raw]
    return []


@click.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("-o", "--output-path", required=True, type=click.Path())
@click.option("--provider", default=None)
@click.option("--format", "output_format", default=None)
@click.option("--mode", type=click.Choice(["manga", "novel"]), default=None)
@click.option("--learn-from", default=None, type=click.Path(exists=True))
@click.option("--learn-only", is_flag=True)
@click.option(
    "--output-profiles",
    default=None,
    type=click.Path(),
    help="Copy learned character_profiles/*.toml to this directory after learning.",
)
@click.option("--lang", default="ja-zh")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
@click.option("--save-json", is_flag=True, help="Save full translation report and debug artifacts.")
@click.option("--bilingual", is_flag=True, help="Output bilingual PDF (original + translation side-by-side).")
@click.option("--incremental", is_flag=True, help="Load prior project memory and update it after this chapter.")
@click.option("--chapter-id", default="", help="Chapter id for incremental memory updates.")
@click.option("--dry-run", is_flag=True)
@click.option("-v", "--verbose", is_flag=True, help="Verbose output.")
@click.option(
    "--artifact-payload-dir",
    default=None,
    type=click.Path(exists=True),
    help="Reuse an existing runtime payload directory and skip Pass 1 export.",
)
@click.option(
    "--parallel-mode",
    type=click.Choice(["serial", "parallel", "pipelined"]),
    default=None,
    help="Pipeline parallelism mode (default: serial).",
)
@click.option(
    "--concurrency",
    default=None,
    type=int,
    help="Max pages in flight for parallel/pipelined mode (default: 5).",
)
@click.option(
    "--auto-vision-model",
    is_flag=True,
    help="If the configured vision model rejects image input, automatically "
    "switch to a vision-capable model on the same provider/key for this run.",
)
def translate(
    input_path, output_path, provider, output_format, mode, learn_from, learn_only,
    output_profiles, lang, config_path, save_json, bilingual, incremental, chapter_id, dry_run,
    verbose, artifact_payload_dir, parallel_mode, concurrency, auto_vision_model,
):
    """Run the translation pipeline on INPUT_PATH."""
    from mga.config.loader import build_project_config
    from mga.pipeline.orchestrator import PipelineOrchestrator

    if verbose:
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger("mga").setLevel(logging.DEBUG)

    parts = lang.split("-", 1)
    src, tgt = parts[0] if parts else "ja", parts[1] if len(parts) > 1 else "zh-CN"
    pipeline_mode, detected_format = _detect_mode(input_path, mode)
    cfg, _ = build_project_config(
        input_path=input_path, output_path=output_path,
        provider_override=provider, save_json=False, dry_run=dry_run, config_path=config_path,
    )
    cfg.source_lang, cfg.target_lang = src, tgt
    cfg.pipeline_mode = pipeline_mode
    cfg.save_artifacts = save_json
    if parallel_mode:
        cfg.parallel_mode = parallel_mode
    if concurrency is not None:
        cfg.pipeline_concurrency = concurrency
    if output_format:
        cfg.output_format = output_format
    elif pipeline_mode == "novel":
        cfg.output_format = detected_format
    else:
        cfg.output_format = "images"
    cfg.input_format = detected_format
    if bilingual:
        cfg.output_format = "bilingual"

    effective_learn_from = learn_from or (input_path if learn_only else None)
    if effective_learn_from:
        _seed_memory(
            Path(effective_learn_from),
            Path(cfg.working_dir),
            mode=pipeline_mode,
            provider=_resolve_learning_provider(cfg),
        )
        if output_profiles:
            count = _export_learned_profiles(Path(cfg.working_dir), Path(output_profiles))
            click.echo(f"Profiles exported: {count} profiles")
        if learn_only:
            click.echo("Memory seeded. --learn-only set, skipping translation.")
            return
    if dry_run:
        click.echo(f"Dry run:\n{cfg.model_dump_json(indent=2)}")
        return

    mode_label = f" ({pipeline_mode} mode)" if pipeline_mode == "novel" else ""
    click.echo(f"Translating{mode_label} {input_path} -> {output_path}  ({src} -> {tgt})")

    # Two-pass mode: export artifact from runtime, then run intelligence pipeline
    pipeline_metadata: dict = {}
    if pipeline_mode == "manga":
        click.echo("Provider pre-check: testing translation provider connectivity...")
        _check_translation_provider_connectivity(cfg)
        click.echo("Provider pre-check: OK")
        click.echo("Vision pre-check: testing image input capability...")
        _check_vision_provider_capability(cfg, auto_vision_model=auto_vision_model)
        click.echo("Vision pre-check: OK")
        if artifact_payload_dir:
            payload_dir = Path(artifact_payload_dir).resolve()
            pipeline_metadata["artifact_payload_dir"] = str(payload_dir)
            click.echo(f"Pass 1 skipped. Reusing runtime payload: {payload_dir}")
        else:
            try:
                from mga.runtime_bridge.external import run_export_artifact
                payload_dir = Path(output_path) / ".mga-payload"
                click.echo(f"Pass 1: Exporting runtime artifact to {payload_dir}")
                run_export_artifact(
                    input_dir=Path(input_path),
                    payload_dir=payload_dir,
                )
                pipeline_metadata["artifact_payload_dir"] = str(payload_dir)
                click.echo("Pass 1 complete. Running intelligence pipeline...")
            except Exception as e:
                click.echo(f"Runtime export unavailable ({e}), falling back to LLM vision.", err=True)

    if incremental or pipeline_mode == "manga":
        from mga.pipeline.incremental import IncrementalTranslator

        effective_chapter_id = chapter_id or Path(input_path).stem or Path(input_path).name
        ctx = IncrementalTranslator(Path(cfg.working_dir), config=cfg).translate_chapter(
            input_path,
            output_path,
            effective_chapter_id,
            metadata=pipeline_metadata or None,
        )
        click.echo(f"Incremental translation complete: {effective_chapter_id}")
    else:
        ctx = PipelineOrchestrator(config=cfg).run(
            input_path,
            output_path,
            cfg,
            metadata=pipeline_metadata,
        )
    out = Path(output_path)
    if pipeline_mode == "novel":
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        out.mkdir(parents=True, exist_ok=True)
    # run.json is now written by OutputStage via ArtifactStore — no duplicate write here
    run_dir = out if pipeline_mode == "manga" else out.parent
    click.echo(f"Done. run.json -> {run_dir / 'run.json'}")
    for err in ctx.errors:
        click.echo(f"  [!] {err['stage']}: {err['error']}", err=True)
    if ctx.errors:
        first_error = ctx.errors[0]
        raise click.ClickException(
            f"Pipeline aborted at stage '{first_error['stage']}': {first_error['error']}"
        )


@click.group()
def legacy():
    """Legacy benchmark commands."""

@legacy.command("benchmark-extraction")
@click.argument("input_path", type=click.Path(exists=True))
@click.option("-o", "--output-path", required=True, type=click.Path())
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
def legacy_benchmark_extraction(input_path, output_path, config_path):
    from mga.artifacts import ArtifactStore
    from mga.benchmark.evaluate import run_extraction_benchmark
    from mga.config.loader import build_project_config
    from mga.format.manifest import discover_image_paths
    from mga.models import Page, PageImage

    cfg, _ = build_project_config(
        input_path=input_path, output_path=output_path,
        provider_override=None, save_json=False, dry_run=False, config_path=config_path,
    )
    provider = _resolve_stage_provider(cfg, "vision")
    pages = [Page(page_id=f"p{i}", page_index=i, image=PageImage(path=str(p)))
             for i, p in enumerate(discover_image_paths(Path(input_path)))]
    summary = run_extraction_benchmark(
        pages=pages, provider=provider, store=ArtifactStore(Path(output_path)),
        ocr_specs=["tesseract_jpn"],
    )
    click.echo(f"Extraction benchmark complete: {summary['page_count']} pages.")


@click.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("-o", "--output-path", required=True, type=click.Path())
@click.option("--no-compare-with-internal", is_flag=True)
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
def benchmark_external(input_path, output_path, no_compare_with_internal, config_path):
    """Run the external (manga-image-translator) benchmark."""
    from mga.benchmark.external import run_manga_image_translator_baseline
    click.echo(f"Running external benchmark: {input_path} -> {output_path}")
    summary = run_manga_image_translator_baseline(
        repo_dir=None, input_dir=Path(input_path), output_dir=Path(output_path),
    )
    click.echo(json.dumps(summary, indent=2, ensure_ascii=False))


@click.group()
def memory():
    """Memory management commands."""

@memory.command("init")
@click.argument("project_dir", required=False, default=".", type=click.Path())
def memory_init(project_dir):
    from mga.memory.state import StateManager
    p = Path(project_dir); StateManager.load(p)
    click.echo(f"Memory initialized at {p / 'memory' / 'state'}")

@memory.command("sync")
@click.argument("project_dir", required=False, default=".", type=click.Path(exists=True))
@click.option(
    "--direction",
    type=click.Choice(["state-to-wiki", "wiki-to-state"]),
    default="state-to-wiki",
    show_default=True,
)
@click.option("--work", default=None, help="Optional work/series namespace for long-running projects.")
def memory_sync(project_dir, direction, work):
    from mga.memory.sync import state_to_wiki, wiki_to_state

    if direction == "wiki-to-state":
        wiki_to_state(Path(project_dir), work=work)
        scope = f" for work {work}" if work else ""
        click.echo(f"State synced from wiki{scope} at {Path(project_dir) / 'memory' / 'state'}")
        return
    state_to_wiki(Path(project_dir), work=work)
    scope = f" for work {work}" if work else ""
    click.echo(f"Wiki synced{scope} at {Path(project_dir) / 'memory'}")


@click.group()
def profile():
    """Character profile commands."""

@profile.command("list")
@click.argument("project_dir", required=False, default=".", type=click.Path(exists=True))
def profile_list(project_dir):
    from mga.memory.state import StateManager
    chars = StateManager.list_characters(Path(project_dir))
    if not chars:
        click.echo("No character profiles found."); return
    for c in chars:
        click.echo(f"  {c.character_id}: {c.name_jp} / {c.name_zh}  ({c.archetype})")


@profile.command("edit")
@click.argument("project_dir", type=click.Path())
@click.argument("character_id")
@click.option("--name-jp", default=None)
@click.option("--name-zh", default=None)
@click.option("--archetype", default=None)
@click.option("--speech-pattern", multiple=True, help="Add or update a speech pattern as key=value.")
@click.option("--tone", multiple=True, help="Add or update a tone entry as key=value.")
@click.option("--translation-note", multiple=True, help="Add or update a translation note as key=value.")
@click.option("--catchphrase", multiple=True, help="Append a catchphrase if it is not already present.")
def profile_edit(
    project_dir,
    character_id,
    name_jp,
    name_zh,
    archetype,
    speech_pattern,
    tone,
    translation_note,
    catchphrase,
):
    """Create or update a character profile."""
    from mga.memory.entities import CharacterState
    from mga.memory.state import StateManager

    project_path = Path(project_dir)
    profile_state = (
        StateManager.get_character(project_path, character_id)
        or CharacterState(character_id=character_id)
    )
    if name_jp is not None:
        profile_state.name_jp = name_jp
    if name_zh is not None:
        profile_state.name_zh = name_zh
    if archetype is not None:
        profile_state.archetype = archetype

    profile_state.speech_patterns.update(
        _parse_key_value_options(speech_pattern, "--speech-pattern")
    )
    profile_state.tone_spectrum.update(
        _parse_key_value_options(tone, "--tone")
    )
    profile_state.translation_notes.update(
        _parse_key_value_options(translation_note, "--translation-note")
    )
    for phrase in catchphrase:
        if phrase not in profile_state.catchphrases:
            profile_state.catchphrases.append(phrase)

    StateManager.upsert_character(project_path, profile_state)
    click.echo(f"Profile saved: {profile_state.character_id}")


@profile.command("export")
@click.argument("project_dir", type=click.Path(exists=True))
def profile_export(project_dir):
    """Export memory/state characters to character_profiles/*.toml."""
    import tomli_w

    from mga.memory.state import StateManager

    project_path = Path(project_dir)
    out_dir = project_path / "character_profiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for character in StateManager.list_characters(project_path):
        if not character.character_id:
            continue
        meta = {
            "character_id": character.character_id,
            "name_jp": character.name_jp,
            "name_zh": character.name_zh,
            "archetype": character.archetype,
        }
        if character.provenance:
            meta["provenance"] = character.provenance
        payload = {
            "meta": meta,
            "speech_patterns": character.speech_patterns,
            "catchphrases": {"patterns": character.catchphrases},
            "tone_spectrum": character.tone_spectrum,
            "translation_notes": character.translation_notes,
        }
        if character.voice_evolutions:
            payload["voice_evolution"] = character.voice_evolutions
        (out_dir / f"{character.character_id}.toml").write_text(
            tomli_w.dumps(payload),
            encoding="utf-8",
        )
        count += 1
    click.echo(f"Profiles exported: {count} profiles")


@profile.command("import")
@click.argument("project_dir", type=click.Path(exists=True))
def profile_import(project_dir):
    """Import character_profiles/**/*.toml into memory/state."""
    import toml

    from mga.memory.entities import CharacterState
    from mga.memory.state import StateManager

    project_path = Path(project_dir)
    profiles_dir = project_path / "character_profiles"
    count = 0
    for path in sorted(profiles_dir.rglob("*.toml")) if profiles_dir.exists() else []:
        data = toml.load(path)
        meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}
        character_id = str(
            meta.get("character_id")
            or data.get("character_id")
            or path.stem
        )
        provenance = meta.get("provenance", data.get("provenance", {}))
        if not isinstance(provenance, dict):
            provenance = {}
        voice_evolutions = data.get("voice_evolution", data.get("voice_evolutions", []))
        if not isinstance(voice_evolutions, list):
            voice_evolutions = []
        StateManager.upsert_character(
            project_path,
            CharacterState(
                character_id=character_id,
                name_jp=str(meta.get("name_jp", data.get("name_jp", ""))),
                name_zh=str(meta.get("name_zh", data.get("name_zh", ""))),
                archetype=str(meta.get("archetype", data.get("archetype", ""))),
                speech_patterns=_stringify_profile_mapping(data.get("speech_patterns", {})),
                catchphrases=_profile_catchphrases(data.get("catchphrases", [])),
                tone_spectrum=_stringify_profile_mapping(data.get("tone_spectrum", {})),
                translation_notes=_stringify_profile_mapping(data.get("translation_notes", {})),
                voice_evolutions=voice_evolutions,
                provenance=provenance,
            ),
        )
        count += 1
    click.echo(f"Profiles imported: {count} profiles")


@click.group()
def scene():
    """Scene memory commands."""


@scene.command("list")
@click.argument("project_dir", type=click.Path(exists=True))
def scene_list(project_dir):
    """List recorded scene contexts."""
    from mga.memory.state import StateManager

    scenes = StateManager.list_scenes(Path(project_dir))
    if not scenes:
        click.echo("No scene contexts found.")
        return
    for item in scenes:
        click.echo(
            f"  {item.scene_id}: ch{item.chapter} p{item.page} "
            f"({item.mood}) {item.scene_description}"
        )


@scene.command("edit")
@click.argument("project_dir", type=click.Path())
@click.argument("scene_id")
@click.option("--chapter", type=int, default=None)
@click.option("--page", type=int, default=None)
@click.option("--description", "scene_description", default=None)
@click.option("--mood", default=None)
@click.option("--narrative-summary", default=None)
@click.option("--character", multiple=True, help="Append a character id if it is not already present.")
@click.option("--relationship-change", multiple=True, help="Append a relationship change if it is not already present.")
@click.option("--key-dialogue", multiple=True, help="Append key dialogue if it is not already present.")
@click.option("--future-impact", default=None)
def scene_edit(
    project_dir,
    scene_id,
    chapter,
    page,
    scene_description,
    mood,
    narrative_summary,
    character,
    relationship_change,
    key_dialogue,
    future_impact,
):
    """Create or update a scene memory entry."""
    from mga.memory.entities import SceneState
    from mga.memory.state import StateManager

    project_path = Path(project_dir)
    scene_state = (
        StateManager.get_scene(project_path, scene_id)
        or SceneState(scene_id=scene_id)
    )
    if chapter is not None:
        scene_state.chapter = chapter
    if page is not None:
        scene_state.page = page
    if scene_description is not None:
        scene_state.scene_description = scene_description
    if mood is not None:
        scene_state.mood = mood
    if narrative_summary is not None:
        scene_state.narrative_summary = narrative_summary
    if future_impact is not None:
        scene_state.future_impact = future_impact
    for character_id in character:
        if character_id not in scene_state.characters:
            scene_state.characters.append(character_id)
    for item in relationship_change:
        if item not in scene_state.relationship_changes:
            scene_state.relationship_changes.append(item)
    for item in key_dialogue:
        if item not in scene_state.key_dialogue:
            scene_state.key_dialogue.append(item)

    StateManager.upsert_scene(project_path, scene_state)
    click.echo(f"Scene saved: {scene_state.scene_id}")


@click.group()
def term():
    """Terminology commands."""

@term.command("list")
@click.argument("project_dir", required=False, default=".", type=click.Path(exists=True))
def term_list(project_dir):
    from mga.memory.state import StateManager
    terms = StateManager.list_terms(Path(project_dir))
    if not terms:
        click.echo("No terminology entries found."); return
    for t in terms:
        click.echo(f"  {t.term_id}: {t.term_jp} -> {t.term_zh}  (freq={t.frequency})")


@term.command("edit")
@click.argument("project_dir", type=click.Path())
@click.argument("term_id")
@click.option("--term-jp", default=None)
@click.option("--term-zh", default=None)
@click.option("--context", default=None)
@click.option("--cultural-weight", default=None)
@click.option("--strategy", default=None)
@click.option("--frequency", type=int, default=None)
def term_edit(
    project_dir,
    term_id,
    term_jp,
    term_zh,
    context,
    cultural_weight,
    strategy,
    frequency,
):
    """Create or update a terminology entry."""
    from mga.memory.entities import TermState
    from mga.memory.state import StateManager

    project_path = Path(project_dir)
    term_state = (
        StateManager.get_term(project_path, term_id)
        or TermState(term_id=term_id)
    )
    if term_jp is not None:
        term_state.term_jp = term_jp
    if term_zh is not None:
        term_state.term_zh = term_zh
    if context is not None:
        term_state.context = context
    if cultural_weight is not None:
        term_state.cultural_weight = cultural_weight
    if strategy is not None:
        term_state.strategy = strategy
    if frequency is not None:
        term_state.frequency = frequency

    StateManager.upsert_term(project_path, term_state)
    click.echo(f"Term saved: {term_state.term_id}")


@term.command("export")
@click.argument("project_dir", type=click.Path(exists=True))
def term_export(project_dir):
    """Export memory/state terms to terminology/terms.toml."""
    from mga.cultural.terminology_db import TerminologyDB, TermState as TomlTermState
    from mga.memory.state import StateManager

    project_path = Path(project_dir)
    db = TerminologyDB()
    for term_state in StateManager.list_terms(project_path):
        db.register(
            TomlTermState(
                term_jp=term_state.term_jp or term_state.term_id,
                term_target=term_state.term_zh,
                candidate_translations=term_state.candidate_translations,
                strategy=term_state.strategy,
                notes=term_state.context,
                accepted_reason=term_state.accepted_reason,
                rejected_reasons=term_state.rejected_reasons,
                applicability_scope=term_state.applicability_scope,
                problem_types=[term_state.cultural_weight] if term_state.cultural_weight else [],
                confirmed=True,
            )
        )
    out_path = db.export(project_path)
    click.echo(f"Terminology exported: {out_path}")


@term.command("import")
@click.argument("project_dir", type=click.Path(exists=True))
def term_import(project_dir):
    """Import terminology/*.toml terms into memory/state."""
    from mga.cultural.terminology_db import TerminologyDB
    from mga.memory.entities import TermState
    from mga.memory.state import StateManager

    project_path = Path(project_dir)
    db = TerminologyDB.load(project_path)
    count = 0
    for item in db.items():
        term_id = item.term_jp.lower().replace(" ", "_")
        StateManager.upsert_term(
            project_path,
            TermState(
                term_id=term_id,
                term_jp=item.term_jp,
                term_zh=item.term_target,
                candidate_translations=item.candidate_translations,
                context=item.notes,
                cultural_weight=item.problem_types[0] if item.problem_types else "",
                strategy=item.strategy,
                accepted_reason=item.accepted_reason,
                rejected_reasons=item.rejected_reasons,
                applicability_scope=item.applicability_scope,
            ),
        )
        count += 1
    click.echo(f"Terminology imported: {count} terms")


@click.group()
def decision():
    """Translation decision commands."""


@decision.command("list")
@click.argument("project_dir", type=click.Path(exists=True))
def decision_list(project_dir):
    """List recorded translation decisions."""
    from mga.memory.state import StateManager

    decisions = StateManager.list_decisions(Path(project_dir))
    if not decisions:
        click.echo("No translation decisions found.")
        return
    for item in decisions:
        click.echo(
            f"  {item.decision_id}: [{item.stage}] {item.decision} "
            f"(confidence={item.confidence})"
        )


@decision.command("add")
@click.argument("project_dir", type=click.Path())
@click.option("--decision-id", default=None)
@click.option("--stage", required=True)
@click.option("--input-ref", default="")
@click.option("--decision", "decision_text", required=True)
@click.option("--rationale", default="")
@click.option("--confidence", type=float, default=0.0, show_default=True)
def decision_add(
    project_dir,
    decision_id,
    stage,
    input_ref,
    decision_text,
    rationale,
    confidence,
):
    """Record a translation decision in memory state."""
    from mga.memory.entities import DecisionState
    from mga.memory.state import StateManager

    decision_state = DecisionState(
        decision_id=decision_id or "",
        stage=stage,
        input_ref=input_ref,
        decision=decision_text,
        rationale=rationale,
        confidence=confidence,
    )
    StateManager.upsert_decision(Path(project_dir), decision_state)
    click.echo(f"Decision saved: {decision_state.decision_id}")


@click.group()
def graph():
    """Character relationship graph commands."""


@graph.command("add")
@click.argument("project_dir", type=click.Path())
@click.argument("source")
@click.argument("target")
@click.option("--relationship", default="")
@click.option(
    "--formality",
    default="casual",
    type=click.Choice(["intimate", "casual", "polite", "formal", "honorific"]),
    show_default=True,
)
@click.option("--honorific", default="")
@click.option("--notes", default="")
def graph_add(project_dir, source, target, relationship, formality, honorific, notes):
    """Add or update a directed character relationship."""
    from mga.memory.graph import CharacterGraph

    project_path = Path(project_dir)
    character_graph = CharacterGraph.load(project_path)
    character_graph.add_character(source)
    character_graph.add_character(target)
    character_graph.add_relationship(
        source,
        target,
        relationship=relationship,
        formality=formality,
        honorific=honorific,
        notes=notes,
    )
    character_graph.save(project_path)
    click.echo(f"Relationship saved: {source} -> {target}")


@graph.command("list")
@click.argument("project_dir", type=click.Path(exists=True))
@click.option("--character", default=None, help="Filter relationships touching this character id.")
def graph_list(project_dir, character):
    """List character relationship edges."""
    from mga.memory.graph import CharacterGraph

    character_graph = CharacterGraph.load(Path(project_dir))
    edges = [
        (source, target, data)
        for source, target, data in character_graph.graph.edges(data=True)
        if character is None or source == character or target == character
    ]
    if not edges:
        click.echo("No character relationships found.")
        return
    for source, target, data in edges:
        details = []
        if data.get("relationship"):
            details.append(data["relationship"])
        if data.get("formality"):
            details.append(f"formality={data['formality']}")
        if data.get("honorific"):
            details.append(f"honorific={data['honorific']}")
        if data.get("notes"):
            details.append(f"notes={data['notes']}")
        suffix = f" ({', '.join(details)})" if details else ""
        click.echo(f"  {source} -> {target}{suffix}")


@graph.command("context")
@click.argument("project_dir", type=click.Path(exists=True))
@click.argument("speaker")
@click.argument("listener")
@click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
def graph_context(project_dir, speaker, listener, as_json):
    """Retrieve speaker/listener relationship context."""
    from mga.memory.graph_retrieval import GraphRetrieval

    retrieval = GraphRetrieval.from_project(Path(project_dir))
    addressing = retrieval.get_addressing(speaker, listener)
    prompt_context = retrieval.get_translation_context(speaker, listener)
    payload = {
        "speaker": speaker,
        "listener": listener,
        **addressing,
        "prompt_context": prompt_context,
    }
    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    click.echo(f"{speaker} -> {listener}")
    click.echo(f"relationship: {payload['relationship'] or '(none)'}")
    click.echo(f"formality: {payload['formality']}")
    click.echo(f"honorific: {payload['honorific'] or '(none)'}")
    click.echo(f"suggestion: {payload['suggestion']}")
    if prompt_context:
        click.echo(f"context: {prompt_context}")


@graph.command("check-formality")
@click.argument("project_dir", type=click.Path(exists=True))
@click.argument("speaker")
@click.argument("listener")
@click.argument(
    "proposed_formality",
    type=click.Choice(["intimate", "casual", "polite", "formal", "honorific"]),
)
@click.option("--json", "as_json", is_flag=True, help="Emit structured JSON.")
def graph_check_formality(project_dir, speaker, listener, proposed_formality, as_json):
    """Check whether proposed formality matches graph context."""
    from mga.memory.graph_retrieval import GraphRetrieval

    result = GraphRetrieval.from_project(Path(project_dir)).check_formality_consistency(
        speaker,
        listener,
        proposed_formality,
    )
    payload = {
        "speaker": speaker,
        "listener": listener,
        **result,
    }
    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    status = "consistent" if result["consistent"] else "mismatch"
    click.echo(
        f"Formality {status}: expected={result['expected']} "
        f"proposed={result['proposed']}"
    )
    click.echo(result["message"])


@click.group()
def batch():
    """Batch translation commands."""


def _load_chapter_manifest(chapters_json: str) -> list[dict[str, str]]:
    chapters_payload = json.loads(Path(chapters_json).read_text(encoding="utf-8"))
    if not isinstance(chapters_payload, list):
        raise click.ClickException("chapters_json must contain a JSON list")
    for index, chapter in enumerate(chapters_payload):
        if not isinstance(chapter, dict):
            raise click.ClickException(f"chapter entry {index} must be an object")
        if "input_path" not in chapter or "output_path" not in chapter:
            raise click.ClickException(
                f"chapter entry {index} must include input_path and output_path"
            )
    return chapters_payload


@batch.command("run")
@click.argument("chapters_json", type=click.Path(exists=True, dir_okay=False))
@click.option("--project-dir", required=True, type=click.Path())
@click.option("--max-workers", default=1, type=int, show_default=True)
@click.option("--resume/--no-resume", default=True, show_default=True)
@click.option("--provider", default=None)
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
@click.option("--save-json", is_flag=True)
def batch_run(
    chapters_json,
    project_dir,
    max_workers,
    resume,
    provider,
    config_path,
    save_json,
):
    """Run batch translation from a JSON chapter manifest."""
    from mga.pipeline.batch import BatchProcessor

    chapters_payload = _load_chapter_manifest(chapters_json)
    project_path = Path(project_dir)
    project_path.mkdir(parents=True, exist_ok=True)
    summary = BatchProcessor(
        project_path,
        max_workers=max_workers,
        provider_override=provider,
        config_path=config_path,
        save_json=save_json,
    ).process(chapters_payload, resume=resume)
    summary_path = project_path / "batch-summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    click.echo(
        "Batch complete: "
        f"{summary.get('completed', 0)} completed, "
        f"{summary.get('partial', 0)} partial, "
        f"{summary.get('failed', 0)} failed. "
        f"{summary_path}"
    )


@batch.command("status")
@click.argument("chapters_json", type=click.Path(exists=True, dir_okay=False))
@click.option("--project-dir", required=True, type=click.Path())
def batch_status(chapters_json, project_dir):
    """Report batch progress for a JSON chapter manifest."""
    from mga.pipeline.batch import BatchProcessor

    chapters_payload = _load_chapter_manifest(chapters_json)
    project_path = Path(project_dir)
    project_path.mkdir(parents=True, exist_ok=True)
    status = BatchProcessor(project_path).get_status(chapters_payload)
    status_path = project_path / "batch-status.json"
    status_path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    click.echo(
        "Batch status: "
        f"{status.get('completed', 0)} completed, "
        f"{status.get('partial', 0)} partial, "
        f"{status.get('failed', 0)} failed, "
        f"{status.get('pending', 0)} pending. "
        f"{status_path}"
    )


@batch.command("reset")
@click.option("--project-dir", required=True, type=click.Path())
def batch_reset(project_dir):
    """Clear saved batch progress."""
    from mga.pipeline.batch import BatchProcessor

    project_path = Path(project_dir)
    BatchProcessor(project_path).reset()
    click.echo(f"Batch progress reset: {project_path / 'batch_progress.json'}")


@click.group()
def review():
    """Review and diff translation artifacts."""


@review.command("diff")
@click.argument("original_json", type=click.Path(exists=True, dir_okay=False))
@click.argument("revised_json", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output-path", required=True, type=click.Path(file_okay=False))
def review_diff(original_json, revised_json, output_path):
    """Compare two translation JSON artifacts."""
    from mga.review import write_translation_diff

    artifact_path, payload = write_translation_diff(
        original_json,
        revised_json,
        output_path,
    )
    click.echo(
        "Review diff complete: "
        f"{payload['changed_bubbles']}/{payload['total_bubbles']} bubbles changed. "
        f"{artifact_path}"
    )


@review.command("report")
@click.argument("translation_report_json", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output-path", required=True, type=click.Path(file_okay=False))
def review_report(translation_report_json, output_path):
    """Generate review/report.json from a translation-report.json artifact."""
    from mga.artifacts import ArtifactStore
    from mga.review import (
        load_review_reports_from_translation_report,
        write_review_artifacts,
    )

    reports = load_review_reports_from_translation_report(translation_report_json)
    artifact_path = write_review_artifacts(ArtifactStore(Path(output_path)), reports)
    needing_review = sum(1 for report in reports if report.needs_human_review)
    click.echo(
        "Review report complete: "
        f"{len(reports)} pages, {needing_review} needing human review. "
        f"{artifact_path}"
    )


@review.command("repair-plan")
@click.argument("translation_report_json", type=click.Path(exists=True, dir_okay=False))
@click.option("-o", "--output-path", required=True, type=click.Path(file_okay=False))
def review_repair_plan(translation_report_json, output_path):
    """Generate review/repair-plan.json from a translation-report.json artifact."""
    from mga.artifacts import ArtifactStore
    from mga.review import (
        load_repair_plan_from_translation_report,
        write_repair_plan_artifact,
    )

    payload = load_repair_plan_from_translation_report(translation_report_json)
    artifact_path = write_repair_plan_artifact(
        ArtifactStore(Path(output_path)),
        payload,
    )
    click.echo(
        "Review repair plan complete: "
        f"{payload['summary']['total_repairs']} repairs. "
        f"{artifact_path}"
    )


@review.command("decide")
@click.argument("repair_plan_json", type=click.Path(exists=True, dir_okay=False))
@click.option("--project-dir", required=True, type=click.Path())
@click.option("--bubble-id", required=True)
@click.option("--status", required=True, type=click.Choice(["accept", "reject"]))
@click.option("--rationale", default="")
def review_decide(repair_plan_json, project_dir, bubble_id, status, rationale):
    """Record a human review decision for a repair-plan item."""
    from mga.memory.entities import DecisionState
    from mga.memory.state import StateManager

    payload = json.loads(Path(repair_plan_json).read_text(encoding="utf-8"))
    repairs = payload.get("repairs", []) if isinstance(payload, dict) else []
    if not isinstance(repairs, list):
        raise click.ClickException("repair plan must contain a repairs list")

    repair = next(
        (
            item for item in repairs
            if isinstance(item, dict) and str(item.get("bubble_id", "")) == bubble_id
        ),
        None,
    )
    if repair is None:
        raise click.ClickException(f"No repair found for bubble_id={bubble_id}")

    page_id = str(repair.get("page_id") or "unknown")
    action = str(repair.get("action") or repair.get("target") or "repair")
    decision_id = f"review-{page_id}-{bubble_id}-{status}"
    try:
        confidence = float(repair.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    decision_state = DecisionState(
        decision_id=decision_id,
        stage="review",
        input_ref=f"{page_id}/{bubble_id}",
        decision=f"{status} {action} for {bubble_id}",
        rationale=rationale or str(repair.get("message") or ""),
        confidence=confidence,
        metadata={
            "page_id": page_id,
            "bubble_id": bubble_id,
            "target": str(repair.get("target") or ""),
            "action": action,
            "message": str(repair.get("message") or ""),
            "original_text": str(repair.get("original_text") or ""),
            "suggested_text": str(repair.get("suggested_text") or ""),
            "repair_rationale": str(repair.get("rationale") or ""),
            "status": status,
        },
    )
    StateManager.upsert_decision(Path(project_dir), decision_state)
    click.echo(f"Review decision saved: {decision_state.decision_id}")


@click.command("web")
@click.option("--project-root", default=".", type=click.Path(), show_default=True)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, type=int, show_default=True)
def web(project_root, host, port):
    """Run the FastAPI project management Web UI."""
    import uvicorn

    from mga.web import create_app

    app = create_app(project_root=Path(project_root))
    uvicorn.run(app, host=host, port=port)


@click.command("mcp")
@click.option("--project-root", default=".", type=click.Path(), show_default=True)
def mcp(project_root):
    """Run the stdio MCP server for local agent tools."""
    from mga.mcp_server import MangaTranslatorMCPServer, run_stdio

    run_stdio(MangaTranslatorMCPServer(project_root=Path(project_root)))


@click.group()
def main():
    """Manga Translate Agent (mga) CLI."""

main.add_command(translate)
main.add_command(benchmark_external)
main.add_command(legacy)
main.add_command(memory)
main.add_command(profile)
main.add_command(scene)
main.add_command(term)
main.add_command(decision)
main.add_command(graph)
main.add_command(batch)
main.add_command(review)
main.add_command(web)
main.add_command(mcp)

if __name__ == "__main__":
    main()
