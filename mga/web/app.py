"""FastAPI project management UI for Manga Translate Agent."""

from __future__ import annotations

import re
import json
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import tomli_w
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from mga.cultural.terminology_db import TerminologyDB, TermState as TerminologyAssetState
from mga.memory.entities import CharacterState, DecisionState, TermState
from mga.memory.profile_builder import save_profile
from mga.memory.profile_loader import load_all_profiles, load_character_profile
from mga.memory.state import StateManager
from mga.providers.registry import _PROVIDER_MAP


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
    name_jp: str = ""
    name_zh: str = ""
    archetype: str = ""
    speech_patterns: dict[str, str] = Field(default_factory=dict)
    catchphrases: list[str] = Field(default_factory=list)
    tone_spectrum: dict[str, str] = Field(default_factory=dict)
    translation_notes: dict[str, str] = Field(default_factory=dict)


class TermPayload(BaseModel):
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


def create_app(project_root: str | Path | None = None) -> FastAPI:
    """Create the product Web UI app."""
    root = Path(project_root or ".").resolve()
    root.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="Manga Translate Agent Web UI")
    app.state.project_root = root

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _index_html()

    @app.get("/api/projects")
    def list_projects() -> dict[str, list[dict]]:
        return {
            "projects": [
                summary.model_dump()
                for summary in _list_project_summaries(root)
            ]
        }

    @app.post("/api/projects", status_code=201)
    def create_project(payload: ProjectCreateRequest) -> dict:
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
        project_dir = _resolve_project_dir(root, project_id)
        return _project_summary(project_dir).model_dump()

    @app.get("/api/projects/{project_id}/characters")
    def list_characters(project_id: str) -> dict[str, list[dict]]:
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

    @app.get("/api/projects/{project_id}/terms")
    def list_terms(project_id: str) -> dict[str, list[dict]]:
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

    @app.get("/api/projects/{project_id}/terms/{term_id}")
    def get_term(project_id: str, term_id: str) -> dict:
        project_dir = _resolve_project_dir(root, project_id)
        term = StateManager.get_term(project_dir, term_id)
        if term is None:
            term = _term_from_assets(project_dir, term_id)
        if term is None:
            raise HTTPException(status_code=404, detail="Term not found")
        return term.model_dump()

    @app.post("/api/projects/{project_id}/terms/{term_id}")
    def save_term(project_id: str, term_id: str, payload: TermPayload) -> dict:
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

    @app.get("/api/projects/{project_id}/provider-config")
    def get_provider_config(project_id: str) -> dict:
        project_dir = _resolve_project_dir(root, project_id)
        return _provider_config_response(project_dir)

    @app.post("/api/projects/{project_id}/provider-config")
    def save_provider_config(project_id: str, payload: ProviderConfigPayload) -> dict:
        project_dir = _resolve_project_dir(root, project_id)
        config = _sanitize_provider_config(payload.model_dump())
        path = _provider_config_path(project_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(tomli_w.dumps(config), encoding="utf-8")
        return _provider_config_response(project_dir)

    @app.get("/api/projects/{project_id}/translation-reports")
    def list_translation_reports(project_id: str) -> dict[str, list[dict]]:
        project_dir = _resolve_project_dir(root, project_id)
        return {
            "reports": [
                _translation_report_summary(project_dir, path)
                for path in _iter_translation_reports(project_dir)
            ]
        }

    @app.get("/api/projects/{project_id}/translation-report")
    def get_translation_report(project_id: str, path: str = Query(...)) -> dict:
        project_dir = _resolve_project_dir(root, project_id)
        report_path = _resolve_report_path(project_dir, path)
        return _read_translation_report(report_path)

    @app.get("/api/projects/{project_id}/review-items")
    def list_review_items(project_id: str, path: str = Query(...)) -> dict:
        project_dir = _resolve_project_dir(root, project_id)
        report_path = _resolve_report_path(project_dir, path)
        return {"items": _review_items_from_report(_read_translation_report(report_path))}

    @app.post("/api/projects/{project_id}/review-decisions", status_code=201)
    def create_review_decision(project_id: str, payload: ReviewDecisionRequest) -> dict:
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

    return app


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
    term_id = _term_id(item.term_jp)
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


def _term_id(value: str) -> str:
    return re.sub(r"\s+", "_", value.strip().lower()) or "term"


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
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "item"


def _float(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower())
    slug = slug.strip("-")
    if not slug:
        raise HTTPException(status_code=422, detail="Project name must contain letters or numbers")
    return slug


def _index_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Manga Translate Agent</title>
  <script crossorigin src="https://unpkg.com/react@18/umd/react.development.js"></script>
  <script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.development.js"></script>
  <style>
    :root { color-scheme: light; font-family: Inter, Segoe UI, Arial, sans-serif; }
    body { margin: 0; background: #f6f7f9; color: #1f2933; }
    header { height: 56px; display: flex; align-items: center; justify-content: space-between; padding: 0 24px; border-bottom: 1px solid #d8dde6; background: #ffffff; }
    main { max-width: 1180px; margin: 0 auto; padding: 24px; display: grid; grid-template-columns: 300px 1fr; gap: 20px; }
    h1 { font-size: 18px; margin: 0; font-weight: 650; }
    h2 { font-size: 15px; margin: 0 0 12px; font-weight: 650; }
    h3 { font-size: 13px; margin: 0; font-weight: 650; }
    form, section { background: #ffffff; border: 1px solid #d8dde6; border-radius: 8px; padding: 16px; }
    label { display: grid; gap: 6px; font-size: 12px; color: #52616f; margin-bottom: 12px; }
    input, textarea { border: 1px solid #c8d0da; border-radius: 6px; padding: 8px 10px; font-size: 14px; font-family: inherit; }
    input { height: 34px; padding-top: 0; padding-bottom: 0; }
    textarea { min-height: 76px; resize: vertical; }
    button { height: 36px; border: 0; border-radius: 6px; background: #1f6feb; color: #ffffff; font-weight: 650; padding: 0 14px; cursor: pointer; }
    .ghost { background: #eef2f6; color: #243342; }
    button:disabled { background: #9aa8b6; cursor: default; }
    .project { display: grid; grid-template-columns: 1fr auto; gap: 8px; padding: 12px 0; border-top: 1px solid #edf0f4; }
    .project:first-child { border-top: 0; }
    .name { font-weight: 650; }
    .meta, .counts { color: #667785; font-size: 12px; }
    .empty { color: #667785; padding: 12px 0; }
    .workspace { display: grid; grid-template-columns: 260px 1fr; gap: 16px; align-items: start; }
    .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .character { width: 100%; height: auto; min-height: 42px; display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; margin-bottom: 8px; background: #ffffff; color: #1f2933; border: 1px solid #d8dde6; text-align: left; }
    .character.active { border-color: #1f6feb; background: #f2f7ff; }
    .term { width: 100%; height: auto; min-height: 42px; display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: center; margin-bottom: 8px; background: #ffffff; color: #1f2933; border: 1px solid #d8dde6; text-align: left; }
    .term.active { border-color: #1f6feb; background: #f2f7ff; }
    .report { width: 100%; height: auto; min-height: 42px; display: grid; gap: 4px; margin-bottom: 8px; background: #ffffff; color: #1f2933; border: 1px solid #d8dde6; text-align: left; }
    .editor-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .editor-grid label:nth-child(n+4) { grid-column: 1 / -1; }
    .full { grid-column: 1 / -1; }
    .comparison { margin-top: 14px; display: grid; gap: 10px; }
    .entry { border: 1px solid #d8dde6; border-radius: 8px; padding: 12px; display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
    .entry .meta { grid-column: 1 / -1; }
    .review-item { border: 1px solid #d8dde6; border-radius: 8px; padding: 12px; display: grid; gap: 8px; margin-top: 10px; }
    .source, .target { white-space: pre-wrap; line-height: 1.45; }
    @media (max-width: 760px) { main { grid-template-columns: 1fr; padding: 16px; } }
    @media (max-width: 920px) { .workspace, .editor-grid, .entry { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div id="app"></div>
  <script>
    const e = React.createElement;
    function App() {
      const [projects, setProjects] = React.useState([]);
      const [selectedProject, setSelectedProject] = React.useState(null);
      const [characters, setCharacters] = React.useState([]);
      const [selectedCharacter, setSelectedCharacter] = React.useState(null);
      const [form, setForm] = React.useState(emptyCharacter());
      const [terms, setTerms] = React.useState([]);
      const [selectedTerm, setSelectedTerm] = React.useState(null);
      const [termForm, setTermForm] = React.useState(emptyTerm());
      const [providerConfig, setProviderConfig] = React.useState(emptyProviderConfig());
      const [providerName, setProviderName] = React.useState("openai");
      const [providerSettings, setProviderSettings] = React.useState("");
      const [reports, setReports] = React.useState([]);
      const [selectedReport, setSelectedReport] = React.useState(null);
      const [reportEntries, setReportEntries] = React.useState([]);
      const [reviewItems, setReviewItems] = React.useState([]);
      const [name, setName] = React.useState("");
      const [busy, setBusy] = React.useState(false);
      const load = () => fetch("/api/projects").then(r => r.json()).then(data => {
        const items = data.projects || [];
        setProjects(items);
        if (!selectedProject && items.length) setSelectedProject(items[0]);
      });
      React.useEffect(() => { load(); }, []);
      React.useEffect(() => {
        if (!selectedProject) return;
        fetch("/api/projects/" + selectedProject.id + "/characters")
          .then(r => r.json())
          .then(data => setCharacters(data.characters || []));
        fetch("/api/projects/" + selectedProject.id + "/translation-reports")
          .then(r => r.json())
          .then(data => setReports(data.reports || []));
        fetch("/api/projects/" + selectedProject.id + "/terms")
          .then(r => r.json())
          .then(data => setTerms(data.terms || []));
        fetch("/api/projects/" + selectedProject.id + "/provider-config")
          .then(r => r.json())
          .then(data => {
            setProviderConfig(providerConfigToForm(data));
            const names = Object.keys(data.providers || {});
            const first = names[0] || (data.provider_options || ["openai"])[0] || "openai";
            setProviderName(first);
            setProviderSettings(mappingToText((data.providers || {})[first] || {}));
          });
      }, [selectedProject]);
      const create = async event => {
        event.preventDefault();
        if (!name.trim()) return;
        setBusy(true);
        const response = await fetch("/api/projects", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({name})
        });
        setBusy(false);
        if (response.ok) {
          setName("");
          load();
        }
      };
      const openCharacter = async id => {
        const response = await fetch("/api/projects/" + selectedProject.id + "/characters/" + id);
        if (!response.ok) return;
        const profile = await response.json();
        setSelectedCharacter(profile.character_id);
        setForm(profileToForm(profile));
      };
      const newCharacter = () => {
        setSelectedCharacter("");
        setForm(emptyCharacter());
      };
      const saveCharacter = async event => {
        event.preventDefault();
        if (!selectedProject || !form.character_id.trim()) return;
        const id = form.character_id.trim();
        const response = await fetch("/api/projects/" + selectedProject.id + "/characters/" + id, {
          method: "PUT",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(formToPayload(form))
        });
        if (!response.ok) return;
        const profile = await response.json();
        setSelectedCharacter(profile.character_id);
        setForm(profileToForm(profile));
        const list = await fetch("/api/projects/" + selectedProject.id + "/characters").then(r => r.json());
        setCharacters(list.characters || []);
      };
      const openTerm = async id => {
        const response = await fetch("/api/projects/" + selectedProject.id + "/terms/" + encodeURIComponent(id));
        if (!response.ok) return;
        const term = await response.json();
        setSelectedTerm(term.term_id);
        setTermForm(termToForm(term));
      };
      const newTerm = () => {
        setSelectedTerm("");
        setTermForm(emptyTerm());
      };
      const saveTerm = async event => {
        event.preventDefault();
        if (!selectedProject || !termForm.term_id.trim()) return;
        const id = termForm.term_id.trim();
        const response = await fetch("/api/projects/" + selectedProject.id + "/terms/" + encodeURIComponent(id), {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(termFormToPayload(termForm))
        });
        if (!response.ok) return;
        const term = await response.json();
        setSelectedTerm(term.term_id);
        setTermForm(termToForm(term));
        const list = await fetch("/api/projects/" + selectedProject.id + "/terms").then(r => r.json());
        setTerms(list.terms || []);
        load();
      };
      const updateProviderStage = (stage, role, value) => setProviderConfig(current => {
        const stages = Object.assign({}, current.stages);
        stages[stage] = Object.assign({}, stages[stage] || {}, {[role]: value});
        return Object.assign({}, current, {stages});
      });
      const chooseProvider = name => {
        const clean = name || "openai";
        setProviderName(clean);
        setProviderSettings(mappingToText((providerConfig.providers || {})[clean] || {}));
      };
      const saveProviderConfig = async event => {
        event.preventDefault();
        if (!selectedProject) return;
        const providers = Object.assign({}, providerConfig.providers || {});
        providers[providerName] = textToMapping(providerSettings);
        const payload = Object.assign({}, providerConfig, {providers});
        const response = await fetch("/api/projects/" + selectedProject.id + "/provider-config", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(payload)
        });
        if (!response.ok) return;
        const saved = providerConfigToForm(await response.json());
        setProviderConfig(saved);
        setProviderSettings(mappingToText((saved.providers || {})[providerName] || {}));
      };
      const openReport = async report => {
        const response = await fetch("/api/projects/" + selectedProject.id + "/translation-report?path=" + encodeURIComponent(report.path));
        if (!response.ok) return;
        const payload = await response.json();
        setSelectedReport(report.path);
        setReportEntries(payload.entries || []);
        const review = await fetch("/api/projects/" + selectedProject.id + "/review-items?path=" + encodeURIComponent(report.path)).then(r => r.json());
        setReviewItems(review.items || []);
      };
      const decideReview = async (item, status) => {
        if (!selectedProject) return;
        const reportPath = selectedReport || (reports[0] ? reports[0].path : "");
        if (!reportPath) return;
        await fetch("/api/projects/" + selectedProject.id + "/review-decisions", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(Object.assign({}, item, {report_path: reportPath, status}))
        });
      };
      React.useEffect(() => {
        if (selectedProject && reports.length && !selectedReport) openReport(reports[0]);
      }, [reports, selectedProject, selectedReport]);
      React.useEffect(() => {
        if (selectedProject && terms.length && selectedTerm === null) openTerm(terms[0].term_id);
      }, [terms, selectedProject, selectedTerm]);
      const update = (key, value) => setForm(current => Object.assign({}, current, {[key]: value}));
      const updateTerm = (key, value) => setTermForm(current => Object.assign({}, current, {[key]: value}));
      const visibleEntries = reportEntries.length ? reportEntries : (reports[0] ? reports[0].preview_entries || [] : []);
      const visibleReviewItems = reviewItems.length ? reviewItems : (reports[0] ? reports[0].review_items || [] : []);
      return e(React.Fragment, null,
        e("header", null, e("h1", null, "Manga Translate Agent"), e("span", {className: "meta"}, "Project Workspace")),
        e("main", null,
          e("form", {onSubmit: create},
            e("h2", null, "New Project"),
            e("label", null, "Name", e("input", {value: name, onChange: ev => setName(ev.target.value), placeholder: "Chapter workspace"})),
            e("button", {disabled: busy}, busy ? "Creating" : "Create")
          ),
          e("section", null,
            e("h2", null, "Projects"),
            projects.length === 0
              ? e("div", {className: "empty"}, "No projects")
              : projects.map(project => e("div", {className: "project", key: project.id},
                  e("div", null,
                    e("div", {className: "name"}, project.name),
                    e("div", {className: "meta"}, project.source_lang + " to " + project.target_lang)
                  ),
                  e("div", {className: "row"},
                    e("div", {className: "counts"}, project.character_count + " characters / " + project.term_count + " terms"),
                    e("button", {className: "ghost", onClick: () => setSelectedProject(project)}, "Open")
                  )
                ))
          ),
          selectedProject && e("section", {className: "full"},
            e("div", {className: "workspace"},
              e("div", null,
                e("div", {className: "row"},
                  e("h2", null, "Characters"),
                  e("button", {className: "ghost", onClick: newCharacter}, "New")
                ),
                characters.length === 0
                  ? e("div", {className: "empty"}, "No characters")
                  : characters.map(character => e("button", {
                      className: "character" + (character.character_id === selectedCharacter ? " active" : ""),
                      key: character.character_id,
                      onClick: () => openCharacter(character.character_id)
                    },
                      e("span", null,
                        e("span", {className: "name"}, character.name_jp || character.character_id),
                        e("div", {className: "meta"}, character.name_zh || character.archetype || character.character_id)
                      ),
                      e("span", {className: "counts"}, character.speech_pattern_count + " patterns")
                    ))
              ),
              e("form", {onSubmit: saveCharacter},
                e("div", {className: "row"}, e("h2", null, selectedProject.name), e("span", {className: "meta"}, "Character Profile")),
                e("div", {className: "editor-grid"},
                  e("label", null, "Character ID", e("input", {value: form.character_id, onChange: ev => update("character_id", ev.target.value)})),
                  e("label", null, "Japanese Name", e("input", {value: form.name_jp, onChange: ev => update("name_jp", ev.target.value)})),
                  e("label", null, "Chinese Name", e("input", {value: form.name_zh, onChange: ev => update("name_zh", ev.target.value)})),
                  e("label", null, "Archetype", e("input", {value: form.archetype, onChange: ev => update("archetype", ev.target.value)})),
                  e("label", null, "Catchphrases", e("textarea", {value: form.catchphrases, onChange: ev => update("catchphrases", ev.target.value)})),
                  e("label", null, "Speech Patterns", e("textarea", {value: form.speech_patterns, onChange: ev => update("speech_patterns", ev.target.value)})),
                  e("label", null, "Tone Spectrum", e("textarea", {value: form.tone_spectrum, onChange: ev => update("tone_spectrum", ev.target.value)})),
                  e("label", null, "Translation Notes", e("textarea", {value: form.translation_notes, onChange: ev => update("translation_notes", ev.target.value)})),
                  e("button", {disabled: !form.character_id.trim()}, "Save Profile")
                )
              )
            )
          ),
          selectedProject && e("section", {className: "full"},
            e("div", {className: "workspace"},
              e("div", null,
                e("div", {className: "row"},
                  e("h2", null, "Terminology"),
                  e("button", {className: "ghost", onClick: newTerm}, "New")
                ),
                terms.length === 0
                  ? e("div", {className: "empty"}, "No terms")
                  : terms.map(term => e("button", {
                      className: "term" + (term.term_id === selectedTerm ? " active" : ""),
                      key: term.term_id,
                      onClick: () => openTerm(term.term_id)
                    },
                      e("span", null,
                        e("span", {className: "name"}, term.term_jp || term.term_id),
                        e("div", {className: "meta"}, (term.term_zh || "No translation") + (term.strategy ? " / " + term.strategy : ""))
                      ),
                      e("span", {className: "counts"}, term.pending_human_review ? "review" : term.frequency + " uses")
                    ))
              ),
              e("form", {onSubmit: saveTerm},
                e("div", {className: "row"}, e("h2", null, selectedProject.name), e("span", {className: "meta"}, "Terminology Management")),
                e("div", {className: "editor-grid"},
                  e("label", null, "Term ID", e("input", {value: termForm.term_id, onChange: ev => updateTerm("term_id", ev.target.value)})),
                  e("label", null, "Source Term", e("input", {value: termForm.term_jp, onChange: ev => updateTerm("term_jp", ev.target.value)})),
                  e("label", null, "Translation", e("input", {value: termForm.term_zh, onChange: ev => updateTerm("term_zh", ev.target.value)})),
                  e("label", null, "Category / Type", e("input", {value: termForm.cultural_weight, onChange: ev => updateTerm("cultural_weight", ev.target.value)})),
                  e("label", null, "Strategy", e("input", {value: termForm.strategy, onChange: ev => updateTerm("strategy", ev.target.value)})),
                  e("label", null, "Frequency", e("input", {type: "number", value: termForm.frequency, onChange: ev => updateTerm("frequency", ev.target.value)})),
                  e("label", null, "Candidate Translations", e("textarea", {value: termForm.candidate_translations, onChange: ev => updateTerm("candidate_translations", ev.target.value)})),
                  e("label", null, "Rejected Reasons", e("textarea", {value: termForm.rejected_reasons, onChange: ev => updateTerm("rejected_reasons", ev.target.value)})),
                  e("label", null, "Accepted Reason", e("textarea", {value: termForm.accepted_reason, onChange: ev => updateTerm("accepted_reason", ev.target.value)})),
                  e("label", null, "Applicability Scope", e("textarea", {value: termForm.applicability_scope, onChange: ev => updateTerm("applicability_scope", ev.target.value)})),
                  e("label", null, "Notes", e("textarea", {value: termForm.context, onChange: ev => updateTerm("context", ev.target.value)})),
                  e("label", null, "Pending Human Review", e("input", {type: "checkbox", checked: termForm.pending_human_review, onChange: ev => updateTerm("pending_human_review", ev.target.checked)})),
                  e("button", {disabled: !termForm.term_id.trim()}, "Save Term")
                )
              )
            )
          ),
          selectedProject && e("section", {className: "full"},
            e("form", {onSubmit: saveProviderConfig},
              e("div", {className: "row"},
                e("h2", null, "Provider Configuration"),
                e("span", {className: "meta"}, providerConfig.path || "configs/providers.toml")
              ),
              e("div", {className: "editor-grid"},
                ["vision", "translation", "qa"].flatMap(stage => [
                  e("label", {key: stage + "-primary"}, stage + " Primary", e("input", {value: (providerConfig.stages[stage] || {}).primary || "", onChange: ev => updateProviderStage(stage, "primary", ev.target.value), list: "provider-options"})),
                  e("label", {key: stage + "-fallback"}, stage + " Fallback", e("input", {value: (providerConfig.stages[stage] || {}).fallback || "", onChange: ev => updateProviderStage(stage, "fallback", ev.target.value), list: "provider-options"})),
                  e("label", {key: stage + "-local"}, stage + " Local", e("input", {value: (providerConfig.stages[stage] || {}).local || "", onChange: ev => updateProviderStage(stage, "local", ev.target.value), list: "provider-options"}))
                ]),
                e("datalist", {id: "provider-options"}, (providerConfig.provider_options || []).map(name => e("option", {key: name, value: name}))),
                e("label", null, "Provider", e("input", {value: providerName, onChange: ev => chooseProvider(ev.target.value), list: "provider-options"})),
                e("label", null, "Provider Settings", e("textarea", {value: providerSettings, onChange: ev => setProviderSettings(ev.target.value), placeholder: "api_key=${OPENAI_API_KEY}\\ntext_model=gpt-4o-mini"})),
                e("button", null, "Save Provider Config")
              )
            )
          ),
          selectedProject && e("section", {className: "full"},
            e("div", {className: "row"},
              e("h2", null, "Translation Reports"),
              selectedReport && e("span", {className: "meta"}, selectedReport)
            ),
            reports.length === 0
              ? e("div", {className: "empty"}, "No translation reports")
              : reports.map(report => e("button", {className: "report", key: report.path, onClick: () => openReport(report)},
                  e("span", {className: "name"}, report.path),
                  e("span", {className: "meta"}, report.entry_count + " entries / " + report.entries_needing_human_review + " review")
                )),
            e("div", {className: "comparison"},
              visibleEntries.map(entry => e("div", {className: "entry", key: entry.page_id + ':' + entry.bubble_id},
                e("div", {className: "meta"}, entry.page_id + " / " + entry.bubble_id + " / confidence " + Number(entry.confidence || 0).toFixed(2) + (entry.needs_human_review ? " / needs review" : "")),
                e("div", {className: "source"}, entry.source_text || ""),
                e("div", {className: "target"}, entry.translated_text || ""),
                (entry.qa_findings || []).length > 0 && e("div", {className: "meta"}, (entry.qa_findings || []).length + " QA findings")
              ))
            ),
            e("h2", null, "QA Review"),
            renderReviewItems(visibleReviewItems, decideReview)
          )
        )
      );
    }
    function emptyCharacter() {
      return {character_id: "", name_jp: "", name_zh: "", archetype: "", catchphrases: "", speech_patterns: "", tone_spectrum: "", translation_notes: ""};
    }
    function profileToForm(profile) {
      return {
        character_id: profile.character_id || "",
        name_jp: profile.name_jp || "",
        name_zh: profile.name_zh || "",
        archetype: profile.archetype || "",
        catchphrases: (profile.catchphrases || []).join("\\n"),
        speech_patterns: mappingToText(profile.speech_patterns || {}),
        tone_spectrum: mappingToText(profile.tone_spectrum || {}),
        translation_notes: mappingToText(profile.translation_notes || {})
      };
    }
    function formToPayload(form) {
      return {
        name_jp: form.name_jp,
        name_zh: form.name_zh,
        archetype: form.archetype,
        catchphrases: lines(form.catchphrases),
        speech_patterns: textToMapping(form.speech_patterns),
        tone_spectrum: textToMapping(form.tone_spectrum),
        translation_notes: textToMapping(form.translation_notes)
      };
    }
    function emptyProviderConfig() {
      return {
        path: "configs/providers.toml",
        provider_options: [],
        stages: {
          vision: {primary: "", fallback: "", local: ""},
          translation: {primary: "", fallback: "", local: ""},
          qa: {primary: "", fallback: "", local: ""}
        },
        providers: {}
      };
    }
    function providerConfigToForm(payload) {
      const base = emptyProviderConfig();
      return Object.assign({}, base, {
        path: payload.path || base.path,
        provider_options: payload.provider_options || [],
        stages: Object.assign({}, base.stages, payload.stages || {}),
        providers: payload.providers || {}
      });
    }
    function emptyTerm() {
      return {term_id: "", term_jp: "", term_zh: "", candidate_translations: "", context: "", cultural_weight: "", strategy: "", accepted_reason: "", rejected_reasons: "", applicability_scope: "", pending_human_review: false, frequency: 0};
    }
    function termToForm(term) {
      return {
        term_id: term.term_id || "",
        term_jp: term.term_jp || "",
        term_zh: term.term_zh || "",
        candidate_translations: (term.candidate_translations || []).join("\\n"),
        context: term.context || "",
        cultural_weight: term.cultural_weight || "",
        strategy: term.strategy || "",
        accepted_reason: term.accepted_reason || "",
        rejected_reasons: mappingToText(term.rejected_reasons || {}),
        applicability_scope: term.applicability_scope || "",
        pending_human_review: Boolean(term.pending_human_review),
        frequency: Number(term.frequency || 0)
      };
    }
    function termFormToPayload(form) {
      return {
        term_jp: form.term_jp,
        term_zh: form.term_zh,
        candidate_translations: lines(form.candidate_translations),
        context: form.context,
        cultural_weight: form.cultural_weight,
        strategy: form.strategy,
        accepted_reason: form.accepted_reason,
        rejected_reasons: textToMapping(form.rejected_reasons),
        applicability_scope: form.applicability_scope,
        pending_human_review: Boolean(form.pending_human_review),
        frequency: Number(form.frequency || 0)
      };
    }
    function lines(value) {
      return String(value || "").split(/\\n+/).map(item => item.trim()).filter(Boolean);
    }
    function mappingToText(value) {
      return Object.entries(value).map(([key, item]) => key + "=" + item).join("\\n");
    }
    function textToMapping(value) {
      return Object.fromEntries(lines(value).map(line => {
        const index = line.indexOf("=");
        return index === -1 ? [line, ""] : [line.slice(0, index).trim(), line.slice(index + 1).trim()];
      }).filter(([key]) => key));
    }
    function renderReviewItems(items, decideReview) {
      if (items.length === 0) {
        return e("div", {className: "empty"}, "No QA review items");
      }
      return items.map(item => e("div", {className: "review-item", key: item.item_id},
        e("div", {className: "meta"}, item.kind + " / " + item.page_id + " / " + item.bubble_id + " / " + item.action),
        e("div", null, item.message),
        item.suggested_text && e("div", {className: "target"}, item.suggested_text),
        e("div", {className: "row"},
          e("button", {onClick: () => decideReview(item, "accept")}, "Accept"),
          e("button", {className: "ghost", onClick: () => decideReview(item, "reject")}, "Reject")
        )
      ));
    }
    ReactDOM.createRoot(document.getElementById("app")).render(e(App));
  </script>
</body>
</html>"""
