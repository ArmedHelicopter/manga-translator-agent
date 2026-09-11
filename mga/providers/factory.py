"""Unified provider factory - single source of truth for provider creation.

This module consolidates all provider creation logic from:
- registry.py (legacy, deprecated)
- factory.py (new, now canonical)

The cascade logic is in cascade.py.
"""

from __future__ import annotations

import importlib
from typing import Any

from ..exceptions import ProviderError

# ── Provider Registry ───────────────────────────────────────────────────────────

_PROVIDER_MAP: dict[str, tuple[str, str]] = {
    "openai": (".openai_provider", "OpenAIProvider"),
    "anthropic": (".anthropic_provider", "AnthropicProvider"),
    "gemini": (".gemini_provider", "GeminiProvider"),
    "deepseek": (".deepseek_provider", "DeepSeekProvider"),
    "ollama": (".ollama_provider", "OllamaProvider"),
    "lmstudio": (".lmstudio_provider", "LMStudioProvider"),
    "vllm": (".vllm_provider", "VLLMProvider"),
    "openrouter": (".openrouter_provider", "OpenRouterProvider"),
    "llamacpp": (".llamacpp_provider", "LlamaCppProvider"),
    "cohere": (".cohere_provider", "CohereProvider"),
    "mistral": (".mistral_provider", "MistralProvider"),
    "groq": (".groq_provider", "GroqProvider"),
    "mimo": (".mimo_provider", "MimoProvider"),
    "generic": (".generic_provider", "GenericOpenAIProvider"),
}

