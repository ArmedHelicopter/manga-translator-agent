from __future__ import annotations

from importlib import import_module

try:
    import colorama
except ModuleNotFoundError:
    colorama = None

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if colorama is not None:
    colorama.init(autoreset=True)

if load_dotenv is not None:
    load_dotenv()

__all__ = [
    "Config",
    "Context",
    "MangaTranslator",
    "TranslationInterrupt",
    "apply_dictionary",
    "load_dictionary",
    "logger",
    "set_main_logger",
]

_LAZY_IMPORTS = {
    "Config": (".config", "Config"),
    "Context": (".utils", "Context"),
    "MangaTranslator": (".manga_translator", "MangaTranslator"),
    "TranslationInterrupt": (".manga_translator", "TranslationInterrupt"),
    "apply_dictionary": (".manga_translator", "apply_dictionary"),
    "load_dictionary": (".manga_translator", "load_dictionary"),
    "logger": (".manga_translator", "logger"),
    "set_main_logger": (".manga_translator", "set_main_logger"),
}


def __getattr__(name: str):
    if name not in _LAZY_IMPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attr_name = _LAZY_IMPORTS[name]
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
