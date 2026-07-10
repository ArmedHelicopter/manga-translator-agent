"""Tests for mga.cultural.terminology_db — TOML terminology database."""

from pathlib import Path

from mga.cultural.terminology_db import TerminologyDB, TermState


def test_empty_db():
    db = TerminologyDB()
    assert db.size == 0
    assert db.lookup("anything") is None


def test_register_and_lookup():
    db = TerminologyDB()
    db.register(TermState(term_jp="刀", term_target="sword", strategy="preserve"))
    assert db.size == 1
    found = db.lookup("刀")
    assert found is not None
    assert found.term_target == "sword"


def test_load_from_toml(tmp_path):
    term_dir = tmp_path / "terminology"
    term_dir.mkdir()
    (term_dir / "terms.toml").write_text(
        '[terms]\n'
        'katana = { term_jp = "刀", term_target = "sword", strategy = "preserve", confirmed = true }\n',
        encoding="utf-8",
    )
    db = TerminologyDB.load(tmp_path)
    assert db.size == 1
    found = db.lookup("刀")
    assert found is not None
    assert found.term_target == "sword"
    assert found.confirmed is True


def test_load_nonexistent_dir(tmp_path):
    db = TerminologyDB.load(tmp_path / "nonexistent")
    assert db.size == 0


def test_export(tmp_path):
    db = TerminologyDB()
    db.register(TermState(term_jp="桜", term_target="cherry blossom"))
    out = db.export(tmp_path)
    assert out.exists()
    assert "桜" in out.read_text(encoding="utf-8")


def test_get_injection_context():
    db = TerminologyDB()
    db.register(TermState(
        term_jp="刀", term_target="sword", reading="かたな",
        strategy="preserve", notes="keep original",
    ))
    ctx = db.get_injection_context(["刀"])
    assert "刀" in ctx
    assert "sword" in ctx
    assert "preserve" in ctx


def test_get_injection_context_empty():
    db = TerminologyDB()
    ctx = db.get_injection_context(["nonexistent"])
    assert ctx == ""
