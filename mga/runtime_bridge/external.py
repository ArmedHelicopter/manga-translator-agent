"""Formal external runtime integration for the external-core architecture."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

from ..artifacts import ArtifactStore
from ..format.manifest import build_manifest_payload, discover_image_paths, load_image_metadata
from ..models import Page, PageImage, ProjectConfig
from ..providers.registry import resolve_provider_settings

DEFAULT_EXTERNAL_RUNTIME_CANDIDATES = (
    Path("external/manga-image-translator"),
    Path("external/external/manga-image-translator"),
)


def _split_path_list(value: str) -> tuple[list[str], str]:
    if ";" in value:
        return value.split(";"), ";"
    if ":" in value and not (len(value) >= 3 and value[1] == ":" and value[2] in "\\/"):
        return value.split(":"), ":"
    return ([value] if value else []), os.pathsep


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


def _input_signature(input_path: Path) -> dict[str, Any]:
    stat = input_path.stat()
    signature: dict[str, Any] = {
        "input_path": str(input_path.resolve()),
        "input_size": stat.st_size,
        "input_mtime_ns": stat.st_mtime_ns,
        "input_suffix": input_path.suffix.lower(),
    }
    if input_path.suffix.lower() == ".pdf":
        from mga.format.pdf_adapter import _RENDER_DPI

        signature["pdf_render_dpi"] = _RENDER_DPI
    return signature


def _write_runtime_input_manifest(
    payload_dir: Path,
    input_path: Path,
    runtime_input: Path,
) -> None:
    image_paths = [runtime_input] if runtime_input.is_file() else discover_image_paths(runtime_input)
    manifest = {
        **_input_signature(input_path),
        "runtime_input": str(runtime_input.resolve()),
        "page_count": len(image_paths),
        "pages": [
            {
                "index": index,
                "name": image_path.name,
                "size": image_path.stat().st_size,
            }
            for index, image_path in enumerate(image_paths)
        ],
    }
    (payload_dir / "runtime-input-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _has_matching_runtime_input_manifest(payload_dir: Path, input_path: Path) -> bool:
    manifest_path = payload_dir / "runtime-input-manifest.json"
    if not manifest_path.exists():
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    expected = _input_signature(input_path.resolve())
    return all(manifest.get(key) == value for key, value in expected.items())


def _prepare_runtime_image_input(input_path: Path, payload_dir: Path) -> Path:
    """Return an image file/folder input accepted by the external runtime."""

    input_path = input_path.resolve()
    if input_path.is_dir():
        _write_runtime_input_manifest(payload_dir, input_path, input_path)
        return input_path

    image_extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    if input_path.suffix.lower() in image_extensions:
        _write_runtime_input_manifest(payload_dir, input_path, input_path)
        return input_path

    from mga.format import get_adapter

    adapter = get_adapter(input_path.suffix.lstrip(".").lower())
    runtime_input_dir = payload_dir / ".runtime-input"
    if runtime_input_dir.exists():
        shutil.rmtree(runtime_input_dir)
    runtime_input_dir.mkdir(parents=True, exist_ok=True)

    for page_ref in adapter.extract(input_path):
        source = Path(page_ref.image_path)
        suffix = source.suffix or ".png"
        target = runtime_input_dir / f"page-{page_ref.index:04d}{suffix}"
        shutil.copy2(source, target)

    if not discover_image_paths(runtime_input_dir):
        raise RuntimeError(f"Input adapter did not produce image pages for {input_path}")
    _write_runtime_input_manifest(payload_dir, input_path, runtime_input_dir)
    return runtime_input_dir


def _write_empty_runtime_artifact(payload_dir: Path, image_path: Path, page_index: int) -> None:
    from PIL import Image

    payload_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        suffix = f"-{page_index:04d}"
        rgb.save(payload_dir / f"inpainted{suffix}.png")

    artifact = {
        "version": 1,
        "page_index": page_index,
        "text_regions": [],
        "render_config": {},
        "image_shape": [height, width, 3],
    }
    suffix = f"-{page_index:04d}"
    (payload_dir / f"artifact{suffix}.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _normalize_single_page_runtime_artifact(payload_dir: Path, page_index: int) -> None:
    """Rename a single-page runtime export to the expected global page slot."""

    suffix = f"-{page_index:04d}"
    for stem, ext in (("artifact", ".json"), ("inpainted", ".png"), ("mask", ".png")):
        target = payload_dir / f"{stem}{suffix}{ext}"
        candidates = [payload_dir / f"{stem}-0000{ext}", payload_dir / f"{stem}{ext}"]
        for candidate in candidates:
            if candidate.exists() and candidate != target:
                candidate.replace(target)
                break

    artifact_path = payload_dir / f"artifact{suffix}.json"
    if artifact_path.exists():
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            artifact["page_index"] = page_index
            artifact_path.write_text(
                json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except (OSError, json.JSONDecodeError):
            pass


def _write_pages_manifest(payload_dir: Path, page_count: int) -> None:
    pages_list = []
    for index in range(page_count):
        suffix = f"-{index:04d}"
        pages_list.append({
            "page_index": index,
            "artifact": f"artifact{suffix}.json",
            "inpainted": f"inpainted{suffix}.png",
        })
    (payload_dir / "pages.json").write_text(
        json.dumps(pages_list, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _complete_runtime_artifacts(payload_dir: Path, runtime_input: Path) -> bool:
    """Fill empty-page artifacts and return whether any artifact exists."""

    if runtime_input.is_file():
        image_paths = [runtime_input]
    else:
        image_paths = discover_image_paths(runtime_input)
    if not image_paths:
        return False

    pages_list: list[dict[str, Any]] = []
    for index, image_path in enumerate(image_paths):
        suffix = f"-{index:04d}"
        artifact_path = payload_dir / f"artifact{suffix}.json"
        inpainted_path = payload_dir / f"inpainted{suffix}.png"
        if not artifact_path.exists() or not inpainted_path.exists():
            _write_empty_runtime_artifact(payload_dir, image_path, index)
        pages_list.append({
            "page_index": index,
            "artifact": f"artifact{suffix}.json",
            "inpainted": f"inpainted{suffix}.png",
        })

    (payload_dir / "pages.json").write_text(
        json.dumps(pages_list, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return bool(pages_list)


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    # sk-proj-... (OpenAI project keys)
    (r"sk-proj-[A-Za-z0-9_-]{10,}", "[REDACTED]"),
    # Bearer tokens in "Authorization: Bearer <token>" headers
    (r"Bearer\s+([A-Za-z0-9_-]{10,})", r"Bearer [REDACTED]"),
    # api_key=... query params
    (r"(api_key|apikey|api-key)=[A-Za-z0-9_-]{6,}", r"\1=[REDACTED]"),
    # KEY=value env var style
    (r"([A-Z_][A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD|KEY)[A-Z0-9_]*)=[^\s]{4,}", r"\1=[REDACTED]"),
]


def _sanitize_subprocess_output(output: str) -> str:
    """Redact secrets from subprocess stdout/stderr for safe logging."""
    if not output:
        return output
    result = output
    for pattern, replacement in _SECRET_PATTERNS:
        result = re.sub(pattern, replacement, result)
    return result


# ---------------------------------------------------------------------------
# Child process environment
# ---------------------------------------------------------------------------

def _build_external_child_env() -> dict[str, str]:
    """Build a tighter child environment for external subprocesses."""

    child_env = os.environ.copy()
    for key in list(child_env):
        if key.startswith("CONDA_"):
            child_env.pop(key, None)

    child_env.pop("PYTHONHOME", None)
    child_env.pop("PYTHONPATH", None)

    # Strip API key / secret / token environment variables
    _API_KEY_PATTERN_RE = re.compile(
        r"^[A-Z_][A-Z0-9_]*(?:API_KEY|SECRET|TOKEN|PASSWORD|KEY)$"
    )
    for key in list(child_env):
        if _API_KEY_PATTERN_RE.match(key):
            child_env.pop(key, None)

    path_entries, path_separator = _split_path_list(child_env.get("PATH", ""))
    filtered_path = [
        entry
        for entry in path_entries
        if entry and "anaconda" not in entry.lower() and "conda" not in entry.lower()
    ]
    child_env["PATH"] = path_separator.join(filtered_path)

    system_libstdcpp = "/usr/lib/x86_64-linux-gnu/libstdc++.so.6"
    ld_library_entries = ["/usr/lib/x86_64-linux-gnu"]
    raw_ld_library_path = child_env.get("LD_LIBRARY_PATH", "")
    ld_path_entries, _ = _split_path_list(raw_ld_library_path)
    ld_library_entries.extend(
        entry
        for entry in ld_path_entries
        if entry and "anaconda" not in entry.lower() and "conda" not in entry.lower()
    )
    child_env["LD_LIBRARY_PATH"] = ":".join(dict.fromkeys(ld_library_entries)) + ":"
    ld_preload_entries, _ = _split_path_list(child_env.get("LD_PRELOAD", ""))
    child_env["LD_PRELOAD"] = ":".join(
        dict.fromkeys(
            [
                system_libstdcpp,
                *[entry for entry in ld_preload_entries if entry],
            ]
        )
    ) + ":"
    return child_env


def _resolve_runtime_openai_settings(project_config: ProjectConfig, raw_config: dict[str, Any]) -> dict[str, Any]:
    """Resolve the translation provider settings needed by the OpenAI-based runtime."""

    providers = raw_config.get("providers", {})
    route = project_config.provider_routes.get("translation") or project_config.provider_routes.get("translate")
    provider_name = route.primary.provider if route and route.primary.provider else "openai"
    provider_type, settings = resolve_provider_settings(provider_name, providers.get(provider_name, {}))
    if provider_type != "openai":
        return {}

    if route and route.primary.model and "model" not in settings and "text_model" not in settings:
        settings["model"] = route.primary.model

    api_key_env = settings.pop("api_key_env", None)
    base_url_env = settings.pop("base_url_env", None)
    if not settings.get("api_key") and api_key_env:
        settings["api_key"] = os.getenv(str(api_key_env), "")
    if not settings.get("base_url") and base_url_env:
        settings["base_url"] = os.getenv(str(base_url_env), "")
    return settings


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

    openai_settings = _resolve_runtime_openai_settings(project_config, raw_config)
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


def _run_export_artifact_command(
    *,
    external_python: Path,
    resolved_repo: Path,
    runtime_input: Path,
    output_dir: Path,
    payload_dir: Path,
    export_config_path: Path,
) -> subprocess.CompletedProcess[str]:
    command = [
        str(external_python),
        "-m", "manga_translator", "local",
        "-i", str(runtime_input.resolve()),
        "-o", str(output_dir.resolve()),
        "--overwrite",
        "--export-artifact", str(payload_dir.resolve()),
        "--config-file", str(export_config_path.resolve()),
    ]

    return subprocess.run(
        command,
        cwd=resolved_repo,
        env=_build_external_child_env(),
        capture_output=True,
        text=True,
        check=False,
    )


def run_export_artifact(
    *,
    input_dir: Path,
    payload_dir: Path,
    repo_dir: Path | None = None,
    config_path: Path | None = None,
    inpaint_backend: str = "auto",
) -> dict[str, Any]:
    """Pass 1: Run detect/OCR/merge/inpaint and export the render payload.

    The runtime stops after inpainting and writes artifact.json + inpainted.png
    to *payload_dir*. No translation or rendering happens.

    Args:
        inpaint_backend: Inpainter to use. "auto" selects lama_large (background
        reconstruction) so text regions are erased cleanly instead of painted
        white. Maps to the runtime's Inpainter enum:
        none|lama_large|lama_mpe|sd|original|default.
    """
    if inpaint_backend not in ("auto", "none", "lama_large", "lama_mpe", "sd", "original", "default"):
        raise ValueError(
            f"Invalid inpaint_backend: {inpaint_backend!r}. "
            f"Choose from: auto, none, lama_large, lama_mpe, sd, original, default"
        )
    # Use the project root (which has our modified manga_translator/) rather than
    # the external clone, since --export-artifact is our addition.
    project_root = Path(__file__).resolve().parent.parent.parent
    if not (project_root / "manga_translator" / "__main__.py").exists():
        resolved_repo = resolve_external_runtime_repo(repo_dir)
    else:
        resolved_repo = project_root

    external_python = Path(os.getenv("MANGA_TRANSLATE_EXTERNAL_PYTHON") or sys.executable).expanduser()
    if not external_python.is_absolute():
        external_python = (Path.cwd() / external_python).absolute()

    payload_dir.mkdir(parents=True, exist_ok=True)
    input_path = input_dir.resolve()
    for pattern in (
        "artifact*.json",
        "inpainted*.png",
        "mask*.png",
        "pages.json",
        "translations-*.json",
        "runtime-export-config.json",
    ):
        for path in payload_dir.glob(pattern):
            if path.is_file():
                path.unlink()
    runtime_input = _prepare_runtime_image_input(input_dir, payload_dir)
    export_config_path = payload_dir / "runtime-export-config.json"
    # "auto" uses lama_large (background reconstruction) for the export pass so
    # text regions are erased cleanly instead of filled white (none.py paints
    # mask>0 white, leaving blank patches on TOC/cover pages — page-003 white-page
    # regression). lama_large_512px.ckpt ships in models/inpainting/ (no download).
    # Only override when the user explicitly selects a different backend.
    effective_inpainter = "lama_large" if inpaint_backend == "auto" else inpaint_backend
    export_config_path.write_text(
        json.dumps(
            {
                "detector": {
                    "detection_size": 1024,
                },
                "inpainter": {
                    "inpainter": effective_inpainter,
                    "inpainting_size": 1024,
                },
                "translator": {
                    "translator": "none",
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

    image_paths = [runtime_input] if runtime_input.is_file() else discover_image_paths(runtime_input)
    last_completed: subprocess.CompletedProcess[str] | None = None

    # Export every input page in isolation, then install it into the expected
    # global slot. The runtime's multi-page export names artifacts with an
    # internal counter that advances only after several early-return branches;
    # when any page exits early, artifact JSON and inpainted PNG queues shift and
    # the tail can reuse a base plate (docs/issues/recon-ticket-pipeline-index-shift.md).
    # Isolating each page
    # makes artifact-N/inpainted-N derive from source image N, not from runtime
    # control-flow order.
    with tempfile.TemporaryDirectory(prefix="mga-pass1-") as tmp_root:
        tmp_root_path = Path(tmp_root)
        for index, image_path in enumerate(image_paths):
            page_payload = tmp_root_path / f"payload-{index:04d}"
            page_output = tmp_root_path / f"output-{index:04d}"
            page_payload.mkdir(parents=True, exist_ok=True)
            completed = _run_export_artifact_command(
                external_python=external_python,
                resolved_repo=resolved_repo,
                runtime_input=image_path,
                output_dir=page_output,
                payload_dir=page_payload,
                export_config_path=export_config_path,
            )
            last_completed = completed
            output_tail = f"{completed.stdout[-4000:]}\n{completed.stderr[-4000:]}"
            if completed.returncode != 0 or "ERROR:" in output_tail or "Traceback" in output_tail:
                raise RuntimeError(
                    f"Export artifact failed for page {index} (exit {completed.returncode}).\n"
                    f"stdout: {_sanitize_subprocess_output(completed.stdout[-2000:])}\n"
                    f"stderr: {_sanitize_subprocess_output(completed.stderr[-2000:])}"
                )

            _complete_runtime_artifacts(page_payload, image_path)
            _normalize_single_page_runtime_artifact(page_payload, index)
            suffix = f"-{index:04d}"
            for stem, ext in (("artifact", ".json"), ("inpainted", ".png"), ("mask", ".png")):
                source = page_payload / f"{stem}{suffix}{ext}"
                if source.exists():
                    shutil.copy2(source, payload_dir / source.name)

    _write_pages_manifest(payload_dir, len(image_paths))
    has_artifact = bool(image_paths)
    if not has_artifact:
        stdout = last_completed.stdout[-2000:] if last_completed else ""
        raise RuntimeError(
            f"Export artifact completed but no artifact files found in {payload_dir}.\n"
            f"stdout: {stdout}"
        )

    return {
        "payload_dir": str(payload_dir),
        "returncode": last_completed.returncode if last_completed else 0,
    }


def run_render_only(
    *,
    payload_dir: Path,
    output_dir: Path,
    page_index: int = 0,
    repo_dir: Path | None = None,
    config_path: Path | None = None,
    inpaint_backend: str = "auto",
) -> dict[str, Any]:
    """Pass 2: Load payload + translations and run rendering for one page.

    Expects *payload_dir* to contain per-page artifact/inpainted/translations files.

    Args:
        inpaint_backend: Inpainter to use for re-inpainting. "auto" defers to
        the runtime default. When not "auto", writes a render config JSON with
        the selected backend and passes it via --config-file.
    """
    if inpaint_backend not in ("auto", "none", "lama_large", "lama_mpe", "sd", "original", "default"):
        raise ValueError(
            f"Invalid inpaint_backend: {inpaint_backend!r}. "
            f"Choose from: auto, none, lama_large, lama_mpe, sd, original, default"
        )
    project_root = Path(__file__).resolve().parent.parent.parent
    if not (project_root / "manga_translator" / "__main__.py").exists():
        resolved_repo = resolve_external_runtime_repo(repo_dir)
    else:
        resolved_repo = project_root

    external_python = Path(os.getenv("MANGA_TRANSLATE_EXTERNAL_PYTHON") or sys.executable).expanduser()
    if not external_python.is_absolute():
        external_python = (Path.cwd() / external_python).absolute()

    output_dir.mkdir(parents=True, exist_ok=True)

    # If an inpaint backend is selected and no explicit config_path is
    # provided, write a render config JSON with the selected inpainter.
    render_config_path = config_path
    if render_config_path is None and inpaint_backend != "auto":
        render_config_path = output_dir / "runtime-render-config.json"
        render_config_path.write_text(
            json.dumps(
                {"inpainter": {"inpainter": inpaint_backend}},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    command = [
        str(external_python),
        "-m", "manga_translator", "local",
        "-i", str(payload_dir.resolve()),
        "-o", str(output_dir.resolve()),
        "--overwrite",
        "--render-only", str(payload_dir.resolve()),
    ]
    if render_config_path:
        command.extend(["--config-file", str(render_config_path.resolve())])

    child_env = _build_external_child_env()
    completed = subprocess.run(
        command,
        cwd=resolved_repo,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )

    rendered_images = _collect_rendered_images(output_dir)

    if completed.returncode != 0:
        raise RuntimeError(
            f"Render-only failed (exit {completed.returncode}).\n"
            f"stderr: {_sanitize_subprocess_output(completed.stderr[-2000:])}"
        )

    return {
        "output_dir": str(output_dir),
        "rendered_images": rendered_images,
        "returncode": completed.returncode,
    }