# Provider profiles with default settings
# These are OpenAI-compatible gateways that can be used without custom provider classes.
# Each profile defines: api_key_env, base_url, and default models.
_PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    # ── Official Providers ──────────────────────────────────────────────────────
    "mimo": {
        "provider_type": "mimo",
        "api_key_env": "MIMO_API_KEY",
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "vision_model": "mimo-v2.5-pro",
        "text_model": "mimo-v2.5-pro",
    },
    # ── Chinese AI Providers ────────────────────────────────────────────────────
    "siliconflow": {
        "provider_type": "openai",
        "api_key_env": "SILICONFLOW_API_KEY",
        "base_url": "https://api.siliconflow.cn/v1",
        "vision_model": "Qwen/Qwen-VL-Plus",
        "text_model": "Qwen/Qwen2.5-72B-Instruct",
    },
    "zhipu": {
        "provider_type": "openai",
        "api_key_env": "ZHIPU_API_KEY",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "vision_model": "glm-4v-flash",
        "text_model": "glm-4-flash",
    },
    "kimi": {
        "provider_type": "openai",
        "api_key_env": "MOONSHOT_API_KEY",
        "base_url": "https://api.moonshot.cn/v1",
        "vision_model": "moonshot-v1-vision",
        "text_model": "moonshot-v1-128k",
    },
    "claude": {
        "provider_type": "openai",
        "api_key_env": "CLAUDE_API_KEY",
        "base_url": "https://api.claude.chat/v1",
        "vision_model": "claude-sonnets-chat",
        "text_model": "claude-sonnets-chat",
    },
    "baidu": {
        "provider_type": "openai",
        "api_key_env": "BAIDU_API_KEY",
        "base_url": "https://qianfan.baidubce.com/v2",
        "vision_model": "ernie-4.0-8k",
        "text_model": "ernie-4.0-8k",
    },
    "aliyun": {
        "provider_type": "openai",
        "api_key_env": "ALIYUN_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "vision_model": "qwen-vl-plus",
        "text_model": "qwen-plus",
    },
    "volcengine": {
        "provider_type": "openai",
        "api_key_env": "VOLCENGINE_API_KEY",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "vision_model": "doubao-vision-pro",
        "text_model": "doubao-pro-32k",
    },
    "stepfun": {
        "provider_type": "openai",
        "api_key_env": "STEPFUN_API_KEY",
        "base_url": "https://api.stepfun.com/v1",
        "vision_model": "step-1v-8k",
        "text_model": "step-1-32k",
    },
    # ── International Providers ────────────────────────────────────────────────
    "novita": {
        "provider_type": "openai",
        "api_key_env": "NOVITA_API_KEY",
        "base_url": "https://api.novita.ai/v2",
        "vision_model": "novita/llama-3.3-70b-instruct",
        "text_model": "novita/llama-3.3-70b-instruct",
    },
    "api2d": {
        "provider_type": "openai",
        "api_key_env": "API2D_API_KEY",
        "base_url": "https://api.api2d.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "nebulabox": {
        "provider_type": "openai",
        "api_key_env": "NEBULABOX_API_KEY",
        "base_url": "https://api.nebula-box.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "cherryai": {
        "provider_type": "openai",
        "api_key_env": "CHERRYAI_API_KEY",
        "base_url": "https://api.cherryai.top/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "apikeyfun": {
        "provider_type": "openai",
        "api_key_env": "APIKEYFUN_API_KEY",
        "base_url": "https://api.apikey.fun/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "relaxy": {
        "provider_type": "openai",
        "api_key_env": "RELAXY_API_KEY",
        "base_url": "https://api.relaxy.cn/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "dmxapi": {
        "provider_type": "openai",
        "api_key_env": "DMXAPI_API_KEY",
        "base_url": "https://api.dmxapi.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "modelverse": {
        "provider_type": "openai",
        "api_key_env": "MODELVERSE_API_KEY",
        "base_url": "https://api.modelscope.cn/v1",
        "vision_model": "qwen-vl-plus",
        "text_model": "qwen-plus",
    },
    "pateway": {
        "provider_type": "openai",
        "api_key_env": "PATEWAY_API_KEY",
        "base_url": "https://api.pateway.ai/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "llmstack": {
        "provider_type": "openai",
        "api_key_env": "PIPELLM_API_KEY",
        "base_url": "https://api.pipellm.ai/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "rightcode": {
        "provider_type": "openai",
        "api_key_env": "RIGHTCODE_API_KEY",
        "base_url": "https://api.rightcodeai.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "packycode": {
        "provider_type": "openai",
        "api_key_env": "PACKYCODE_API_KEY",
        "base_url": "https://api.packycode.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "sudocode": {
        "provider_type": "openai",
        "api_key_env": "SUDOCODE_API_KEY",
        "base_url": "https://api.sudocode.ai/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "ctok": {
        "provider_type": "openai",
        "api_key_env": "CTOK_API_KEY",
        "base_url": "https://api.ctok.ai/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "eflowcode": {
        "provider_type": "openai",
        "api_key_env": "EFLOWCODE_API_KEY",
        "base_url": "https://api.eflowcode.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "therouter": {
        "provider_type": "openai",
        "api_key_env": "THEROUTER_API_KEY",
        "base_url": "https://api.therouter.cn/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "sssaicode": {
        "provider_type": "openai",
        "api_key_env": "SSSAICODE_API_KEY",
        "base_url": "https://api.sssai.cn/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "algocode": {
        "provider_type": "openai",
        "api_key_env": "ALGOCODE_API_KEY",
        "base_url": "https://api.algocode.tech/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "crazyrouter": {
        "provider_type": "openai",
        "api_key_env": "CRAZYROUTER_API_KEY",
        "base_url": "https://api.crazyrouter.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "atlascloud": {
        "provider_type": "openai",
        "api_key_env": "ATLASCLOUD_API_KEY",
        "base_url": "https://api.atlascloud.io/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "micu": {
        "provider_type": "openai",
        "api_key_env": "MICU_API_KEY",
        "base_url": "https://api.micu.cn/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "runapi": {
        "provider_type": "openai",
        "api_key_env": "RUNAPI_API_KEY",
        "base_url": "https://api.runapi.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "aihubmix": {
        "provider_type": "openai",
        "api_key_env": "AIHUBMIX_API_KEY",
        "base_url": "https://api.aihubmix.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "claudecn": {
        "provider_type": "openai",
        "api_key_env": "CLAUDECN_API_KEY",
        "base_url": "https://api.claudecn.com/v1",
        "vision_model": "claude-3-5-sonnet",
        "text_model": "claude-3-5-haiku",
    },
    "claudeapi": {
        "provider_type": "openai",
        "api_key_env": "CLAUDEAPI_API_KEY",
        "base_url": "https://api.claudeapi.com/v1",
        "vision_model": "claude-3-5-sonnet",
        "text_model": "claude-3-5-haiku",
    },
    "lemondata": {
        "provider_type": "openai",
        "api_key_env": "LEMON_DATA_API_KEY",
        "base_url": "https://api.lemondata.net/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "cubence": {
        "provider_type": "openai",
        "api_key_env": "CUBENCE_API_KEY",
        "base_url": "https://api.cubence.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "bailing": {
        "provider_type": "openai",
        "api_key_env": "BAILING_API_KEY",
        "base_url": "https://bailing-api.cn/v1",
        "vision_model": "qwen-vl-plus",
        "text_model": "qwen-plus",
    },
    "katcoder": {
        "provider_type": "openai",
        "api_key_env": "KATCODER_API_KEY",
        "base_url": "https://api.katcoder.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "longcat": {
        "provider_type": "openai",
        "api_key_env": "LONGCAT_API_KEY",
        "base_url": "https://api.longcat.studio/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "opencode": {
        "provider_type": "openai",
        "api_key_env": "OPENCODE_API_KEY",
        "base_url": "https://api.opencode.ai/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "codemirror": {
        "provider_type": "openai",
        "api_key_env": "CODEMIRROR_API_KEY",
        "base_url": "https://api.codemirror.cn/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "yunyun": {
        "provider_type": "openai",
        "api_key_env": "YUNYUN_API_KEY",
        "base_url": "https://api.yunyun.cn/v1",
        "vision_model": "qwen-vl-plus",
        "text_model": "qwen-plus",
    },
    "ccsub": {
        "provider_type": "openai",
        "api_key_env": "CCSUB_API_KEY",
        "base_url": "https://api.ccsub.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "byteplus": {
        "provider_type": "openai",
        "api_key_env": "BYTEPLUS_API_KEY",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "vision_model": "doubao-vision-pro",
        "text_model": "doubao-pro-32k",
    },
    "doubioseed": {
        "provider_type": "openai",
        "api_key_env": "DOUBIOSEED_API_KEY",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "vision_model": "doubao-vision-pro",
        "text_model": "doubao-pro-32k",
    },
    "shengsuan": {
        "provider_type": "openai",
        "api_key_env": "SHENGSUAN_API_KEY",
        "base_url": "https://api.shengsuan.cn/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    # ── AWS Bedrock (Special - uses AWS credentials) ─────────────────────────────
    # Note: AWS Bedrock requires special handling with AWS credentials
    # "bedrock": {
    #     "provider_type": "openai",
    #     "api_key_env": "AWS_ACCESS_KEY_ID",
    #     "base_url_env": "AWS_BEDROCK_ENDPOINT",
    #     "vision_model": "claude-3-5-sonnet",
    #     "text_model": "claude-3-5-haiku",
    # },
}


