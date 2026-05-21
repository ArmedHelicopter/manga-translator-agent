"""Tests for CLI novel mode."""

from pathlib import Path

from click.testing import CliRunner

from mga.cli.main import _detect_mode, translate


def _setup_config(tmp_path: Path, monkeypatch) -> Path:
    """Create minimal provider config and set env var."""
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "openai"\n\n'
        '[stages.translation]\nprimary = "openai"\n\n'
        '[providers.openai]\napi_key = "test-key"\nvision_model = "gpt-4o"\ntext_model = "gpt-4o-mini"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MANGA_TRANSLATE_CONFIG", str(config_path))
    return config_path


def test_detect_mode_auto_txt():
    mode, fmt = _detect_mode("chapter.txt", None)
    assert mode == "novel"
    assert fmt == "txt"


def test_detect_mode_auto_epub():
    mode, fmt = _detect_mode("book.epub", None)
    assert mode == "novel"
    assert fmt == "epub"


def test_detect_mode_auto_mobi():
    mode, fmt = _detect_mode("book.mobi", None)
    assert mode == "novel"
    assert fmt == "mobi"


def test_detect_mode_auto_images_dir():
    mode, fmt = _detect_mode("pages/", None)
    assert mode == "manga"
    assert fmt == "images"


def test_detect_mode_explicit_novel():
    mode, fmt = _detect_mode("something.png", "novel")
    assert mode == "novel"
    assert fmt == "png"


def test_detect_mode_explicit_manga():
    mode, fmt = _detect_mode("book.epub", "manga")
    assert mode == "manga"
    assert fmt == "images"


def test_translate_novel_mode_dry_run(tmp_path, monkeypatch):
    """Test --mode novel --dry-run."""
    _setup_config(tmp_path, monkeypatch)
    txt = tmp_path / "test.txt"
    txt.write_text("Hello world", encoding="utf-8")
    output = tmp_path / "out.txt"

    runner = CliRunner()
    result = runner.invoke(translate, [
        str(txt), "-o", str(output),
        "--mode", "novel", "--dry-run", "--lang", "en-zh",
    ])
    assert result.exit_code == 0, result.output
    assert "novel" in result.output.lower() or "Dry run" in result.output


def test_translate_auto_detect_novel_dry_run(tmp_path, monkeypatch):
    """Test auto-detection of novel mode from .txt extension."""
    _setup_config(tmp_path, monkeypatch)
    txt = tmp_path / "chapter.txt"
    txt.write_text("Hello world", encoding="utf-8")
    output = tmp_path / "out.txt"

    runner = CliRunner()
    result = runner.invoke(translate, [
        str(txt), "-o", str(output),
        "--dry-run", "--lang", "en-zh",
    ])
    assert result.exit_code == 0, result.output
    assert "novel" in result.output.lower() or "Dry run" in result.output
