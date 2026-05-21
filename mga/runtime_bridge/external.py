"""Formal external runtime integration for the external-core architecture."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from ..artifacts import ArtifactStore
from ..format.manifest import build_manifest_payload, discover_image_paths, load_image_metadata
from ..models import Page, PageImage, ProjectConfig

DEFAULT_EXTERNAL_RUNTIME_CANDIDATES = (
    Path("external/manga-image-translator"),
    Path("external/external/manga-image-translator"),
)


def resolve_external_runtime_repo(repo_dir: Path | None = None) -> Path:
    """Resolve the local external runtime checkout."""

    candidates: list[Path] = []
    if repo_dir is not None:
        candidates.append(repo_dir)
    candidates.extend(DEFAULT_EXTERNAL_RUNTIME_CANDIDATES)

    for candidate in candidates:
        if (candidate / "manga_translator" / "__main__.py").exists():
            return candidate

    searched = ", ".join(str(path) for path in candidates)
    raise RuntimeError(
        "Could not locate the external runtime repo. "
        f"Checked: {searched}"
    )


def _collect_rendered_images(output_dir: Path) -> list[str]:
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    return sorted(
        str(path.relative_to(output_dir))
        for path in output_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in exts
    )


def _build_external_child_env() -> dict[str, str]:
    """Build a tighter child environment for external subprocesses."""

    child_env = os.environ.copy()
    for key in list(child_env):
        if key.startswith("CONDA_"):
            child_env.pop(key, None)

    child_env.pop("PYTHONHOME", None)
    child_env.pop("PYTHONPATH", None)

    path_entries = child_env.get("PATH", "").split(os.pathsep)
    filtered_path = [
        entry
        for entry in path_entries
        if entry and "anaconda" not in entry.lower() and "conda" not in entry.lower()
    ]
    child_env["PATH"] = os.pathsep.join(filtered_path)

    system_libstdcpp = "/usr/lib/x86_64-linux-gnu/libstdc++.so.6"
    ld_library_entries = ["/usr/lib/x86_64-linux-gnu"]
    ld_library_entries.extend(
        entry
        for entry in child_env.get("LD_LIBRARY_PATH", "").split(os.pathsep)
        if entry and "anaconda" not in entry.lower() and "conda" not in entry.lower()
    )
    child_env["LD_LIBRARY_PATH"] = os.pathsep.join(dict.fromkeys(ld_library_entries))
    child_env["LD_PRELOAD"] = os.pathsep.join(
        dict.fromkeys(
            [
                system_libstdcpp,
                *[
                    entry
                    for entry in child_env.get("LD_PRELOAD", "").split(os.pathsep)
                    if entry
                ],
            ]
        )
    )
    return child_env


def _parse_saved_text_blocks(raw_text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_region: dict[str, Any] | None = None
    current_field: str | None = None

    for raw_line in raw_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("[") and stripped.endswith("]"):
            if current is not None:
                if current_region is not None:
                    current["regions"].append(current_region)
                    current_region = None
                blocks.append(current)
            current = {"image_path": stripped[1:-1], "regions": []}
            current_region = None
            current_field = None
            continue

        if current is None:
            continue

        if stripped.startswith("-- ") and stripped.endswith(" --"):
            if current_region is not None:
                current["regions"].append(current_region)
            current_region = {"text": "", "translation": "", "coords": []}
            current_field = None
            continue

        if current_region is None:
            continue

        if stripped.startswith("text:"):
            current_region["text"] = stripped.split(":", 1)[1].strip()
            current_field = "text"
        elif stripped.startswith("trans:"):
            current_region["translation"] = stripped.split(":", 1)[1].strip()
            current_field = "translation"
        elif stripped.startswith("coords:"):
            current_region["coords"].append(stripped.split(":", 1)[1].strip())
            current_field = "coords"
        elif current_field == "text":
            current_region["text"] = "\n".join(
                part for part in [current_region["text"], stripped] if part
            )
        elif current_field == "translation":
            current_region["translation"] = "\n".join(
                part for part in [current_region["translation"], stripped] if part
            )

    if current is not None:
        if current_region is not None:
            current["regions"].append(current_region)
        blocks.append(current)

    return blocks


def _normalize_external_text_blocks(
    blocks: list[dict[str, Any]],
    *,
    input_dir: Path,
    output_dir: Path,
) -> list[dict[str, Any]]:
    input_dir = input_dir.resolve()
    image_to_page_id: dict[str, str] = {}
    for index, image_path in enumerate(discover_image_paths(input_dir), start=1):
        image_to_page_id[str(image_path.resolve())] = f"page-{index:04d}"

    normalized: list[dict[str, Any]] = []
    for block in blocks:
        resolved_image = str(Path(block["image_path"]).resolve())
        translations = [region["translation"] for region in block["regions"] if region.get("translation")]
        sources = [region["text"] for region in block["regions"] if region.get("text")]
        normalized.append(
            {
                "page_id": image_to_page_id.get(resolved_image),
                "image_path": resolved_image,
                "source_text_joined": "\n".join(sources),
                "translated_text_joined": "\n".join(translations),
                "region_count": len(block["regions"]),
            }
        )

    normalized_path = output_dir / "external-baseline-text-normalized.json"
    normalized_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return normalized


def _build_manifest_pages(config: ProjectConfig) -> list[Page]:
    pages: list[Page] = []
    for index, image_path in enumerate(discover_image_paths(config.working_dir)):
        width, height, dpi = load_image_metadata(image_path)
        pages.append(
            Page(
                page_id=f"page-{index + 1:04d}",
                page_index=index,
                image=PageImage(
                    path=str(Path(image_path).resolve()),
                    width=width,
                    height=height,
                    dpi=dpi,
                ),
                source_lang=config.source_lang,
            )
        )
    return pages


def build_external_run_payload(
    *,
    config: ProjectConfig,
    input_dir: Path,
    output_dir: Path,
    repo_dir: str,
    translation_mode: str = "external-core",
) -> dict[str, Any]:
    """Build the stable run summary payload for an external-core translation run."""

    pages = _build_manifest_pages(config)
    manifest_payload = build_manifest_payload(config.project_name, input_dir, pages)
    return {
        "project_name": config.project_name,
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "artifact_dir": config.artifact_dir,
        "translation_mode": translation_mode,
        "runtime": {
            "type": "external-core",
            "repo_dir": repo_dir,
        },
        "manifest": manifest_payload,
    }


def run_external_translation_runtime(
    *,
    project_config: ProjectConfig,
    raw_config: dict[str, Any],
    store: ArtifactStore,
    repo_dir: Path | None = None,
) -> dict[str, Any]:
    """Run the external runtime as the primary translation path and normalize outputs."""

    input_dir = Path(project_config.working_dir).resolve()
    output_dir = Path(project_config.output_dir).resolve()
    resolved_repo = resolve_external_runtime_repo(repo_dir)

    openai_settings = raw_config.get("providers", {}).get("openai", {})
    image_inputs = discover_image_paths(input_dir)
    if not image_inputs:
        raise RuntimeError(f"No image files found in {input_dir}")

    external_python = Path(os.getenv("MANGA_TRANSLATE_EXTERNAL_PYTHON") or sys.executable).expanduser()
    if not external_python.is_absolute():
        external_python = (Path.cwd() / external_python).absolute()

    saved_text_path = output_dir / "external-baseline-text.txt"
    config_path = output_dir / "external-runtime-config.json"
    config_path.write_text(
        json.dumps(
            {
                "translator": {
                    "translator": "chatgpt",
                    "target_lang": "CHS",
                }
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    command = [
        str(external_python),
        "-m",
        "manga_translator",
        "local",
        "-i",
        str(input_dir),
        "-o",
        str(output_dir),
        "--overwrite",
        "--save-text-file",
        str(saved_text_path),
        "--config-file",
        str(config_path),
    ]

    child_env = _build_external_child_env()
    api_key = openai_settings.get("api_key")
    base_url = openai_settings.get("base_url")
    text_model = openai_settings.get("text_model") or openai_settings.get("model")
    if api_key:
        child_env["OPENAI_API_KEY"] = str(api_key)
    if base_url:
        child_env["OPENAI_API_BASE"] = str(base_url)
    if text_model:
        child_env["OPENAI_MODEL"] = str(text_model)

    completed = subprocess.run(
        command,
        cwd=resolved_repo,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )

    parsed_blocks: list[dict[str, Any]] = []
    normalized_pages: list[dict[str, Any]] = []
    if saved_text_path.exists():
        parsed_blocks = _parse_saved_text_blocks(saved_text_path.read_text(encoding="utf-8"))
        normalized_pages = _normalize_external_text_blocks(
            parsed_blocks,
            input_dir=input_dir,
            output_dir=output_dir,
        )

    manifest = build_manifest_payload(project_config.project_name, input_dir, _build_manifest_pages(project_config))
    store.write_json("manifest.json", manifest)

    summary = {
        "repo_dir": str(resolved_repo),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "command": command,
        "returncode": completed.returncode,
        "input_count": len(image_inputs),
        "rendered_images": _collect_rendered_images(output_dir),
        "saved_text_artifact": str(saved_text_path) if saved_text_path.exists() else None,
        "normalized_text_artifact": (
            str(output_dir / "external-baseline-text-normalized.json") if normalized_pages else None
        ),
        "config_artifact": str(config_path),
        "python_executable": str(external_python),
        "translator": "chatgpt",
        "target_lang": "CHS",
        "openai_base_url": child_env.get("OPENAI_API_BASE"),
        "openai_model": child_env.get("OPENAI_MODEL"),
        "openai_api_key_present": bool(child_env.get("OPENAI_API_KEY")),
        "parsed_page_count": len(normalized_pages),
        "runtime_env": {
            "sanitized_conda": True,
            "pythonpath_removed": "PYTHONPATH" not in child_env,
            "pythonhome_removed": "PYTHONHOME" not in child_env,
            "ld_library_path_present": bool(child_env.get("LD_LIBRARY_PATH")),
            "ld_preload_present": bool(child_env.get("LD_PRELOAD")),
        },
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }
    store.write_json("external-baseline-summary.json", summary)

    if completed.returncode != 0:
        raise RuntimeError(
            "External runtime translation failed. "
            f"See {output_dir / 'external-baseline-summary.json'} for details."
        )

    return {
        "manifest": manifest,
        "summary": summary,
        "normalized_pages": normalized_pages,
        "parsed_blocks": parsed_blocks,
    }
