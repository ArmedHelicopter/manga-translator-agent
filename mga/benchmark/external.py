"""External-core benchmark integration points."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..artifacts import ArtifactStore
from ..format.manifest import discover_image_paths
from ..runtime_bridge.external import (
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


@dataclass
class BenchmarkResult:
    """Result of a benchmark run."""
    page_count: int
    bubble_count: int
    output_dir: str


def extract_text_for_benchmark(
    input_dir: Path,
    output_dir: Path,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Extract text from images for benchmark comparison (legacy entry point)."""
    from ..models import Page, PageImage
    from ..format.manifest import discover_image_paths
    from .evaluate import run_extraction_benchmark
    # Import from cascade so tests can monkeypatch get_provider
    from ..providers.cascade import get_provider

    output_dir = Path(output_dir)
    benchmark_dir = output_dir / "benchmark"
    if not force and benchmark_dir.exists():
        return {"page_count": 0, "bubble_count": 0, "output_dir": str(benchmark_dir)}

    benchmark_dir.mkdir(parents=True, exist_ok=True)
    image_paths = discover_image_paths(input_dir)
    if not image_paths:
        return {"page_count": 0, "bubble_count": 0, "output_dir": str(benchmark_dir)}

    pages: list[Page] = []
    for index, image_path in enumerate(image_paths):
        from PIL import Image
        with Image.open(image_path) as img:
            width, height = img.size
        pages.append(
            Page(
                page_id=f"page-{index + 1:04d}",
                page_index=index,
                image=PageImage(path=str(image_path.resolve()), width=width, height=height, dpi=96),
                source_lang="ja",
            )
        )

    store = ArtifactStore(benchmark_dir)
    ocr_specs = ["tesseract_jpn"]

    # Load provider config from TOML file next to input_dir
    raw_config: dict[str, Any] = {"stages": {}, "providers": {}}
    config_path = Path(input_dir).resolve() / "providers.toml"
    if config_path.exists():
        try:
            import tomllib
            raw_config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Build cascade from raw config and call get_provider via cascade
    stages_cfg = raw_config.get("stages", {})
    providers_cfg = raw_config.get("providers", {})
    vision_stage = stages_cfg.get("vision", {})
    primary_provider = vision_stage.get("primary", "openai")
    fallback_provider = vision_stage.get("fallback", "gemini")
    primary_settings = providers_cfg.get(primary_provider, {})
    fallback_settings = providers_cfg.get(fallback_provider, {})

    provider = None
    for name, settings in [(primary_provider, primary_settings), (fallback_provider, fallback_settings)]:
        try:
            provider = get_provider(name, **settings)
            break
        except Exception:
            continue

    result = run_extraction_benchmark(
        pages=pages,
        provider=provider,
        store=store,
        ocr_specs=ocr_specs,
    )

    return {
        "page_count": len(pages),
        "bubble_count": result.get("bubble_count", 0),
        "output_dir": str(benchmark_dir),
    }


def run_manga_image_translator_baseline(
    *,
    repo_dir: Path | None,
    input_dir: Path,
    output_dir: Path,
    openai_settings: dict[str, Any] | None = None,
) -> dict:
    """Run the external runtime through the shared external-core integration."""

    from ..models import ProjectConfig, ProviderRoute, StageProviderConfig

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