def _load_provider_class(name: str) -> type:
    """Load provider class by name."""
    entry = _PROVIDER_MAP.get(name.lower())
    if entry is None:
        raise ProviderError(f"Unknown provider: {name!r}")
    module_path, class_name = entry
    module = importlib.import_module(module_path, package=__package__)
    return getattr(module, class_name)


def resolve_provider_settings(name: str, settings: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Resolve provider name to concrete type and kwargs.

    Args:
        name: Provider name (openai, anthropic, mimo, etc.)
        settings: Optional settings dict

    Returns:
        (provider_type, resolved_settings) tuple
    """
    provider_name = name.lower()
    resolved = dict(settings or {})

    # Merge with profile if exists
    profile = _PROVIDER_PROFILES.get(provider_name)
    if profile:
        merged = dict(profile)
        merged.update(resolved)
        resolved = merged

    provider_type = str(resolved.pop("provider_type", provider_name)).lower()
    return provider_type, resolved


def create_provider(name: str, settings: dict[str, Any] | None = None, **kwargs: Any):
    """Create a provider instance by name.

    Args:
        name: Provider name (openai, anthropic, mimo, etc.)
        settings: Optional settings dict
        **kwargs: Additional settings as keyword arguments

    Returns:
        LLMProvider instance
    """
    merged = dict(settings or {})
    merged.update(kwargs)

    provider_type, resolved = resolve_provider_settings(name, merged)

    # Check for plugin provider first
    if provider_type not in _PROVIDER_MAP:
        from mga.plugins import has_plugin_class, instantiate_plugin_from_settings
        if has_plugin_class(resolved):
            return instantiate_plugin_from_settings(resolved)

    cls = _load_provider_class(provider_type)
    return cls(**resolved)


def get_provider(name: str, **kwargs: Any):
    """Backward-compatible alias for create_provider."""
    return create_provider(name, kwargs)


def get_default_model(provider: str, stage: str | None = None) -> str:
    """Get default model for a provider and stage.

    Args:
        provider: Provider name
        stage: Optional stage (vision, translation, qa)

    Returns:
        Model name string
    """
    profile = _PROVIDER_PROFILES.get(provider.lower(), {})
    if stage == "vision":
        return str(profile.get("vision_model") or profile.get("model") or "")
    if stage in ("translation", "translate", "qa"):
        return str(profile.get("text_model") or profile.get("translate_model") or profile.get("model") or "")
    return str(profile.get("model") or profile.get("vision_model") or profile.get("text_model") or "")


def list_providers() -> list[str]:
    """List all registered provider names (hardcoded provider classes)."""
    return list(_PROVIDER_MAP.keys())


def list_profiles() -> list[str]:
    """List all provider profile names (OpenAI-compatible gateways)."""
    return list(_PROVIDER_PROFILES.keys())


def list_all_providers() -> list[str]:
    """List all available providers (both hardcoded classes and profiles)."""
    return sorted(set(_PROVIDER_MAP.keys()) | set(_PROVIDER_PROFILES.keys()))


def get_provider_info(name: str) -> dict[str, Any] | None:
    """Get detailed info about a provider.

    Returns a dict with keys:
        - type: "class" or "profile"
        - provider_type: the underlying provider type (e.g., "openai")
        - api_key_env: environment variable for API key
        - base_url: API base URL
        - vision_model: default vision model
        - text_model: default text model

    Returns None if provider not found.
    """
    name = name.lower()

    # Check if it's a hardcoded class
    if name in _PROVIDER_MAP:
        info: dict[str, Any] = {"type": "class", "name": name}
        # Augment with lazy-registry metadata if available (vision/structured/notes)
        try:
            from .lazy_registry import get_lazy_provider_info
            lazy = get_lazy_provider_info(name)
            if lazy is not None:
                if lazy.get("vision") is not None:
                    info["vision"] = lazy["vision"]
                if lazy.get("structured"):
                    info["structured"] = lazy["structured"]
                if lazy.get("notes"):
                    info["notes"] = lazy["notes"]
        except Exception:
            pass
        return info

    # Check if it's a profile
    profile = _PROVIDER_PROFILES.get(name)
    if profile:
        return {
            "type": "profile",
            "name": name,
            "provider_type": profile.get("provider_type", "openai"),
            "api_key_env": profile.get("api_key_env", ""),
            "base_url": profile.get("base_url", ""),
            "vision_model": profile.get("vision_model", ""),
            "text_model": profile.get("text_model", ""),
        }

    return None


# ── Re-export for convenience ──────────────────────────────────────────────────

from .base import LLMProvider

__all__ = [
    "create_provider",
    "get_provider",
    "resolve_provider_settings",
    "get_default_model",
    "get_provider_info",
    "list_providers",
    "list_profiles",
    "list_all_providers",
    "LLMProvider",
]