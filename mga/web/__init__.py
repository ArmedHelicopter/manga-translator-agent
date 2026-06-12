"""Web UI entrypoints for Manga Translate Agent.

Provides a blue-white themed web interface with:
- FastAPI + Jinja2 templates
- Tutorial wizard for first-time setup
- Bilingual support (English/Chinese)
- Translation, memory, profile, and settings management
"""

from .frontend import create_app, run_web_server

__all__ = ["create_app", "run_web_server"]
