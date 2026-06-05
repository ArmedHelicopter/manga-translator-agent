"""Runtime configuration loading for Phase 1."""

from __future__ import annotations

import os
from pathlib import Path

import toml
from toml import TomlDecodeError

from ..exceptions import ConfigError
from ..models import ProjectConfig, ProviderRoute, StageProviderConfig
from ..providers.registry import get_provider_model_default

DEFAULT_CONFIG_PATH = Path("configs/providers.toml")
SUPPORTED_STAGE_NAMES = ("vision", "translation", "qa")
STAGE_CONFIG_KEYS = {
    "vision": "vision",
    "translation": "translation",
    "qa": "qa",
}
CONFIG_ENV_VAR = "MANGA_TRANSLATE_CONFIG"

def _resolve_config_path(config_path: str | None = None) -> Path:
    if config_path:
        return Path(config_path)

    env_path = os.getenv(CONFIG_ENV_VAR)
    if env_path:
        return Path(env_path)

    return DEFAULT_CONFIG_PATH


def load_provider_settings(config_path: str | None = None) -> dict:
    """Load raw provider settings from TOML."""

    path = _resolve_config_path(config_path)
    if not path.exists():
        raise ConfigError(
            f"Provider config not found at {path}. "
            f"Copy configs/providers.toml.example to {path} and fill in your API key."
        )

    try:
        data = toml.load(path)
    except TomlDecodeError as exc:
        raise ConfigError(
            f"Invalid TOML in provider config at {path}: {exc}. "
            "Remove any JSON blocks or trailing braces and keep the file in TOML format."
        ) from exc
    if "stages" not in data or "providers" not in data:
        raise ConfigError(
            "Provider config must define both [stages] and [providers] sections. "
            "Start from configs/providers.toml.example and keep at least "
            "[stages.vision], [stages.translation], and [providers.openai]."
        )
    data["providers"] = {
        name: _resolve_env_placeholders(settings)
        for name, settings in data.get("providers", {}).items()
    }
    return data


def _resolve_env_placeholders(value):
    if isinstance(value, dict):
        return {k: _resolve_env_placeholders(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_placeholders(v) for v in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_name = value[2:-1]
        return os.getenv(env_name, "")
    return value


def _build_stage_route(stage_name: str, stage_data: dict, providers_data: dict) -> StageProviderConfig:
    primary_name = stage_data.get("primary")
    if not primary_name:
        raise ConfigError(f"Stage '{stage_name}' is missing a primary provider.")
    if primary_name not in providers_data:
        raise ConfigError(f"Stage '{stage_name}' references unknown provider '{primary_name}'.")

    model_key = "vision_model" if stage_name == "vision" else "text_model"
    primary_settings = providers_data[primary_name]
    primary_model = (
        primary_settings.get(model_key)
        or primary_settings.get("model")
        or get_provider_model_default(primary_name, stage_name)
    )
    if not primary_model:
        raise ConfigError(f"Provider '{primary_name}' is missing '{model_key}' for stage '{stage_name}'.")

    fallback_route = None
    fallback_name = stage_data.get("fallback")
    if fallback_name:
        if fallback_name not in providers_data:
            raise ConfigError(
                f"Stage '{stage_name}' references unknown fallback provider '{fallback_name}'."
            )
        fallback_settings = providers_data[fallback_name]
        fallback_route = ProviderRoute(
            provider=fallback_name,
            model=(
                fallback_settings.get(model_key)
                or fallback_settings.get("model")
                or get_provider_model_default(fallback_name, stage_name)
            ),
        )

    local_route = None
    local_name = stage_data.get("local")
    if local_name and local_name in providers_data:
        local_settings = providers_data[local_name]
        local_route = ProviderRoute(
            provider=local_name,
            model=(
                local_settings.get(model_key)
                or local_settings.get("model")
                or get_provider_model_default(local_name, stage_name)
            ),
        )

    return StageProviderConfig(
        primary=ProviderRoute(provider=primary_name, model=primary_model),
        fallback=fallback_route,
        local=local_route,
    )


def _stage_data_for(stages_data: dict, stage_name: str) -> dict:
    if stage_name == "translation":
        return stages_data.get("translation") or stages_data.get("translate") or {}
    if stage_name == "qa":
        return stages_data.get("qa") or _stage_data_for(stages_data, "translation")
    return stages_data.get(STAGE_CONFIG_KEYS[stage_name], {})


def build_project_config(
    *,
    input_path: str,
    output_path: str,
    provider_override: str | None,
    save_json: bool,
    dry_run: bool,
    config_path: str | None = None,
) -> tuple[ProjectConfig, dict]:
    """Build the validated project config and return raw provider settings."""

    raw_config = load_provider_settings(config_path)
    stages_data = raw_config["stages"]
    providers_data = raw_config["providers"]

    provider_routes = {
        stage_name: _build_stage_route(
            stage_name,
            _stage_data_for(stages_data, stage_name),
            providers_data,
        )
        for stage_name in SUPPORTED_STAGE_NAMES
    }

    if provider_override:
        if provider_override not in providers_data:
            raise ConfigError(f"The provider override '{provider_override}' is not configured in providers.toml.")
        for stage_name, route in provider_routes.items():
            model_key = "vision_model" if stage_name == "vision" else "text_model"
            provider_model = (
                providers_data[provider_override].get(model_key)
                or providers_data[provider_override].get("model")
                or get_provider_model_default(provider_override, stage_name)
            )
            if not provider_model:
                raise ConfigError(
                    f"Provider override '{provider_override}' is missing '{model_key}' or 'model'."
                )
            provider_routes[stage_name] = StageProviderConfig(
                primary=ProviderRoute(
                    provider=provider_override,
                    model=provider_model,
                ),
                fallback=route.fallback,
                local=route.local,
            )

    resolved_input = Path(input_path).resolve()
    output_dir = Path(output_path).resolve()
    working_dir = resolved_input if resolved_input.is_dir() else output_dir / ".mga-project"
    project_config = ProjectConfig(
        project_name=resolved_input.stem if resolved_input.is_file() else (resolved_input.name or "manga-project"),
        source_lang="ja",
        target_lang="zh-CN",
        working_dir=str(working_dir),
        output_dir=str(output_dir),
        artifact_dir=str(output_dir),
        input_format="images",
        output_format="images",
        reading_direction="rtl",
        local_only=False,
        save_artifacts=True,
        save_debug_json=save_json or dry_run,
        provider_routes=provider_routes,
        provider_settings=dict(providers_data),
        plugins=dict(raw_config.get("plugins", {})),
    )
    return project_config, raw_config
