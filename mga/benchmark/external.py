"""External-core benchmark integration points."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from manga_translate.artifacts import ArtifactStore
from manga_translate.format import discover_image_paths
from manga_translate.runtime.external import (
    _build_external_child_env,
    _normalize_external_text_blocks,
    _parse_saved_text_blocks,
    resolve_external_runtime_repo,
    run_external_translation_runtime,
)

resolve_manga_image_translator_repo = resolve_external_runtime_repo


def _collect_rendered_images(output_dir: Path) -> list[str]:
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    return sorted(
        str(path.relative_to(output_dir))
        for path in output_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in exts
    )


def run_manga_image_translator_baseline(
    *,
    repo_dir: Path | None,
    input_dir: Path,
    output_dir: Path,
    openai_settings: dict[str, Any] | None = None,
) -> dict:
    """Run the external runtime through the shared external-core integration."""

    from manga_translate.models import ProjectConfig, ProviderRoute, StageProviderConfig

    project_config = ProjectConfig(
        project_name=Path(input_dir).resolve().name or "manga-project",
        working_dir=str(Path(input_dir).resolve()),
        output_dir=str(Path(output_dir).resolve()),
        artifact_dir=str(Path(output_dir).resolve()),
        provider_routes={
            "vision": StageProviderConfig(primary=ProviderRoute(provider="openai", model="external-core")),
            "translate": StageProviderConfig(primary=ProviderRoute(provider="openai", model="external-core")),
        },
    )
    result = run_external_translation_runtime(
        project_config=project_config,
        raw_config={"providers": {"openai": openai_settings or {}}},
        store=ArtifactStore(output_dir),
        repo_dir=repo_dir,
    )
    return result["summary"]
