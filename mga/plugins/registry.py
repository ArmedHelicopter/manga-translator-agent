"""Small plugin registry for project-local extension classes."""

from __future__ import annotations

import importlib
from typing import Any

from mga.exceptions import ConfigError

PLUGIN_CLASS_KEYS = ("plugin", "class", "class_path")
PLUGIN_RESERVED_KEYS = set(PLUGIN_CLASS_KEYS) | {"settings"}


def has_plugin_class(settings: dict[str, Any]) -> bool:
    """Return true when settings declare an importable plugin class."""
    return any(bool(settings.get(key)) for key in PLUGIN_CLASS_KEYS)


def load_plugin_class(class_path: str) -> type:
    """Load a class from ``module:Class`` or ``module.Class`` notation."""
    if not class_path or not isinstance(class_path, str):
        raise ConfigError("Plugin class path must be a non-empty string.")
    if ":" in class_path:
        module_name, class_name = class_path.split(":", 1)
    else:
        module_name, _, class_name = class_path.rpartition(".")
    if not module_name or not class_name:
        raise ConfigError(
            f"Invalid plugin class path {class_path!r}; expected 'module:Class'."
        )
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 - surface import failures as config errors.
        raise ConfigError(f"Could not import plugin module {module_name!r}: {exc}") from exc
    try:
        cls = getattr(module, class_name)
    except AttributeError as exc:
        raise ConfigError(
            f"Plugin module {module_name!r} has no class {class_name!r}."
        ) from exc
    if not isinstance(cls, type):
        raise ConfigError(f"Plugin target {class_path!r} is not a class.")
    return cls


def instantiate_plugin_from_settings(settings: dict[str, Any]) -> Any:
    """Instantiate a plugin from provider-style settings."""
    class_path = _class_path_from(settings)
    cls = load_plugin_class(class_path)
    kwargs = _constructor_kwargs(settings)
    return cls(**kwargs)


def instantiate_plugin_from_config(config: str | dict[str, Any]) -> Any:
    """Instantiate a plugin from string or mapping config."""
    if isinstance(config, str):
        return load_plugin_class(config)()
    if not isinstance(config, dict):
        raise ConfigError("Plugin config must be a class path string or mapping.")
    return instantiate_plugin_from_settings(config)


def _class_path_from(settings: dict[str, Any]) -> str:
    for key in PLUGIN_CLASS_KEYS:
        value = settings.get(key)
        if value:
            return str(value)
    raise ConfigError("Plugin config is missing a 'plugin', 'class', or 'class_path' value.")


def _constructor_kwargs(settings: dict[str, Any]) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    explicit_settings = settings.get("settings")
    if isinstance(explicit_settings, dict):
        kwargs.update(explicit_settings)
    kwargs.update({
        key: value
        for key, value in settings.items()
        if key not in PLUGIN_RESERVED_KEYS
    })
    return kwargs
