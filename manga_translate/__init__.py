"""Compatibility shim: manga_translate -> mga namespace.

This package re-exports mga symbols under the legacy 'manga_translate' namespace
so existing tests pass without modification. All business logic lives in mga/.
"""

__version__ = "0.1.0"
