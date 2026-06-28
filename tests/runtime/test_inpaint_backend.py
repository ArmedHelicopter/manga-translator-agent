"""Tests for inpaint_backend configuration and run_export_artifact/run_render_only integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mga.models.project import ProjectConfig
from mga.runtime_bridge.external import run_export_artifact, run_render_only


class TestProjectConfigInpaintBackend:
    """Tests for ProjectConfig.inpaint_backend field."""

    def test_default_inpaint_backend(self):
        """Default inpaint_backend is 'auto'."""
        cfg = ProjectConfig()
        assert cfg.inpaint_backend == "auto"

    def test_custom_inpaint_backend(self):
        """Custom inpaint_backend is accepted."""
        cfg = ProjectConfig(inpaint_backend="lama_large")
        assert cfg.inpaint_backend == "lama_large"

    def test_default_chinese_variant(self):
        """Default chinese_variant is 'auto'."""
        cfg = ProjectConfig()
        assert cfg.chinese_variant == "auto"

    def test_custom_chinese_variant(self):
        """Custom chinese_variant is accepted."""
        cfg = ProjectConfig(chinese_variant="s2t")
        assert cfg.chinese_variant == "s2t"


class TestRunExportArtifactInpaintBackend:
    """Tests for run_export_artifact inpaint_backend parameter."""

    def test_auto_inpaint_backend_writes_lama_large(self, tmp_path: Path, monkeypatch):
        """'auto' uses LaMa in Pass 1 so erased regions are reconstructed."""
        image = tmp_path / "page.png"
        from PIL import Image
        Image.new("RGB", (8, 8), "white").save(image)
        payload_dir = tmp_path / "payload"

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", lambda *a, **kw: Completed())
        run_export_artifact(input_dir=image, payload_dir=payload_dir)

        export_config = json.loads((payload_dir / "runtime-export-config.json").read_text(encoding="utf-8"))
        assert export_config["inpainter"]["inpainter"] == "lama_large"

    def test_custom_inpaint_backend_writes_selected(self, tmp_path: Path, monkeypatch):
        """Custom inpaint_backend writes the selected backend to export config."""
        image = tmp_path / "page.png"
        from PIL import Image
        Image.new("RGB", (8, 8), "white").save(image)
        payload_dir = tmp_path / "payload"

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", lambda *a, **kw: Completed())
        run_export_artifact(input_dir=image, payload_dir=payload_dir, inpaint_backend="lama_large")

        export_config = json.loads((payload_dir / "runtime-export-config.json").read_text(encoding="utf-8"))
        assert export_config["inpainter"]["inpainter"] == "lama_large"

    def test_invalid_inpaint_backend_raises(self, tmp_path: Path):
        """Invalid inpaint_backend raises ValueError."""
        image = tmp_path / "page.png"
        from PIL import Image
        Image.new("RGB", (8, 8), "white").save(image)
        payload_dir = tmp_path / "payload"

        with pytest.raises(ValueError, match="Invalid inpaint_backend"):
            run_export_artifact(input_dir=image, payload_dir=payload_dir, inpaint_backend="invalid_backend")


class TestRunRenderOnlyInpaintBackend:
    """Tests for run_render_only inpaint_backend parameter."""

    def test_auto_inpaint_backend_no_config_file(self, tmp_path: Path, monkeypatch):
        """'auto' (default) does not write a render config file."""
        payload_dir = tmp_path / "payload"
        payload_dir.mkdir()
        output_dir = tmp_path / "output"

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", lambda *a, **kw: Completed())
        monkeypatch.setattr("mga.runtime_bridge.external._collect_rendered_images", lambda d: [])

        run_render_only(payload_dir=payload_dir, output_dir=output_dir)

        # No render config file should be written when inpaint_backend is "auto"
        assert not (output_dir / "runtime-render-config.json").exists()

    def test_custom_inpaint_backend_writes_config(self, tmp_path: Path, monkeypatch):
        """Custom inpaint_backend writes a render config file with the selected backend."""
        payload_dir = tmp_path / "payload"
        payload_dir.mkdir()
        output_dir = tmp_path / "output"

        class Completed:
            returncode = 0
            stdout = ""
            stderr = ""

        monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", lambda *a, **kw: Completed())
        monkeypatch.setattr("mga.runtime_bridge.external._collect_rendered_images", lambda d: [])

        run_render_only(payload_dir=payload_dir, output_dir=output_dir, inpaint_backend="sd")

        render_config = json.loads((output_dir / "runtime-render-config.json").read_text(encoding="utf-8"))
        assert render_config["inpainter"]["inpainter"] == "sd"

    def test_invalid_inpaint_backend_raises(self, tmp_path: Path):
        """Invalid inpaint_backend raises ValueError."""
        payload_dir = tmp_path / "payload"
        payload_dir.mkdir()

        with pytest.raises(ValueError, match="Invalid inpaint_backend"):
            run_render_only(payload_dir=payload_dir, output_dir=tmp_path / "out", inpaint_backend="invalid")
