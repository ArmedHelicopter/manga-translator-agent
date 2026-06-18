"""Recovery orchestration for OCR blank-page detection."""

from __future__ import annotations

import logging
import sys
from typing import Any

from mga.exceptions import StageExecutionError

from .models import BlankPageSequence, OCRGuardConfig, RecoveryDecision, RecoveryStrategy

logger = logging.getLogger(__name__)


_DEFAULT_OCR_MODELS = [
    {"name": "48px", "description": "MIT 48px OCR (runtime model)"},
    {"name": "32px", "description": "MIT 32px OCR (runtime model)"},
    {"name": "48px_ctc", "description": "MIT 48px CTC OCR (runtime model)"},
    {"name": "mocr", "description": "Manga OCR model"},
    {"name": "tesseract", "description": "Tesseract OCR engine"},
]


class RecoveryOrchestrator:
    """Handle user interaction and recovery strategy application."""

    def __init__(self, config: OCRGuardConfig) -> None:
        self.config = config

    def prompt_user(self, sequence: BlankPageSequence, context: Any) -> RecoveryDecision:
        """Present recovery options to the user via CLI or auto strategy."""
        auto_decision = self._auto_decision(sequence)
        if auto_decision is not None:
            logger.info("Applying OCR guard auto recovery strategy: %s", auto_decision.strategy.value)
            return auto_decision

        # Non-interactive: raise if no auto strategy configured
        if not sys.stdin.isatty():
            raise StageExecutionError(
                "OCR blank pages detected in non-interactive mode. "
                "Set auto_recovery_strategy to 'continue' to auto-continue."
            )

        self._print_alert(sequence)
        while True:
            choice = input("Select option [1-5]: ").strip()
            if choice == "1":
                return self._prompt_switch_model(context)
            if choice == "2":
                return self._prompt_adjust_threshold()
            if choice == "3":
                return self._prompt_hybrid_mode(sequence, context)
            if choice == "4":
                return RecoveryDecision(strategy=RecoveryStrategy.CONTINUE)
            if choice == "5":
                return RecoveryDecision(strategy=RecoveryStrategy.ABORT)
            print("Please select a valid option from 1 to 5.")

    def apply_strategy(self, decision: RecoveryDecision, context: Any) -> tuple[Any, bool]:
        """Apply the recovery strategy to the pipeline context.

        For SWITCH_OCR_MODEL, resolves the target engine via the OCR engine
        registry and updates the context metadata with the selected model.

        Returns:
            (context, needs_restart) — context may be modified in-place;
            needs_restart is True only for SWITCH_OCR_MODEL (pipeline must
            restart from the vision stage).
        """
        state = context.ocr_guard_state

        if decision.strategy == RecoveryStrategy.SWITCH_OCR_MODEL:
            state["recovery_applied"] = decision.model_dump(mode="json")
            if decision.new_ocr_model:
                context.metadata["requested_ocr_model"] = decision.new_ocr_model
                # Resolve the engine from the registry to validate it exists
                registry = self._get_engine_registry(context)
                if registry is not None:
                    engine = registry.get(decision.new_ocr_model)
                    if engine is not None and engine.is_available():
                        context.metadata["ocr_engine"] = decision.new_ocr_model
                        logger.info("Switched OCR engine to: %s", decision.new_ocr_model)
                    elif engine is not None:
                        logger.warning(
                            "OCR engine '%s' registered but not available, "
                            "will attempt at runtime",
                            decision.new_ocr_model,
                        )
                    else:
                        logger.warning(
                            "OCR engine '%s' not in registry, "
                            "deferring to runtime model resolution",
                            decision.new_ocr_model,
                        )
            return context, True

        if decision.strategy == RecoveryStrategy.ADJUST_THRESHOLD:
            if decision.new_threshold is None:
                raise StageExecutionError("Threshold recovery selected without a new threshold.")
            state["threshold"] = decision.new_threshold
            state["recovery_applied"] = decision.model_dump(mode="json")
            return context, False

        if decision.strategy == RecoveryStrategy.HYBRID_MODE:
            sequence = self._sequence_from_state(state)
            if sequence is None:
                raise StageExecutionError("Hybrid recovery selected without a detected blank sequence.")
            hybrid_pages = sorted(set(state.get("hybrid_mode_pages", [])) | set(sequence.page_ids))
            state["hybrid_mode_pages"] = hybrid_pages
            state["recovery_applied"] = decision.model_dump(mode="json")
            if decision.hybrid_mode_config:
                state["hybrid_mode_config"] = decision.hybrid_mode_config
            return context, False

        if decision.strategy == RecoveryStrategy.CONTINUE:
            state["recovery_applied"] = decision.model_dump(mode="json")
            return context, False

        if decision.strategy == RecoveryStrategy.ABORT:
            state["recovery_applied"] = decision.model_dump(mode="json")
            raise StageExecutionError("User aborted pipeline due to OCR blank pages.")

        raise StageExecutionError(f"Unsupported OCR recovery strategy: {decision.strategy}")

    def _auto_decision(self, sequence: BlankPageSequence) -> RecoveryDecision | None:
        raw_strategy = (self.config.auto_recovery_strategy or "").strip().lower()
        if not raw_strategy or raw_strategy in {"none", "null", "prompt"}:
            return None
        try:
            strategy = RecoveryStrategy(raw_strategy)
        except ValueError as exc:
            raise StageExecutionError(
                f"Unsupported OCR guard auto_recovery_strategy: {self.config.auto_recovery_strategy}"
            ) from exc

        if strategy == RecoveryStrategy.ADJUST_THRESHOLD:
            return RecoveryDecision(
                strategy=strategy,
                new_threshold=max(self.config.consecutive_blank_threshold, sequence.blank_count + 1),
            )
        if strategy == RecoveryStrategy.HYBRID_MODE:
            return RecoveryDecision(strategy=strategy, hybrid_mode_config=self._hybrid_config_payload())
        return RecoveryDecision(strategy=strategy)

    def _print_alert(self, sequence: BlankPageSequence) -> None:
        print("=" * 65)
        print("OCR BLANK PAGE DETECTION ALERT")
        print("=" * 65)
        print()
        print(
            f"Detected {sequence.blank_count} consecutive blank pages "
            f"(indices {sequence.start_index}-{sequence.end_index}):"
        )
        for page_id in sequence.page_ids:
            print(f"  - {page_id}")
        print()
        print(f"Current threshold: {self.config.consecutive_blank_threshold} consecutive blank pages")
        print(f"Detection criteria: OCR text < {self.config.min_text_length} characters per bubble")
        print()
        print("RECOVERY OPTIONS")
        print("-" * 65)
        print("[1] Switch OCR Model")
        print("    Restart the pipeline with a different OCR engine.")
        print("[2] Adjust Threshold")
        print("    Change the consecutive blank page threshold and continue.")
        print("[3] Enable Hybrid Mode")
        print("    Use OCR for text-rich pages and vision extraction for blanks.")
        print("[4] Continue Anyway")
        print("    Ignore blank pages and proceed with translation.")
        print("[5] Abort Pipeline")
        print("    Stop processing and exit.")
        print()

    def _prompt_switch_model(self, context: Any) -> RecoveryDecision:
        models = self._available_ocr_models(context)
        current_model = str(context.metadata.get("ocr_model") or context.metadata.get("requested_ocr_model") or "48px")
        print()
        print("Available OCR Models:")
        for index, model in enumerate(models, start=1):
            current = " (current)" if model["name"] == current_model else ""
            print(f"  [{index}] {model['name']}{current} - {model['description']}")
        print()

        while True:
            raw_choice = input(f"Select OCR model [1-{len(models)}]: ").strip()
            try:
                selected = models[int(raw_choice) - 1]
            except (ValueError, IndexError):
                print("Please select a valid OCR model number.")
                continue

            proceed = input("This will restart the pipeline from the beginning. Proceed? [y/N]: ").strip()
            if proceed.lower() not in {"y", "yes"}:
                print("OCR model switch cancelled.")
                return RecoveryDecision(strategy=RecoveryStrategy.CONTINUE)
            return RecoveryDecision(
                strategy=RecoveryStrategy.SWITCH_OCR_MODEL,
                new_ocr_model=selected["name"],
            )

    def _prompt_adjust_threshold(self) -> RecoveryDecision:
        print()
        print(f"Current threshold: {self.config.consecutive_blank_threshold} consecutive blank pages")
        while True:
            raw_threshold = input("Enter new threshold (1-50): ").strip()
            try:
                threshold = int(raw_threshold)
            except ValueError:
                print("Please enter a whole number.")
                continue
            if 1 <= threshold <= 50:
                print(f"Threshold updated to: {threshold}")
                return RecoveryDecision(
                    strategy=RecoveryStrategy.ADJUST_THRESHOLD,
                    new_threshold=threshold,
                )
            print("Please enter a value from 1 to 50.")

    def _prompt_hybrid_mode(self, sequence: BlankPageSequence, context: Any) -> RecoveryDecision:
        model = self._hybrid_vision_model(context)
        print()
        print("Hybrid Mode Configuration:")
        print("  - OCR-detected text: keep original OCR results")
        print(
            f"  - Blank pages ({sequence.start_index}-{sequence.end_index}): "
            "use vision-based extraction"
        )
        print(f"  - Vision model: {model or 'stage default'}")
        proceed = input("Proceed with hybrid mode? [Y/n]: ").strip()
        if proceed.lower() in {"n", "no"}:
            return RecoveryDecision(strategy=RecoveryStrategy.CONTINUE)
        return RecoveryDecision(
            strategy=RecoveryStrategy.HYBRID_MODE,
            hybrid_mode_config=self._hybrid_config_payload(model=model),
        )

    def _available_ocr_models(self, context: Any) -> list[dict[str, str]]:
        configured = context.metadata.get("available_ocr_models")
        if isinstance(configured, list) and configured:
            models: list[dict[str, str]] = []
            for item in configured:
                if isinstance(item, dict) and item.get("name"):
                    models.append({
                        "name": str(item["name"]),
                        "description": str(item.get("description", "Configured OCR model")),
                    })
                elif isinstance(item, str):
                    models.append({"name": item, "description": "Configured OCR model"})
            if models:
                return models
        return list(_DEFAULT_OCR_MODELS)

    def _hybrid_vision_model(self, context: Any) -> str:
        if self.config.hybrid_vision_model_override:
            return self.config.hybrid_vision_model_override
        route = getattr(context.project_config, "provider_routes", {}).get("vision")
        if route and route.primary and route.primary.model:
            return route.primary.model
        return ""

    def _hybrid_config_payload(self, model: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"enabled": True}
        selected_model = model if model is not None else self.config.hybrid_vision_model_override
        if selected_model:
            payload["vision_model_override"] = selected_model
        return payload


    def _sequence_from_state(self, state: dict[str, Any]) -> BlankPageSequence | None:
        raw_sequence = state.get("blank_sequence")
        if raw_sequence is None:
            return None
        if isinstance(raw_sequence, BlankPageSequence):
            return raw_sequence
        if isinstance(raw_sequence, dict):
            return BlankPageSequence.model_validate(raw_sequence)
        return None

    def _get_engine_registry(self, context: Any) -> Any:
        """Get OCR engine registry from context metadata, or create and cache a default one.

        Returns an OCREngineRegistry instance (never None).
        """
        from .engines.base import OCREngineRegistry

        registry = context.metadata.get("ocr_engine_registry")
        if registry is not None and isinstance(registry, OCREngineRegistry):
            return registry

        # Create default registry and cache it for future use
        registry = OCREngineRegistry.default()
        context.metadata["ocr_engine_registry"] = registry
        return registry
