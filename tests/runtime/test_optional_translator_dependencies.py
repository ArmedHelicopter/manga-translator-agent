import subprocess
import sys


def test_missing_optional_translator_sdks_do_not_block_cli_startup():
    code = r"""
import builtins
import runpy
import sys

blocked_modules = {"ctranslate2", "deepl", "groq"}
real_import = builtins.__import__

def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name in blocked_modules:
        raise ImportError(f"No module named {name!r}")
    if name == "google" and "genai" in fromlist:
        raise ImportError("No module named 'google.genai'")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = fake_import

sys.argv = ["manga_translator", "--help"]
try:
    runpy.run_module("manga_translator", run_name="__main__")
except SystemExit as exc:
    if exc.code not in (0, None):
        raise
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "usage: manga_translator" in result.stdout
