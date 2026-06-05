"""Stage-aware provider cascade utilities."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

from mga.exceptions import ProviderError
from mga.models import ProjectConfig, ProviderRoute

from .registry import get_provider


@dataclass(frozen=True)
class ProviderCandidate:
    """Resolved provider route and instantiation settings."""

    role: str
    provider: str
    model: str = ""
    settings: dict | None = None

    def trace(self, operation: str = "") -> dict[str, str]:
        """Return non-secret provider metadata suitable for artifacts."""
        return {
            "operation": operation,
            "role": self.role,
            "provider": self.provider,
            "model": self.model or str((self.settings or {}).get("model", "")),
        }


class ProviderCascade:
    """Instantiate stage providers with primary -> fallback -> local ordering."""

    def __init__(self, cfg: ProjectConfig, stage: str) -> None:
        self.cfg = cfg
        self.stage = stage
        self.candidates = list(resolve_provider_candidates(cfg, stage))
        self.errors: list[dict[str, str]] = []
        self.calls: list[dict[str, str]] = []

    def call_chat(
        self,
        messages: list[dict],
        *,
        operation: str = "chat",
        trace_context: dict[str, str] | None = None,
        **kwargs,
    ) -> tuple[str, ProviderCandidate]:
        """Call chat on the first provider that succeeds."""
        for candidate in self.candidates:
            try:
                provider = get_provider(candidate.provider, **(candidate.settings or {}))
                result = provider.chat(messages, **kwargs)
                self.calls.append({**(trace_context or {}), **candidate.trace(operation)})
                return result, candidate
            except Exception as exc:  # noqa: BLE001 - record cascade failure and continue.
                self.errors.append({
                    **(trace_context or {}),
                    "operation": operation,
                    "role": candidate.role,
                    "provider": candidate.provider,
                    "error": str(exc),
                    "type": type(exc).__name__,
                })
        raise ProviderError(
            f"No provider available for stage '{self.stage}'. "
            f"Tried: {[c.provider for c in self.candidates]}"
        )

    def call_chat_structured(
        self,
        *,
        messages: list[dict],
        schema: dict,
        operation: str = "chat_structured",
        trace_context: dict[str, str] | None = None,
        **kwargs,
    ) -> tuple[dict, ProviderCandidate]:
        """Call chat_structured on the first provider that succeeds."""
        for candidate in self.candidates:
            try:
                provider = get_provider(candidate.provider, **(candidate.settings or {}))
                result = provider.chat_structured(
                    messages=messages,
                    schema=schema,
                    **kwargs,
                )
                self.calls.append({**(trace_context or {}), **candidate.trace(operation)})
                return result, candidate
            except Exception as exc:  # noqa: BLE001
                self.errors.append({
                    **(trace_context or {}),
                    "operation": operation,
                    "role": candidate.role,
                    "provider": candidate.provider,
                    "error": str(exc),
                    "type": type(exc).__name__,
                })
        raise ProviderError(
            f"No structured chat provider available for stage '{self.stage}'. "
            f"Tried: {[c.provider for c in self.candidates]}"
        )

    def call_vision_structured(
        self,
        *,
        messages: list[dict],
        images: list[bytes],
        schema: dict,
        operation: str = "vision_structured",
        trace_context: dict[str, str] | None = None,
    ) -> tuple[dict, ProviderCandidate]:
        """Call vision_structured on the first provider that succeeds."""
        for candidate in self.candidates:
            try:
                provider = get_provider(candidate.provider, **(candidate.settings or {}))
                result = provider.vision_structured(
                    messages=messages,
                    images=images,
                    schema=schema,
                )
                self.calls.append({**(trace_context or {}), **candidate.trace(operation)})
                return result, candidate
            except Exception as exc:  # noqa: BLE001
                self.errors.append({
                    **(trace_context or {}),
                    "operation": operation,
                    "role": candidate.role,
                    "provider": candidate.provider,
                    "error": str(exc),
                    "type": type(exc).__name__,
                })
        raise ProviderError(
            f"No vision provider available for stage '{self.stage}'. "
            f"Tried: {[c.provider for c in self.candidates]}"
        )

    def call_vision(
        self,
        *,
        messages: list[dict],
        images: list[bytes],
        operation: str = "vision",
        trace_context: dict[str, str] | None = None,
    ) -> tuple[str, ProviderCandidate]:
        """Call vision on the first provider that succeeds."""
        for candidate in self.candidates:
            try:
                provider = get_provider(candidate.provider, **(candidate.settings or {}))
                result = provider.vision(messages=messages, images=images)
                self.calls.append({**(trace_context or {}), **candidate.trace(operation)})
                return result, candidate
            except Exception as exc:  # noqa: BLE001
                self.errors.append({
                    **(trace_context or {}),
                    "operation": operation,
                    "role": candidate.role,
                    "provider": candidate.provider,
                    "error": str(exc),
                    "type": type(exc).__name__,
                })
        raise ProviderError(
            f"No vision provider available for stage '{self.stage}'. "
            f"Tried: {[c.provider for c in self.candidates]}"
        )


class ProviderCascadeAdapter:
    """Provider-like facade that falls back across already-instantiated candidates."""

    def __init__(
        self,
        cascade: ProviderCascade,
        providers: list[tuple[ProviderCandidate, object]],
    ) -> None:
        self.cascade = cascade
        self.providers = providers

    @property
    def errors(self) -> list[dict[str, str]]:
        return self.cascade.errors

    @property
    def calls(self) -> list[dict[str, str]]:
        return self.cascade.calls

    def _call(
        self,
        method_name: str,
        operation: str,
        trace_context: dict[str, str] | None,
        *args,
        **kwargs,
    ):
        for candidate, provider in self.providers:
            try:
                result = getattr(provider, method_name)(*args, **kwargs)
                self.cascade.calls.append({**(trace_context or {}), **candidate.trace(operation)})
                return result
            except Exception as exc:  # noqa: BLE001 - runtime fallback should continue through candidates.
                self.cascade.errors.append({
                    **(trace_context or {}),
                    "operation": operation,
                    "role": candidate.role,
                    "provider": candidate.provider,
                    "error": str(exc),
                    "type": type(exc).__name__,
                })
        raise ProviderError(
            f"No provider method '{method_name}' available for stage '{self.cascade.stage}'. "
            f"Tried: {[candidate.provider for candidate, _provider in self.providers]}"
        )

    def chat(
        self,
        messages: list[dict],
        *,
        operation: str = "chat",
        trace_context: dict[str, str] | None = None,
        **kwargs,
    ):
        return self._call("chat", operation, trace_context, messages, **kwargs)

    def chat_structured(
        self,
        *,
        messages: list[dict],
        schema: dict,
        operation: str = "chat_structured",
        trace_context: dict[str, str] | None = None,
        **kwargs,
    ):
        return self._call(
            "chat_structured",
            operation,
            trace_context,
            messages=messages,
            schema=schema,
            **kwargs,
        )

    def vision(
        self,
        *,
        messages: list[dict],
        images: list[bytes],
        operation: str = "vision",
        trace_context: dict[str, str] | None = None,
    ):
        return self._call(
            "vision",
            operation,
            trace_context,
            messages=messages,
            images=images,
        )

    def vision_structured(
        self,
        *,
        messages: list[dict],
        images: list[bytes],
        schema: dict,
        operation: str = "vision_structured",
        trace_context: dict[str, str] | None = None,
    ):
        return self._call(
            "vision_structured",
            operation,
            trace_context,
            messages=messages,
            images=images,
            schema=schema,
        )

    def vision_extract(
        self,
        *args,
        operation: str = "vision_extract",
        trace_context: dict[str, str] | None = None,
        **kwargs,
    ):
        return self._call("vision_extract", operation, trace_context, *args, **kwargs)

    def translate(
        self,
        *args,
        operation: str = "translate",
        trace_context: dict[str, str] | None = None,
        **kwargs,
    ):
        return self._call("translate", operation, trace_context, *args, **kwargs)

    def direct_translate_page(
        self,
        *args,
        operation: str = "direct_translate_page",
        trace_context: dict[str, str] | None = None,
        **kwargs,
    ):
        return self._call("direct_translate_page", operation, trace_context, *args, **kwargs)


def resolve_provider_candidates(cfg: ProjectConfig, stage: str) -> Iterable[ProviderCandidate]:
    """Yield configured providers for a stage in cascade order."""
    route_config = cfg.provider_routes.get(stage)
    if route_config is None and stage in {"translation", "qa"}:
        route_config = cfg.provider_routes.get("translation") or cfg.provider_routes.get("translate")

    routes: list[tuple[str, ProviderRoute | None]] = []
    if route_config is not None:
        routes.extend([
            ("primary", route_config.primary),
            ("fallback", route_config.fallback),
            ("local", route_config.local),
        ])
    else:
        routes.append(("primary", ProviderRoute(provider="openai")))

    seen: set[tuple[str, str]] = set()
    for role, route in routes:
        if route is None or not route.provider:
            continue
        settings = dict(cfg.provider_settings.get(route.provider, {}))
        if route.model and "model" not in settings:
            settings["model"] = route.model
        identity = (
            route.provider,
            json.dumps(settings, sort_keys=True, default=str),
        )
        if identity in seen:
            continue
        seen.add(identity)
        yield ProviderCandidate(
            role=role,
            provider=route.provider,
            model=route.model,
            settings=settings,
        )
