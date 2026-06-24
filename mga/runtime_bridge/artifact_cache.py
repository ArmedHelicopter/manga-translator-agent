"""Content-addressed OCR artifact pinning.

The rendered image depends on the OCR artifact (text_regions: the authoritative
geometry of ``I_n`` per PRD §4.1). The runtime OCR that produces it is not
strictly deterministic across fresh Pass-1 runs, so ``g(I_n)`` — and therefore
the rendered image — could vary run-to-run. This module pins the artifact to
``I_n`` by content-addressing it on ``sha256(I_n)``: the first artifact seen for
a given input image is reused for every subsequent render of that image. With
pinning, ``g(I_n)`` becomes a deterministic (constant) function of ``I_n``, so
the end-to-end rendered output is a deterministic function of ``(I_n, T_n)``.

This is mga-layer artifact management (PRD §4.1 "artifact spine"); it does not
modify the runtime or override OCR authority — it caches the runtime's output
keyed by the input image.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def image_sha256(image_path: str | Path) -> str:
    """Return the sha256 hex of an image file's raw bytes.

    Hashing the bytes (not decoded pixels) is intentional: it is fast and makes
    the identity of ``I_n`` exact — two byte-identical files are the same input
    image by definition.
    """
    h = hashlib.sha256()
    with open(image_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class ArtifactPin:
    """A JSON-backed map of ``sha256(I_n) -> artifact dict``.

    Stored as a sidecar (``artifact-pin.json``) inside the payload directory so
    the pin travels with the project. Cheap to read/write; one entry per
    distinct input image.
    """

    def __init__(self, store_path: str | Path) -> None:
        self.store_path = Path(store_path)
        self._data: dict[str, dict[str, Any]] = {}
        if self.store_path.exists():
            try:
                self._data = json.loads(self.store_path.read_text(encoding="utf-8"))
                if not isinstance(self._data, dict):
                    self._data = {}
            except (OSError, json.JSONDecodeError):
                self._data = {}

    def get(self, image_hash: str) -> dict[str, Any] | None:
        return self._data.get(image_hash)

    def put(self, image_hash: str, artifact: dict[str, Any]) -> None:
        self._data[image_hash] = artifact
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        self.store_path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def has(self, image_hash: str) -> bool:
        return image_hash in self._data


def resolve_pinned_artifact(
    payload_path: Path,
    page_idx: int,
    image_path: str | Path,
    store: ArtifactPin,
) -> tuple[dict[str, Any], bool]:
    """Return ``(artifact, was_pinned)`` for ``I_n`` at ``page_idx``.

    If the pin store already holds an artifact for ``sha256(I_n)``, that pinned
    artifact is returned (``was_pinned=True``) and written back to the payload's
    ``artifact-NNNN.json`` so the render subprocess consumes the same pinned
    geometry the guard does. Otherwise the payload's current artifact is read,
    stored in the pin (first-seen wins), and returned (``was_pinned=False``).

    After this call, the artifact on disk is the deterministic ``g(I_n)`` for
    this input image for the lifetime of the pin store.
    """
    image_hash = image_sha256(image_path)
    suffix = f"-{page_idx:04d}"
    artifact_file = payload_path / f"artifact{suffix}.json"
    if not artifact_file.exists():
        artifact_file = payload_path / "artifact.json"

    cached = store.get(image_hash)
    if cached is not None:
        # Reuse the pinned artifact: write it back so subprocess + guard agree.
        artifact_file.write_text(
            json.dumps(cached, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return cached, True

    # First-seen: read the current artifact and pin it for this I_n.
    artifact = json.loads(artifact_file.read_text(encoding="utf-8"))
    store.put(image_hash, artifact)
    return artifact, False
