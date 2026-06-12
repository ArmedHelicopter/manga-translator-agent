"""FastAPI Web UI for Manga Translate Agent - Blue & White Theme.

This module provides a complete web interface with:
- Blue & white color scheme
- Tutorial wizard for first-time setup
- Bilingual support (English/Chinese)
- Translation workflow
- Memory management (characters, terms)
- Profile management
- Provider configuration
- Settings

All templates use Jinja2 and are located in mga/web/templates/.
"""

from __future__ import annotations

import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomli_w
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from starlette.templating import Jinja2Templates

from mga.cultural.terminology_db import TerminologyDB, TermState as TerminologyAssetState
from mga.memory.entities import CharacterState, DecisionState, TermState
from mga.memory.profile_builder import save_profile
from mga.memory.profile_loader import load_all_profiles, load_character_profile
from mga.memory.state import StateManager
from mga.providers.registry import _PROVIDER_MAP

from .i18n import LANGUAGE_PAIRS, Locale, PROVIDER_OPTIONS, SUPPORTED_FORMATS, _TRANSLATIONS

# Optional: Session middleware (requires itsdangerous)
try:
    from starlette.middleware.sessions import SessionMiddleware
    SESSION_MIDDLEWARE_AVAILABLE = True
except ImportError:
    SESSION_MIDDLEWARE_AVAILABLE = False


# ============================================================================
# Pydantic Models
# ============================================================================

class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    source_lang: str = "ja"
    target_lang: str = "zh-CN"


class ProjectSummary(BaseModel):
    id: str
    name: str
    path: str
    source_lang: str = "ja"
    target_lang: str = "zh-CN"
    created_at: str = ""
    updated_at: str = ""
    character_count: int = 0
    term_count: int = 0
    scene_count: int = 0


class CharacterProfilePayload(BaseModel):
    character_id: str = ""
    name_jp: str = ""
    name_zh: str = ""
    archetype: str = ""
    speech_patterns: dict[str, str] = Field(default_factory=dict)
    catchphrases: list[str] = Field(default_factory=list)
    tone_spectrum: dict[str, str] = Field(default_factory=dict)
    translation_notes: dict[str, str] = Field(default_factory=dict)


class TermPayload(BaseModel):
    term_id: str = ""
    term_jp: str = ""
    term_zh: str = ""
    candidate_translations: list[str] = Field(default_factory=list)
    context: str = ""
    cultural_weight: str = ""
    strategy: str = ""
    accepted_reason: str = ""
    rejected_reasons: dict[str, str] = Field(default_factory=dict)
    applicability_scope: str = ""
    pending_human_review: bool = False
    frequency: int = 0


class ProviderConfigPayload(BaseModel):
    stages: dict[str, dict[str, str]] = Field(default_factory=dict)
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ReviewDecisionRequest(BaseModel):
    report_path: str
    item_id: str
    status: str
    rationale: str = ""
    page_id: str = ""
    bubble_id: str = ""
    kind: str = ""
    target: str = ""
    action: str = ""
    message: str = ""
    confidence: float = 0.0


class SettingsPayload(BaseModel):
    locale: str = "en"
    default_source_lang: str = "ja"
    default_target_lang: str = "zh-CN"
    provider_overrides: dict[str, dict[str, Any]] = Field(default_factory=dict)


# ============================================================================
# FastAPI Application Factory
# ============================================================================

