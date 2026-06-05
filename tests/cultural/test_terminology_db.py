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


def test_items_returns_terms_in_stable_order():
    db = TerminologyDB()
    db.register(TermState(term_jp="b", term_target="B"))
    db.register(TermState(term_jp="a", term_target="A"))

    assert [item.term_jp for item in db.items()] == ["a", "b"]


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


def test_loads_documented_categorized_toml_sections(tmp_path):
    term_dir = tmp_path / "terminology"
    term_dir.mkdir()
    (term_dir / "glass_and_blade.toml").write_text(
        '[system]\n'
        'glass_join = { zh = "glass mending", type = "ability", strategy = "literal", notes = "Akari repair art" }\n'
        '\n'
        '[culture]\n'
        'senpai = { zh = "senior", strategy = "adapt", notes = "Relationship title" }\n',
        encoding="utf-8",
    )

    db = TerminologyDB.load(tmp_path)

    assert db.size == 2
    glass = db.lookup("glass_join")
    assert glass is not None
    assert glass.term_target == "glass mending"
    assert glass.strategy == "literal"
    assert glass.notes == "Akari repair art"
    assert glass.problem_types == ["system", "ability"]
    senpai = db.lookup("senpai")
    assert senpai is not None
    assert senpai.term_target == "senior"
    assert senpai.problem_types == ["culture"]


def test_load_and_export_pending_human_review_marker(tmp_path):
    term_dir = tmp_path / "terminology"
    term_dir.mkdir()
    (term_dir / "terms.toml").write_text(
        '[terms]\n'
        'katana = { term_jp = "katana", term_target = "sword", pending_human_review = true }\n',
        encoding="utf-8",
    )

    db = TerminologyDB.load(tmp_path)
    found = db.lookup("katana")

    assert found is not None
    assert found.pending_human_review is True
    assert found.confirmed is False

    out = db.export(tmp_path)
    exported = out.read_text(encoding="utf-8")
    assert "pending_human_review = true" in exported


def test_load_export_and_inject_review_fields(tmp_path):
    term_dir = tmp_path / "terminology"
    term_dir.mkdir()
    (term_dir / "terms.toml").write_text(
        '[terms]\n'
        'glass_join = { term_jp = "glass join", term_target = "glass mending", '
        'candidate_translations = ["glass mending", "crystal join"], '
        'accepted_reason = "Matches established ritual term.", '
        'rejected_reasons = { "crystal join" = "Sounds like a material name." }, '
        'applicability_scope = "Use for the named repair art only." }\n',
        encoding="utf-8",
    )

    db = TerminologyDB.load(tmp_path)
    found = db.lookup("glass join")

    assert found is not None
    assert found.candidate_translations == ["glass mending", "crystal join"]
    assert found.accepted_reason == "Matches established ritual term."
    assert found.rejected_reasons == {
        "crystal join": "Sounds like a material name.",
    }
    assert found.applicability_scope == "Use for the named repair art only."

    ctx = db.get_injection_context(["glass join"])
    assert "candidates=glass mending, crystal join" in ctx
    assert "accepted_reason=Matches established ritual term." in ctx
    assert "rejected=crystal join: Sounds like a material name." in ctx
    assert "scope=Use for the named repair art only." in ctx

    out = db.export(tmp_path)
    exported = out.read_text(encoding="utf-8")
    assert "candidate_translations" in exported
    assert "accepted_reason" in exported
    assert "rejected_reasons" in exported
    assert "applicability_scope" in exported


def test_get_injection_context_includes_problem_types():
    db = TerminologyDB()
    db.register(TermState(
        term_jp="glass_join",
        term_target="glass mending",
        problem_types=["system", "ability"],
    ))

    ctx = db.get_injection_context(["glass_join"])

    assert "types=system, ability" in ctx


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
