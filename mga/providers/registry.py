"""Provider registry with fallback cascade."""

from __future__ import annotations

from typing import Any

from ..exceptions import ProviderError
from .base import LLMProvider

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
}

_PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    # ── Official Providers ──────────────────────────────────────────────────────
    "mimo": {
        "provider_type": "openai",
        "api_key_env": "MIMO_API_KEY",
        "base_url_env": "MIMO_BASE_URL",
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "vision_model": "mimo-v2.5",
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
    "aliyun": {
        "provider_type": "openai",
        "api_key_env": "ALIYUN_API_KEY",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "vision_model": "qwen-vl-plus",
        "text_model": "qwen-plus",
    },
    "bailing": {
        "provider_type": "openai",
        "api_key_env": "BAILING_API_KEY",
        "base_url": "https://bailing-api.cn/v1",
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
    "modelverse": {
        "provider_type": "openai",
        "api_key_env": "MODELVERSE_API_KEY",
        "base_url": "https://api.modelscope.cn/v1",
        "vision_model": "qwen-vl-plus",
        "text_model": "qwen-plus",
    },
    "yunyun": {
        "provider_type": "openai",
        "api_key_env": "YUNYUN_API_KEY",
        "base_url": "https://api.yunyun.cn/v1",
        "vision_model": "qwen-vl-plus",
        "text_model": "qwen-plus",
    },
    # ── Claude Proxies ──────────────────────────────────────────────────────────
    "claudeapi": {
        "provider_type": "openai",
        "api_key_env": "CLAUDEAPI_API_KEY",
        "base_url": "https://api.claudeapi.com/v1",
        "vision_model": "claude-3-5-sonnet",
        "text_model": "claude-3-5-haiku",
    },
    "claudecn": {
        "provider_type": "openai",
        "api_key_env": "CLAUDECN_API_KEY",
        "base_url": "https://api.claudecn.com/v1",
        "vision_model": "claude-3-5-sonnet",
        "text_model": "claude-3-5-haiku",
    },
    # ── More Chinese Gateways ───────────────────────────────────────────────────
    "pateway": {
        "provider_type": "openai",
        "api_key_env": "PATEWAY_API_KEY",
        "base_url": "https://api.pateway.ai/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "shengsuan": {
        "provider_type": "openai",
        "api_key_env": "SHENGSUAN_API_KEY",
        "base_url": "https://api.shengsuan.cn/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    "ccsub": {
        "provider_type": "openai",
        "api_key_env": "CCSUB_API_KEY",
        "base_url": "https://api.ccsub.com/v1",
        "vision_model": "gpt-4o",
        "text_model": "gpt-4o-mini",
    },
    # ── International Providers ────────────────────────────────────────────────
    "novita": {
        "provider_type": "openai",
        "api_key_env": "NOVITA_API_KEY",
        "base_url": "https://api.novita.ai/v2",
        "vision_model": "novita/llama-3.3-70b-instruct",
        "text_model": "novita/llama-3.3-70b-instruct",
    },
    # ── More Generic Gateways ────────────────────────────────────────────────────
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
}

_VALID_NAMES: frozenset[str] = frozenset(set(_PROVIDER_MAP) | set(_PROVIDER_PROFILES))


def get_provider_model_default(name: str, stage: str | None = None) -> str:
    """Return a non-secret default model for built-in compatible provider profiles."""

    profile = _PROVIDER_PROFILES.get(name.lower(), {})
    if stage == "vision":
        return str(profile.get("vision_model") or profile.get("model") or "")
    if stage in {"translation", "translate", "qa"}:
        return str(profile.get("text_model") or profile.get("translate_model") or profile.get("model") or "")
    return str(profile.get("model") or profile.get("vision_model") or profile.get("text_model") or "")


def resolve_provider_settings(name: str, settings: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Resolve a configured provider name into a concrete provider type and kwargs."""

    provider_name = name.lower()
    resolved = dict(settings or {})
    profile = _PROVIDER_PROFILES.get(provider_name)
    if profile:
        merged = dict(profile)
        merged.update(resolved)
        resolved = merged

    provider_type = str(resolved.pop("provider_type", provider_name)).lower()
    return provider_type, resolved


def _load_provider_class(name: str) -> type[LLMProvider]:
    entry = _PROVIDER_MAP.get(name.lower())
    if entry is None:
        raise ProviderError(f"Unknown provider: {name!r}")
    module_path, class_name = entry
    import importlib
    module = importlib.import_module(module_path, package=__package__)
    return getattr(module, class_name)


def get_provider(name: str, **kwargs: Any) -> LLMProvider:
    """Instantiate a provider by name."""
    provider_name, settings = resolve_provider_settings(name, kwargs)

    if provider_name not in _PROVIDER_MAP:
        from mga.plugins import has_plugin_class, instantiate_plugin_from_settings

        if has_plugin_class(settings):
            return instantiate_plugin_from_settings(settings)
    cls = _load_provider_class(provider_name)
    return cls(**settings)


def select_provider(
    stage: str,
    config: dict[str, Any],
    force_local: bool = False,
) -> LLMProvider:
    """Select provider for a stage with primary -> fallback -> local cascade.

    ``config`` should have the shape::

        {
            "stages": {"vision": {"primary": "openai", "fallback": "gemini", "local": "ollama"}},
            "providers": {"openai": {"api_key": "...", ...}},
        }
    """
    stages = config.get("stages", {})
    providers = config.get("providers", {})
    stage_config = stages.get(stage, {})

    if force_local:
        name = stage_config.get("local")
        if not name:
            raise ProviderError(f"No local provider configured for stage {stage!r}")
        return get_provider(name, **providers.get(name, {}))

    from .cascade import ProviderCandidate, ProviderCascadeAdapter

    errors = []
    resolved = []
    for key in ("primary", "fallback", "local"):
        name = stage_config.get(key)
        if name:
            settings = dict(providers.get(name, {}))
            try:
                provider = get_provider(name, **settings)
                candidate = (
                    ProviderCandidate(
                        role=key,
                        provider=name,
                        model=str(settings.get("model", "")),
                        settings=settings,
                    ),
                    provider,
                )
            except Exception as exc:  # noqa: BLE001 - selection should continue through fallback routes.
                errors.append({
                    "role": key,
                    "provider": name,
                    "error": str(exc),
                    "type": type(exc).__name__,
                })
                if resolved:
                    break
                continue
            if errors:
                return provider
            resolved.append(candidate)

    if errors and resolved:
        return resolved[0][1]
    if len(resolved) == 1:
        return resolved[0][1]
    if resolved:
        class _SelectionCascade:
            def __init__(self) -> None:
                self.stage = stage
                self.errors = errors
                self.calls = []

        cascade = _SelectionCascade()
        return ProviderCascadeAdapter(cascade, resolved)

    raise ProviderError(f"No provider available for stage {stage!r}")