def create_app(
    project_root: str | Path | None = None,
    template_dir: str | Path | None = None,
    static_dir: str | Path | None = None,
) -> FastAPI:
    """Create the complete web UI app with blue-white theme.

    Args:
        project_root: Root directory for projects (default: current directory)
        template_dir: Directory for Jinja2 templates
        static_dir: Directory for static files (CSS, JS, images)

    Returns:
        Configured FastAPI application
    """
    root = Path(project_root or ".").resolve()
    root.mkdir(parents=True, exist_ok=True)

    # Determine template directory
    if template_dir:
        templates = Jinja2Templates(directory=template_dir)
    else:
        template_path = Path(__file__).parent / "templates"
        templates = Jinja2Templates(directory=template_path)

    # Create FastAPI app
    app = FastAPI(
        title="Manga Translate Agent Web UI",
        description="AI-powered manga translation with blue-white theme",
        version="1.0.0",
    )

    # Add session middleware for locale preferences (optional)
    if SESSION_MIDDLEWARE_AVAILABLE:
        app.add_middleware(SessionMiddleware, secret_key="mga-web-secret-key-change-in-production")

    # Store paths in app state
    app.state.project_root = root

    # =========================================================================
    # Template Helper Functions
    # =========================================================================

    def _t(key: str, locale: str = "en") -> str:
        """Get translation for a key."""
        locale_enum = Locale(locale) if locale in ["en", "zh"] else Locale.EN
        return _TRANSLATIONS.get(locale_enum, _TRANSLATIONS[Locale.EN]).get(key, key)

    def _get_translations(locale: str) -> dict[str, str]:
        """Get all translations for a locale."""
        locale_enum = Locale(locale) if locale in ["en", "zh"] else Locale.EN
        return _TRANSLATIONS.get(locale_enum, _TRANSLATIONS[Locale.EN])

    # =========================================================================
    # Routes
    # =========================================================================

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> str:
        """Render the main web UI page."""
        # Get locale from cookie, query param, or default to English
        locale = "en"
        try:
            if SESSION_MIDDLEWARE_AVAILABLE and "session" in request.scope:
                locale = request.session.get("locale", "en")
        except Exception:
            pass
        translations_en = _TRANSLATIONS[Locale.EN]
        translations_zh = _TRANSLATIONS[Locale.ZH]

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "locale": locale,
                "t": lambda key: _t(key, locale),
                "translations_en": translations_en,
                "translations_zh": translations_zh,
                "provider_options": PROVIDER_OPTIONS,
                "language_pairs": LANGUAGE_PAIRS,
                "supported_formats": SUPPORTED_FORMATS,
            },
        )

    @app.get("/api/locale/{new_locale}")
    def set_locale(new_locale: str) -> dict:
        """Change the UI locale."""
        if new_locale not in ["en", "zh"]:
            raise HTTPException(status_code=400, detail="Invalid locale")
        return {"locale": new_locale, "message": f"Locale set to {new_locale}"}

    # -------------------------------------------------------------------------
    # Project Management
    # -------------------------------------------------------------------------

    @app.get("/api/projects")
    def list_projects() -> dict[str, list[dict]]:
        """List all projects."""
        return {
            "projects": [
                summary.model_dump()
                for summary in _list_project_summaries(root)
            ]
        }

    @app.post("/api/projects", status_code=201)
    def create_project(payload: ProjectCreateRequest) -> dict:
        """Create a new project."""
        project_id = _slugify(payload.name)
        project_dir = root / project_id
        if project_dir.exists():
            raise HTTPException(status_code=409, detail="Project already exists")

        now = datetime.now(timezone.utc).isoformat()
        project_dir.mkdir(parents=True)
        meta = {
            "project": {
                "id": project_id,
                "name": payload.name.strip(),
                "source_lang": payload.source_lang,
                "target_lang": payload.target_lang,
                "created_at": now,
                "updated_at": now,
            }
        }
        (project_dir / "project_meta.toml").write_text(
            tomli_w.dumps(meta),
            encoding="utf-8",
        )
        StateManager.save(project_dir, StateManager.load(project_dir))
        return _project_summary(project_dir).model_dump()

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str) -> dict:
        """Get project details."""
        project_dir = _resolve_project_dir(root, project_id)
        return _project_summary(project_dir).model_dump()

    @app.delete("/api/projects/{project_id}")
    def delete_project(project_id: str) -> dict:
        """Delete a project."""
        import shutil
        project_dir = _resolve_project_dir(root, project_id)
        shutil.rmtree(project_dir)
        return {"status": "deleted", "project_id": project_id}

    # -------------------------------------------------------------------------
    # Character Management
    # -------------------------------------------------------------------------

    @app.get("/api/projects/{project_id}/characters")
    def list_characters(project_id: str) -> dict[str, list[dict]]:
        """List all characters in a project."""
        project_dir = _resolve_project_dir(root, project_id)
        profiles = load_all_profiles(project_dir)
        return {
            "characters": [
                _character_summary(profile)
                for profile in sorted(profiles.values(), key=lambda item: item.character_id)
            ]
        }

    @app.get("/api/projects/{project_id}/characters/{character_id}")
    def get_character(project_id: str, character_id: str) -> dict:
        """Get a specific character profile."""
        project_dir = _resolve_project_dir(root, project_id)
        profile = load_character_profile(project_dir, character_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Character not found")
        return profile.model_dump()

    @app.put("/api/projects/{project_id}/characters/{character_id}")
    def put_character(
        project_id: str,
        character_id: str,
        payload: CharacterProfilePayload,
    ) -> dict:
        """Create or update a character profile."""
        project_dir = _resolve_project_dir(root, project_id)
        profile = CharacterState(
            character_id=character_id,
            name_jp=payload.name_jp,
            name_zh=payload.name_zh,
            archetype=payload.archetype,
            speech_patterns=payload.speech_patterns,
            catchphrases=payload.catchphrases,
            tone_spectrum=payload.tone_spectrum,
            translation_notes=payload.translation_notes,
        )
        save_profile(project_dir, profile)
        return profile.model_dump()

    @app.delete("/api/projects/{project_id}/characters/{character_id}")
    def delete_character(project_id: str, character_id: str) -> dict:
        """Delete a character profile."""
        project_dir = _resolve_project_dir(root, project_id)
        profile_path = project_dir / "character_profiles" / f"{character_id}.toml"
        if profile_path.exists():
            profile_path.unlink()
        return {"status": "deleted", "character_id": character_id}

    # -------------------------------------------------------------------------
    # Terminology Management
    # -------------------------------------------------------------------------

    @app.get("/api/projects/{project_id}/terms")
    def list_terms(project_id: str) -> dict[str, list[dict]]:
        """List all terms in a project."""
        project_dir = _resolve_project_dir(root, project_id)
        return {
            "terms": [
                _term_summary(term)
                for term in sorted(
                    _merged_terms(project_dir),
                    key=lambda item: item.term_id or item.term_jp,
                )
            ]
        }

    @app.get("/api/projects/{project_id}/terms/{term_id:path}")
    def get_term(project_id: str, term_id: str) -> dict:
        """Get a specific term."""
        project_dir = _resolve_project_dir(root, project_id)
        term = StateManager.get_term(project_dir, term_id)
        if term is None:
            term = _term_from_assets(project_dir, term_id)
        if term is None:
            raise HTTPException(status_code=404, detail="Term not found")
        return term.model_dump()

    @app.post("/api/projects/{project_id}/terms/{term_id:path}")
    def save_term(project_id: str, term_id: str, payload: TermPayload) -> dict:
        """Create or update a term."""
        project_dir = _resolve_project_dir(root, project_id)
        term = TermState(
            term_id=term_id,
            term_jp=payload.term_jp,
            term_zh=payload.term_zh,
            candidate_translations=payload.candidate_translations,
            context=payload.context,
            cultural_weight=payload.cultural_weight,
            strategy=payload.strategy,
            accepted_reason=payload.accepted_reason,
            rejected_reasons=payload.rejected_reasons,
            applicability_scope=payload.applicability_scope,
            pending_human_review=payload.pending_human_review,
            frequency=payload.frequency,
        )
        StateManager.upsert_term(project_dir, term)
        _export_terms(project_dir)
        return term.model_dump()

    @app.delete("/api/projects/{project_id}/terms/{term_id:path}")
    def delete_term(project_id: str, term_id: str) -> dict:
        """Delete a term."""
        project_dir = _resolve_project_dir(root, project_id)
        StateManager.delete_term(project_dir, term_id)
        _export_terms(project_dir)
        return {"status": "deleted", "term_id": term_id}

    # -------------------------------------------------------------------------
    # Provider Configuration
    # -------------------------------------------------------------------------

    @app.get("/api/projects/{project_id}/provider-config")
    def get_provider_config(project_id: str) -> dict:
        """Get provider configuration for a project."""
        project_dir = _resolve_project_dir(root, project_id)
        return _provider_config_response(project_dir)

    @app.post("/api/projects/{project_id}/provider-config")
    def save_provider_config(project_id: str, payload: ProviderConfigPayload) -> dict:
        """Save provider configuration for a project."""
        project_dir = _resolve_project_dir(root, project_id)
        config = _sanitize_provider_config(payload.model_dump())
        path = _provider_config_path(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomli_w.dumps(config), encoding="utf-8")
        return _provider_config_response(project_dir)

    # -------------------------------------------------------------------------
    # Settings
    # -------------------------------------------------------------------------

    @app.get("/api/settings")
    def get_settings() -> dict:
        """Get application settings."""
        settings_path = root / ".mga_settings.json"
        if settings_path.exists():
            return json.loads(settings_path.read_text(encoding="utf-8"))
        return {
            "locale": "en",
            "default_source_lang": "ja",
            "default_target_lang": "zh-CN",
            "provider_overrides": {},
        }

    @app.post("/api/settings")
    def save_settings(payload: SettingsPayload) -> dict:
        """Save application settings."""
        settings_path = root / ".mga_settings.json"
        settings_path.write_text(
            json.dumps(payload.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return payload.model_dump()

    # -------------------------------------------------------------------------
    # Translation Reports (from existing app.py)
    # -------------------------------------------------------------------------

    @app.get("/api/projects/{project_id}/translation-reports")
    def list_translation_reports(project_id: str) -> dict[str, list[dict]]:
        """List translation reports for a project."""
        project_dir = _resolve_project_dir(root, project_id)
        return {
            "reports": [
                _translation_report_summary(project_dir, path)
                for path in _iter_translation_reports(project_dir)
            ]
        }

    @app.get("/api/projects/{project_id}/translation-report")
    def get_translation_report(project_id: str, path: str = Query(...)) -> dict:
        """Get a specific translation report."""
        project_dir = _resolve_project_dir(root, project_id)
        report_path = _resolve_report_path(project_dir, path)
        return _read_translation_report(report_path)

    @app.get("/api/projects/{project_id}/review-items")
    def list_review_items(project_id: str, path: str = Query(...)) -> dict:
        """List QA review items from a translation report."""
        project_dir = _resolve_project_dir(root, project_id)
        report_path = _resolve_report_path(project_dir, path)
        return {"items": _review_items_from_report(_read_translation_report(report_path))}

    @app.post("/api/projects/{project_id}/review-decisions", status_code=201)
    def create_review_decision(project_id: str, payload: ReviewDecisionRequest) -> dict:
        """Record a review decision."""
        project_dir = _resolve_project_dir(root, project_id)
        if payload.status not in {"accept", "reject"}:
            raise HTTPException(status_code=422, detail="status must be accept or reject")
        _resolve_report_path(project_dir, payload.report_path)
        action = payload.action or "review_qa_finding"
        bubble_id = payload.bubble_id or "unknown"
        page_id = payload.page_id or "unknown"
        decision = DecisionState(
            decision_id=_review_decision_id(payload),
            stage="review",
            input_ref=f"{page_id}/{bubble_id}",
            decision=f"{payload.status} {action} for {bubble_id}",
            rationale=payload.rationale or payload.message,
            confidence=payload.confidence,
            metadata={
                "report_path": payload.report_path,
                "item_id": payload.item_id,
                "kind": payload.kind,
                "page_id": page_id,
                "bubble_id": bubble_id,
                "target": payload.target,
                "action": action,
                "message": payload.message,
                "status": payload.status,
            },
        )
        StateManager.upsert_decision(project_dir, decision)
        return decision.model_dump()

    # =========================================================================
    # Helper Functions
    # =========================================================================

    def _list_project_summaries(root: Path) -> list[ProjectSummary]:
        return [
            _project_summary(path)
            for path in sorted(root.iterdir())
            if path.is_dir() and (path / "project_meta.toml").exists()
        ]

    def _project_summary(project_dir: Path) -> ProjectSummary:
        meta = _read_project_meta(project_dir)
        project = meta.get("project", {})
        index = StateManager.load(project_dir)
        project_id = str(project.get("id") or project_dir.name)
        return ProjectSummary(
            id=project_id,
            name=str(project.get("name") or project_id),
            path=str(project_dir),
            source_lang=str(project.get("source_lang") or "ja"),
            target_lang=str(project.get("target_lang") or "zh-CN"),
            created_at=str(project.get("created_at") or ""),
            updated_at=str(project.get("updated_at") or ""),
            character_count=len(index.characters),
            term_count=len(index.terms),
            scene_count=len(index.scenes),
        )

    def _read_project_meta(project_dir: Path) -> dict:
        path = project_dir / "project_meta.toml"
        if not path.exists():
            return {}
        return tomllib.loads(path.read_text(encoding="utf-8"))

    def _resolve_project_dir(root: Path, project_id: str) -> Path:
        import re
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", project_id):
            raise HTTPException(status_code=404, detail="Project not found")
        project_dir = root / project_id
        if not project_dir.exists() or not (project_dir / "project_meta.toml").exists():
            raise HTTPException(status_code=404, detail="Project not found")
        return project_dir

    def _character_summary(profile: CharacterState) -> dict:
        return {
            "character_id": profile.character_id,
            "name_jp": profile.name_jp,
            "name_zh": profile.name_zh,
            "archetype": profile.archetype,
            "speech_pattern_count": len(profile.speech_patterns),
            "catchphrase_count": len(profile.catchphrases),
            "tone_count": len(profile.tone_spectrum),
            "translation_note_count": len(profile.translation_notes),
        }

    def _merged_terms(project_dir: Path) -> list[TermState]:
        terms = {term.term_id: term for term in StateManager.list_terms(project_dir)}
        for term in _terms_from_assets(project_dir):
            if term.term_id not in terms:
                terms[term.term_id] = term
        return list(terms.values())

    def _term_from_assets(project_dir: Path, term_id: str) -> TermState | None:
        for term in _terms_from_assets(project_dir):
            if term.term_id == term_id:
                return term
        return None

    def _terms_from_assets(project_dir: Path) -> list[TermState]:
        return [
            _asset_to_term_state(item)
            for item in TerminologyDB.load(project_dir).items()
        ]

    def _asset_to_term_state(item: TerminologyAssetState) -> TermState:
        import re
        term_id = re.sub(r"\s+", "_", item.term_jp.strip().lower()) or "term"
        return TermState(
            term_id=term_id,
            term_jp=item.term_jp,
            term_zh=item.term_target,
            candidate_translations=item.candidate_translations,
            context=item.notes,
            cultural_weight=item.problem_types[0] if item.problem_types else "",
            strategy=item.strategy,
            accepted_reason=item.accepted_reason,
            rejected_reasons=item.rejected_reasons,
            applicability_scope=item.applicability_scope,
            pending_human_review=item.pending_human_review,
        )

    def _term_summary(term: TermState) -> dict:
        return {
            "term_id": term.term_id,
            "term_jp": term.term_jp,
            "term_zh": term.term_zh,
            "cultural_weight": term.cultural_weight,
            "strategy": term.strategy,
            "pending_human_review": term.pending_human_review,
            "frequency": term.frequency,
            "candidate_count": len(term.candidate_translations),
        }

    def _export_terms(project_dir: Path) -> Path:
        db = TerminologyDB()
        for term in StateManager.list_terms(project_dir):
            db.register(
                TerminologyAssetState(
                    term_jp=term.term_jp or term.term_id,
                    term_target=term.term_zh,
                    candidate_translations=term.candidate_translations,
                    problem_types=[term.cultural_weight] if term.cultural_weight else [],
                    strategy=term.strategy,
                    notes=term.context,
                    accepted_reason=term.accepted_reason,
                    rejected_reasons=term.rejected_reasons,
                    applicability_scope=term.applicability_scope,
                    confirmed=not term.pending_human_review,
                    pending_human_review=term.pending_human_review,
                )
            )
        return db.export(project_dir)

    def _provider_config_response(project_dir: Path) -> dict:
        config = _read_provider_config(project_dir)
        return {
            "path": _provider_config_path(project_dir).relative_to(project_dir).as_posix(),
            "provider_options": sorted(_PROVIDER_MAP),
            "stages": config.get("stages", {}),
            "providers": _redact_provider_settings(config.get("providers", {})),
        }

    def _provider_config_path(project_dir: Path) -> Path:
        return project_dir / "configs" / "providers.toml"

    def _read_provider_config(project_dir: Path) -> dict:
        path = _provider_config_path(project_dir)
        if not path.exists():
            return {
                "stages": {
                    "vision": {"primary": "", "fallback": "", "local": ""},
                    "translation": {"primary": "", "fallback": "", "local": ""},
                    "qa": {"primary": "", "fallback": "", "local": ""},
                },
                "providers": {},
            }
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        return {
            "stages": payload.get("stages", {}) if isinstance(payload.get("stages", {}), dict) else {},
            "providers": payload.get("providers", {}) if isinstance(payload.get("providers", {}), dict) else {},
        }

    def _redact_provider_settings(providers: dict[str, Any]) -> dict[str, dict[str, Any]]:
        redacted: dict[str, dict[str, Any]] = {}
        for name, settings in providers.items():
            if not isinstance(settings, dict):
                continue
            redacted[str(name)] = {
                str(key): _redact_provider_value(str(key), value)
                for key, value in settings.items()
            }
        return redacted

    def _redact_provider_value(key: str, value: Any) -> Any:
        if _credential_like(key) and not _env_placeholder(value):
            return "***"
        return value

    def _sanitize_provider_config(config: dict[str, Any]) -> dict:
        return {
            "stages": _sanitize_provider_stages(config.get("stages", {})),
            "providers": _sanitize_provider_settings(config.get("providers", {})),
        }

    def _sanitize_provider_stages(stages: Any) -> dict[str, dict[str, str]]:
        if not isinstance(stages, dict):
            raise HTTPException(status_code=422, detail="stages must be an object")
        output: dict[str, dict[str, str]] = {}
        for stage in ("vision", "translation", "qa"):
            raw_stage = stages.get(stage, {})
            if not isinstance(raw_stage, dict):
                raise HTTPException(status_code=422, detail=f"stage {stage} must be an object")
            stage_payload = {}
            for role in ("primary", "fallback", "local"):
                provider = str(raw_stage.get(role) or "").strip()
                if provider and provider not in _PROVIDER_MAP:
                    raise HTTPException(status_code=422, detail=f"Unknown provider: {provider}")
                if provider:
                    stage_payload[role] = provider
            output[stage] = stage_payload
        return output

    def _sanitize_provider_settings(providers: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(providers, dict):
            raise HTTPException(status_code=422, detail="providers must be an object")
        output: dict[str, dict[str, Any]] = {}
        for name, raw_settings in providers.items():
            provider = str(name).strip()
            if not provider:
                continue
            if provider not in _PROVIDER_MAP:
                raise HTTPException(status_code=422, detail=f"Unknown provider: {provider}")
            if not isinstance(raw_settings, dict):
                raise HTTPException(status_code=422, detail=f"Provider {provider} settings must be an object")
            settings = {}
            for key, value in raw_settings.items():
                key_text = str(key).strip()
                if not key_text:
                    continue
                if _credential_like(key_text):
                    if value in ("", None, "***"):
                        continue
                    if not _env_placeholder(value):
                        raise HTTPException(
                            status_code=422,
                            detail=f"{provider}.{key_text} must use an environment variable placeholder",
                        )
                settings[key_text] = value
            output[provider] = settings
        return output

    def _credential_like(key: str) -> bool:
        lowered = key.lower()
        return any(token in lowered for token in ("api_key", "apikey", "token", "secret", "password"))

    def _env_placeholder(value: Any) -> bool:
        return isinstance(value, str) and value.startswith("${") and value.endswith("}") and len(value) > 3

    def _iter_translation_reports(project_dir: Path) -> list[Path]:
        return sorted(project_dir.rglob("translation-report.json"))

    def _translation_report_summary(project_dir: Path, path: Path) -> dict:
        payload = _read_translation_report(path)
        entries = payload.get("entries", [])
        summary = payload.get("summary", {})
        return {
            "path": path.relative_to(project_dir).as_posix(),
            "entry_count": len(entries) if isinstance(entries, list) else 0,
            "preview_entries": entries[:3] if isinstance(entries, list) else [],
            "review_items": _review_items_from_report(payload)[:5],
            "entries_needing_human_review": int(summary.get("entries_needing_human_review", 0))
            if isinstance(summary, dict)
            else 0,
            "avg_confidence": float(summary.get("avg_confidence", 0.0))
            if isinstance(summary, dict)
            else 0.0,
            "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        }

    def _resolve_report_path(project_dir: Path, value: str) -> Path:
        requested = Path(value)
        if requested.is_absolute() or ".." in requested.parts:
            raise HTTPException(status_code=404, detail="Translation report not found")
        path = project_dir / requested
        if path.name != "translation-report.json" or not path.exists():
            raise HTTPException(status_code=404, detail="Translation report not found")
        return path

    def _read_translation_report(path: Path) -> dict:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="Translation report must be a JSON object")
        entries = payload.get("entries", [])
        summary = payload.get("summary", {})
        return {
            "entries": entries if isinstance(entries, list) else [],
            "summary": summary if isinstance(summary, dict) else {},
        }

    def _review_items_from_report(payload: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        entries = payload.get("entries", [])
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            page_id = str(entry.get("page_id") or "")
            bubble_id = str(entry.get("bubble_id") or "")
            for index, repair in enumerate(entry.get("repair_plan", [])):
                if not isinstance(repair, dict):
                    continue
                action = str(repair.get("action") or "repair_translation")
                items.append({
                    "item_id": f"repair:{page_id}:{bubble_id}:{index}",
                    "kind": "repair",
                    "page_id": page_id,
                    "bubble_id": bubble_id,
                    "target": str(repair.get("target") or ""),
                    "action": action,
                    "message": str(repair.get("message") or action),
                    "confidence": _float(repair.get("confidence", 0.0)),
                    "original_text": str(repair.get("original_text") or ""),
                    "suggested_text": str(repair.get("suggested_text") or ""),
                })
            for index, finding in enumerate(entry.get("qa_findings", [])):
                if not isinstance(finding, dict):
                    continue
                action = str(finding.get("action") or "review_qa_finding")
                items.append({
                    "item_id": f"qa:{page_id}:{bubble_id}:{index}",
                    "kind": "qa",
                    "page_id": page_id,
                    "bubble_id": bubble_id,
                    "target": str(finding.get("target") or "review"),
                    "action": action,
                    "message": str(finding.get("message") or finding.get("category") or action),
                    "confidence": _float(finding.get("confidence", 0.0)),
                    "severity": str(finding.get("severity") or finding.get("feedback_type") or ""),
                    "original_text": str(finding.get("original_text") or entry.get("translated_text") or ""),
                    "suggested_text": str(finding.get("suggested_text") or ""),
                })
        return items

    def _review_decision_id(payload: ReviewDecisionRequest) -> str:
        import re
        return "-".join(
            part
            for part in [
                "review",
                _slug_token(payload.page_id or "unknown"),
                _slug_token(payload.bubble_id or "unknown"),
                _slug_token(payload.item_id),
                payload.status,
            ]
            if part
        )

    def _slug_token(value: str) -> str:
        import re
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"

    def _float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _slugify(value: str) -> str:
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
        slug = slug.strip("-")
        if not slug:
            raise HTTPException(status_code=422, detail="Project name must contain letters or numbers")
        return slug

    return app


# ============================================================================
# CLI Command Entry Point
# ============================================================================

def run_web_server(
    project_root: str | Path = ".",
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
) -> None:
    """Run the web UI server.

    Args:
        project_root: Root directory for projects
        host: Server host address
        port: Server port number
        reload: Enable auto-reload for development
    """
    import uvicorn

    if reload:
        # Reload mode requires an import string + factory so the worker
        # subprocess can re-import the app on file changes.
        uvicorn.run(
            "mga.web.frontend:create_app",
            factory=True,
            host=host,
            port=port,
            reload=True,
        )
        return

    app = create_app(project_root=project_root)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Manga Translate Agent Web UI")
    parser.add_argument("--project-root", default=".", help="Root directory for projects")
    parser.add_argument("--host", default="127.0.0.1", help="Server host address")
    parser.add_argument("--port", type=int, default=8000, help="Server port number")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()

    run_web_server(
        project_root=args.project_root,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )