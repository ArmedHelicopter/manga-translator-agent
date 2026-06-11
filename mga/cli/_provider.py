"""Provider resolution utilities for CLI."""

from __future__ import annotations

from typing import Any

import click

from mga.providers import ProviderCascade, ProviderCascadeAdapter, get_provider


def resolve_stage_provider(cfg: Any, stage: str = "vision"):
    """Resolve provider(s) for a given stage with fallback cascade."""
    cascade = ProviderCascade(cfg, stage)
    if not cascade.candidates:
        raise click.ClickException(f"No provider configured for stage '{stage}'.")

    errors: list[dict[str, str]] = []
    providers = []
    for candidate in cascade.candidates:
        try:
            providers.append((
                candidate,
                get_provider(candidate.provider, **(candidate.settings or {}))
            ))
        except Exception as exc:  # noqa: BLE001
            errors.append({
                "role": candidate.role,
                "provider": candidate.provider,
                "error": str(exc),
                "type": type(exc).__name__,
            })

    if len(providers) == 1:
        return providers[0][1]
    if providers:
        return ProviderCascadeAdapter(cascade, providers)
    raise click.ClickException(f"Provider unavailable for stage '{stage}': {errors}")


def resolve_translation_provider(cfg: Any) -> tuple[str, dict]:
    """Resolve provider name/settings for translation stage."""
    route = cfg.provider_routes.get("translation") or cfg.provider_routes.get("translate")
    if route and route.primary.provider:
        name = route.primary.provider
        settings = dict(cfg.provider_settings.get(name, {}))
        if route.primary.model and "model" not in settings:
            settings["model"] = route.primary.model
        return name, settings
    return "openai", dict(cfg.provider_settings.get("openai", {}))


def resolve_provider_name(cfg: Any, stage: str = "vision") -> str:
    """Get provider name for a stage."""
    route = cfg.provider_routes.get(stage)
    return route.primary.provider if route and route.primary.provider else "openai"


def resolve_learning_provider(cfg: Any):
    """Resolve provider for learning stage."""
    stage = "vision" if cfg.pipeline_mode == "manga" else "translation"
    cascade = ProviderCascade(cfg, stage)
    if not cascade.candidates:
        return None

    errors: list[dict[str, str]] = []
    providers = []
    for candidate in cascade.candidates:
        try:
            providers.append((
                candidate,
                get_provider(candidate.provider, **(candidate.settings or {}))
            ))
        except Exception as exc:  # noqa: BLE001
            errors.append({
                "role": candidate.role,
                "provider": candidate.provider,
                "error": str(exc),
                "type": type(exc).__name__,
            })

    if not providers:
        raise click.ClickException(f"Learning provider unavailable: {errors}")
    if len(providers) == 1:
        return providers[0][1]
    return ProviderCascadeAdapter(cascade, providers)


def check_provider_connectivity(cfg: Any) -> None:
    """Run lightweight connectivity check before pipeline."""
    import logging
    logger = logging.getLogger(__name__)

    cascade = ProviderCascade(cfg, "translation")
    try:
        cascade.call_chat(
            [{"role": "user", "content": "Reply with OK."}],
            temperature=0.0,
            max_tokens=8,
        )
    except Exception as exc:
        raise click.ClickException(
            f"Provider pre-check failed: {exc}; cascade_errors={cascade.errors}"
        ) from exc
    logger.info("Provider pre-check succeeded with %s", cascade.candidates[0].provider if cascade.candidates else "unknown")


def check_vision_capability(cfg: Any, auto_vision_model: bool = False) -> None:
    """Probe vision-stage cascade with 1px image; fail fast or auto-switch."""
    import logging
    logger = logging.getLogger(__name__)

    try:
        from mga.providers import factory as _factory_mod
        from mga.providers import vision_probe as _vp_mod
    except ImportError:
        logger.debug("Vision probe not available, skipping pre-check")
        return

    cascade = ProviderCascade(cfg, "vision")
    if not cascade.candidates:
        return

    for candidate in cascade.candidates:
        try:
            provider = _factory_mod.create_provider(
                candidate.provider,
                candidate.settings or {},
            )
        except Exception as exc:
            # Skip providers that fail to instantiate (e.g., missing API key).
            # These are not image-rejection errors; they're config errors.
            logger.debug("Skipping provider %s (instantiation failed): %s", candidate.provider, exc)
            continue

        try:
            supports_vision, error_msg = _vp_mod.probe_vision(provider)
            if not supports_vision:
                if _vp_mod.is_image_rejection_error(error_msg):
                    msg = f"Provider {candidate.provider} does not support vision"
                    suggestions = _vp_mod.discover_vision_models(
                        candidate.provider,
                        candidate.settings or {},
                        current_model=candidate.model,
                    )
                    if suggestions:
                        if auto_vision_model:
                            chosen = suggestions[0]
                            _apply_vision_model_switch(cfg, candidate.provider, chosen)
                            logger.info("%s — auto-switched to %s", msg, chosen)
                            return
                        raise click.ClickException(
                            f"{msg}: {error_msg}; "
                            f"suggestions: {suggestions}; "
                            f"use --auto-vision-model to switch automatically"
                        )
                    raise click.ClickException(msg)
                # Non-image-rejection failure (auth error, timeout, etc.) -> skip,
                # let cascade handle it.
                logger.debug(
                    "Skipping provider %s (transient failure, not vision-related): %s",
                    candidate.provider, error_msg,
                )
                continue
        except click.ClickException:
            raise
        except Exception as exc:
            # Skip providers with transient failures that are not image-rejection errors.
            if _vp_mod.is_image_rejection_error(exc):
                raise click.ClickException(
                    f"Vision model rejected image input: {exc}"
                ) from exc
            logger.debug(
                "Skipping provider %s (transient error, not vision-related): %s",
                candidate.provider, exc,
            )
            continue


def _apply_vision_model_switch(cfg: Any, provider: str, model: str) -> None:
    """Update cfg to use *model* for *provider* in the vision stage."""
    if provider in cfg.provider_settings:
        cfg.provider_settings[provider]["vision_model"] = model
    route = cfg.provider_routes.get("vision")
    if route and route.primary and route.primary.provider == provider:
        route.primary.model = model