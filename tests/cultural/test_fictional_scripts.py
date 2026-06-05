from __future__ import annotations

from mga.cultural.fictional_scripts import load_fictional_script_context


def test_load_fictional_script_context_reads_project_toml(tmp_path):
    scripts_dir = tmp_path / "fictional_scripts"
    scripts_dir.mkdir()
    (scripts_dir / "abyss.toml").write_text(
        """
[meta]
name = "Abyss Script"
source = "Made in Abyss"
has_mapping = true

[mapping]
"*" = "a"
"#" = "i"

[notes]
asterisk = "context-sensitive"
""".strip(),
        encoding="utf-8",
    )

    context = load_fictional_script_context(tmp_path)

    assert context == {
        "abyss": {
            "name": "Abyss Script",
            "source": "Made in Abyss",
            "has_mapping": True,
            "mapping": {"*": "a", "#": "i"},
            "notes": {"asterisk": "context-sensitive"},
        }
    }
