"""Tests for content-addressed OCR artifact pinning (mga.runtime_bridge.artifact_cache).

Pinning makes g(I_n) deterministic: the same input image always renders against
the same pinned OCR artifact, even if the runtime re-runs and would otherwise
produce a different one.
"""

from __future__ import annotations

import json
from pathlib import Path

from mga.runtime_bridge.artifact_cache import (
    ArtifactPin,
    image_sha256,
    resolve_pinned_artifact,
)


def _write_img(path: Path, marker: bytes) -> Path:
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + marker)
    return path


def _artifact(idx: int, text: str = "x") -> dict:
    return {
        "version": 1,
        "page_index": idx,
        "text_regions": [
            {"index": 0, "text": text, "lines": [[[0, 0], [10, 0], [10, 10], [0, 10]]], "prob": 0.9},
        ],
        "render_config": {},
        "image_shape": [100, 100, 3],
    }


class TestImageSha256:
    def test_deterministic_for_same_bytes(self, tmp_path: Path) -> None:
        a = _write_img(tmp_path / "a.png", b"abc")
        b = _write_img(tmp_path / "b.png", b"abc")
        assert image_sha256(a) == image_sha256(b)

    def test_differs_for_different_bytes(self, tmp_path: Path) -> None:
        a = _write_img(tmp_path / "a.png", b"abc")
        b = _write_img(tmp_path / "b.png", b"abd")
        assert image_sha256(a) != image_sha256(b)


class TestArtifactPin:
    def test_put_then_get(self, tmp_path: Path) -> None:
        store = ArtifactPin(tmp_path / "pin.json")
        art = _artifact(0, "hello")
        store.put("hash0", art)
        assert store.has("hash0")
        assert store.get("hash0") == art

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        store = ArtifactPin(tmp_path / "pin.json")
        assert store.get("nope") is None
        assert not store.has("nope")

    def test_persists_across_instances(self, tmp_path: Path) -> None:
        path = tmp_path / "pin.json"
        ArtifactPin(path).put("hash1", _artifact(0, "first"))
        # A new instance loading the same file sees the pinned artifact.
        assert ArtifactPin(path).get("hash1") == _artifact(0, "first")

    def test_malformed_store_starts_empty(self, tmp_path: Path) -> None:
        (tmp_path / "pin.json").write_text("{broken", encoding="utf-8")
        store = ArtifactPin(tmp_path / "pin.json")
        assert store.get("anything") is None  # fail-safe, not crash


class TestResolvePinnedArtifact:
    def test_first_call_pins_current_artifact(self, tmp_path: Path) -> None:
        img = _write_img(tmp_path / "page.png", b"img-bytes")
        (tmp_path / "artifact-0000.json").write_text(
            json.dumps(_artifact(0, "original")), encoding="utf-8"
        )
        store = ArtifactPin(tmp_path / "pin.json")
        art, was_pinned = resolve_pinned_artifact(tmp_path, 0, img, store)
        assert was_pinned is False
        assert art["text_regions"][0]["text"] == "original"
        # Pin store now holds this artifact keyed by sha256(img).
        assert store.has(image_sha256(img))

    def test_second_call_reuses_pinned_overriding_changed_artifact(self, tmp_path: Path) -> None:
        """The core determinism guarantee: even if a fresh Pass-1 overwrites the
        artifact with different content, resolve_pinned_artifact restores the
        pinned (first-seen) artifact so g(I_n) is stable."""
        img = _write_img(tmp_path / "page.png", b"img-bytes")
        art_file = tmp_path / "artifact-0000.json"
        store_path = tmp_path / "pin.json"

        # First run: pin the original artifact.
        art_file.write_text(json.dumps(_artifact(0, "original")), encoding="utf-8")
        resolve_pinned_artifact(tmp_path, 0, img, ArtifactPin(store_path))

        # Simulate a fresh non-deterministic Pass-1 overwriting the artifact.
        art_file.write_text(json.dumps(_artifact(0, "DIFFERENT_FROM_RERUN")), encoding="utf-8")

        # Second run: the pinned (original) artifact is restored.
        store = ArtifactPin(store_path)
        art, was_pinned = resolve_pinned_artifact(tmp_path, 0, img, store)
        assert was_pinned is True
        assert art["text_regions"][0]["text"] == "original"
        # And it's written back to the payload file (subprocess + guard agree).
        on_disk = json.loads(art_file.read_text(encoding="utf-8"))
        assert on_disk["text_regions"][0]["text"] == "original"

    def test_different_images_pinned_independently(self, tmp_path: Path) -> None:
        """Two distinct input images each get their own pinned artifact."""
        img_a = _write_img(tmp_path / "a.png", b"A")
        img_b = _write_img(tmp_path / "b.png", b"B")
        store = ArtifactPin(tmp_path / "pin.json")

        # Page 0 (image A) — write artifact-0000, pin.
        (tmp_path / "artifact-0000.json").write_text(json.dumps(_artifact(0, "A-text")), encoding="utf-8")
        resolve_pinned_artifact(tmp_path, 0, img_a, store)
        # Page 1 (image B) — write artifact-0001, pin.
        (tmp_path / "artifact-0001.json").write_text(json.dumps(_artifact(1, "B-text")), encoding="utf-8")
        resolve_pinned_artifact(tmp_path, 1, img_b, store)

        assert store.get(image_sha256(img_a))["text_regions"][0]["text"] == "A-text"
        assert store.get(image_sha256(img_b))["text_regions"][0]["text"] == "B-text"
