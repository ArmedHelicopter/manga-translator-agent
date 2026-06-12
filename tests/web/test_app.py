from __future__ import annotations

import json

from fastapi.testclient import TestClient

from mga.web import create_app


def test_web_root_returns_jinja2_template(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    response = client.get("/")

    assert response.status_code == 200
    # Check for key elements from the Jinja2 template
    assert "Manga Translate Agent" in response.text or "漫画翻译助手" in response.text
    assert 'id="app"' in response.text or 'class="app-container"' in response.text
    # Check for blue-white theme elements
    assert "blue" in response.text.lower() or "--blue-" in response.text or "#3b82f6" in response.text
    # Check for key navigation elements
    assert "Dashboard" in response.text or "仪表盘" in response.text
    assert "Translate" in response.text or "翻译" in response.text
    # Check for tutorial wizard elements
    assert "tutorial" in response.text.lower() or "Welcome" in response.text or "欢迎" in response.text
    # Check for i18n support
    assert "EN" in response.text or "中文" in response.text


def test_project_api_creates_and_lists_projects(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    empty = client.get("/api/projects")
    assert empty.status_code == 200
    assert empty.json() == {"projects": []}

    created = client.post(
        "/api/projects",
        json={
            "name": "Glass Blade",
            "source_lang": "ja",
            "target_lang": "zh-CN",
        },
    )

    assert created.status_code == 201
    payload = created.json()
    assert payload["id"] == "glass-blade"
    assert payload["name"] == "Glass Blade"
    assert payload["source_lang"] == "ja"
    assert payload["target_lang"] == "zh-CN"
    assert (tmp_path / "glass-blade" / "project_meta.toml").exists()
    assert (tmp_path / "glass-blade" / "memory" / "state" / "index.json").exists()

    listed = client.get("/api/projects")
    assert listed.status_code == 200
    assert listed.json()["projects"][0]["id"] == "glass-blade"


def test_project_api_rejects_duplicate_projects(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))

    first = client.post("/api/projects", json={"name": "Glass Blade"})
    second = client.post("/api/projects", json={"name": "Glass Blade"})

    assert first.status_code == 201
    assert second.status_code == 409


def test_character_profile_api_saves_runtime_state_and_toml(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Glass Blade"}).json()

    saved = client.put(
        f"/api/projects/{project['id']}/characters/akari",
        json={
            "name_jp": "Akari",
            "name_zh": "Deng",
            "archetype": "protagonist",
            "speech_patterns": {"default": "polite"},
            "catchphrases": ["I understand"],
            "tone_spectrum": {"default": "quiet"},
            "translation_notes": {"addressing": "uses surnames"},
        },
    )

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["character_id"] == "akari"
    assert payload["speech_patterns"] == {"default": "polite"}

    state_path = tmp_path / "glass-blade" / "memory" / "state" / "characters" / "akari.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["name_jp"] == "Akari"
    assert state["translation_notes"] == {"addressing": "uses surnames"}

    profile_toml = (tmp_path / "glass-blade" / "character_profiles" / "akari.toml").read_text(
        encoding="utf-8"
    )
    assert 'character_id = "akari"' in profile_toml
    assert 'default = "polite"' in profile_toml
    assert '"I understand"' in profile_toml

    listed = client.get(f"/api/projects/{project['id']}/characters")
    assert listed.status_code == 200
    assert listed.json()["characters"] == [
        {
            "character_id": "akari",
            "name_jp": "Akari",
            "name_zh": "Deng",
            "archetype": "protagonist",
            "speech_pattern_count": 1,
            "catchphrase_count": 1,
            "tone_count": 1,
            "translation_note_count": 1,
        }
    ]

    fetched = client.get(f"/api/projects/{project['id']}/characters/akari")
    assert fetched.status_code == 200
    assert fetched.json()["name_zh"] == "Deng"


def test_character_profile_api_rejects_unknown_character(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Glass Blade"}).json()

    response = client.get(f"/api/projects/{project['id']}/characters/missing")

    assert response.status_code == 404


def test_term_api_saves_runtime_state_and_toml_asset(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Glass Blade"}).json()

    saved = client.post(
        f"/api/projects/{project['id']}/terms/glass_join",
        json={
            "term_jp": "glass join",
            "term_zh": "glass mending",
            "candidate_translations": ["glass mending", "crystal join"],
            "context": "fictional repair term",
            "cultural_weight": "ability",
            "strategy": "coined",
            "accepted_reason": "Matches established ritual term.",
            "rejected_reasons": {"crystal join": "Sounds like a material name."},
            "applicability_scope": "Use for the named repair art only.",
            "pending_human_review": True,
            "frequency": 3,
        },
    )

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["term_id"] == "glass_join"
    assert payload["term_jp"] == "glass join"
    assert payload["pending_human_review"] is True
    assert payload["rejected_reasons"] == {
        "crystal join": "Sounds like a material name.",
    }

    state_path = tmp_path / project["id"] / "memory" / "state" / "terms" / "glass_join.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["term_zh"] == "glass mending"
    assert state["candidate_translations"] == ["glass mending", "crystal join"]

    terms_toml = (tmp_path / project["id"] / "terminology" / "terms.toml").read_text(
        encoding="utf-8"
    )
    assert "glass join" in terms_toml
    assert "pending_human_review = true" in terms_toml
    assert "accepted_reason" in terms_toml

    listed = client.get(f"/api/projects/{project['id']}/terms")
    assert listed.status_code == 200
    assert listed.json()["terms"] == [
        {
            "term_id": "glass_join",
            "term_jp": "glass join",
            "term_zh": "glass mending",
            "cultural_weight": "ability",
            "strategy": "coined",
            "pending_human_review": True,
            "frequency": 3,
            "candidate_count": 2,
        }
    ]

    fetched = client.get(f"/api/projects/{project['id']}/terms/glass_join")
    assert fetched.status_code == 200
    assert fetched.json()["accepted_reason"] == "Matches established ritual term."


def test_term_api_lists_toml_only_assets(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Glass Blade"}).json()
    term_dir = tmp_path / project["id"] / "terminology"
    term_dir.mkdir()
    (term_dir / "terms.toml").write_text(
        '[terms]\n'
        'katana = { term_jp = "katana", term_target = "sword", '
        'strategy = "preserve", pending_human_review = true }\n',
        encoding="utf-8",
    )

    listed = client.get(f"/api/projects/{project['id']}/terms")

    assert listed.status_code == 200
    assert listed.json()["terms"][0]["term_id"] == "katana"
    assert listed.json()["terms"][0]["term_zh"] == "sword"
    assert listed.json()["terms"][0]["pending_human_review"] is True

    fetched = client.get(f"/api/projects/{project['id']}/terms/katana")
    assert fetched.status_code == 200
    assert fetched.json()["strategy"] == "preserve"


def test_provider_config_api_saves_project_local_env_placeholders(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Glass Blade"}).json()

    saved = client.post(
        f"/api/projects/{project['id']}/provider-config",
        json={
            "stages": {
                "vision": {"primary": "openai", "fallback": "gemini", "local": "ollama"},
                "translation": {"primary": "gemini", "fallback": "deepseek"},
                "qa": {"primary": "deepseek", "fallback": "gemini"},
            },
            "providers": {
                "openai": {
                    "api_key": "${OPENAI_API_KEY}",
                    "vision_model": "gpt-4o",
                    "text_model": "gpt-4o-mini",
                },
                "gemini": {
                    "api_key": "${GEMINI_API_KEY}",
                    "model": "gemini-2.5-pro",
                },
                "deepseek": {"api_key": "${DEEPSEEK_API_KEY}", "model": "deepseek-chat"},
                "ollama": {"base_url": "http://localhost:11434", "model": "llama3.1"},
            },
        },
    )

    assert saved.status_code == 200
    payload = saved.json()
    assert payload["path"] == "configs/providers.toml"
    assert "openai" in payload["provider_options"]
    assert payload["stages"]["vision"]["primary"] == "openai"
    assert payload["providers"]["openai"]["api_key"] == "${OPENAI_API_KEY}"

    config_path = tmp_path / project["id"] / "configs" / "providers.toml"
    config_text = config_path.read_text(encoding="utf-8")
    assert '[stages.vision]' in config_text
    assert 'primary = "openai"' in config_text
    assert 'api_key = "${OPENAI_API_KEY}"' in config_text
    assert "sk-" not in config_text

    fetched = client.get(f"/api/projects/{project['id']}/provider-config")
    assert fetched.status_code == 200
    assert fetched.json()["providers"]["gemini"]["model"] == "gemini-2.5-pro"


def test_provider_config_api_redacts_and_rejects_raw_secret_values(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Glass Blade"}).json()
    config_dir = tmp_path / project["id"] / "configs"
    config_dir.mkdir()
    (config_dir / "providers.toml").write_text(
        '[stages.vision]\nprimary = "openai"\n\n'
        '[providers.openai]\napi_key = "sk-local-secret"\ntext_model = "gpt-4o-mini"\n',
        encoding="utf-8",
    )

    fetched = client.get(f"/api/projects/{project['id']}/provider-config")

    assert fetched.status_code == 200
    assert fetched.json()["providers"]["openai"]["api_key"] == "***"

    rejected = client.post(
        f"/api/projects/{project['id']}/provider-config",
        json={
            "stages": {"vision": {"primary": "openai"}},
            "providers": {"openai": {"api_key": "sk-raw-secret"}},
        },
    )

    assert rejected.status_code == 422


def test_translation_report_api_lists_and_reads_reports(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Glass Blade"}).json()
    report_path = tmp_path / project["id"] / "translations" / "ch1" / "translation-report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "page_id": "p1",
                        "bubble_id": "b1",
                        "source_text": "source",
                        "translated_text": "target",
                        "confidence": 0.62,
                        "needs_human_review": True,
                        "qa_findings": [{"message": "check tone"}],
                    }
                ],
                "summary": {
                    "avg_confidence": 0.62,
                    "entries_needing_human_review": 1,
                },
            }
        ),
        encoding="utf-8",
    )

    listed = client.get(f"/api/projects/{project['id']}/translation-reports")

    assert listed.status_code == 200
    assert listed.json()["reports"][0]["path"] == "translations/ch1/translation-report.json"
    assert listed.json()["reports"][0]["entry_count"] == 1
    assert listed.json()["reports"][0]["preview_entries"][0]["source_text"] == "source"
    assert listed.json()["reports"][0]["entries_needing_human_review"] == 1
    assert listed.json()["reports"][0]["avg_confidence"] == 0.62

    fetched = client.get(
        f"/api/projects/{project['id']}/translation-report",
        params={"path": "translations/ch1/translation-report.json"},
    )

    assert fetched.status_code == 200
    assert fetched.json()["entries"][0]["source_text"] == "source"
    assert fetched.json()["entries"][0]["translated_text"] == "target"
    assert fetched.json()["entries"][0]["qa_findings"] == [{"message": "check tone"}]


def test_translation_report_api_rejects_path_escape(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Glass Blade"}).json()

    response = client.get(
        f"/api/projects/{project['id']}/translation-report",
        params={"path": "../translation-report.json"},
    )

    assert response.status_code == 404


def test_review_item_api_lists_repairs_and_records_decisions(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Glass Blade"}).json()
    report_path = tmp_path / project["id"] / "translation-report.json"
    report_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "page_id": "p1",
                        "bubble_id": "b1",
                        "translated_text": "old line",
                        "qa_findings": [
                            {
                                "message": "tone drift",
                                "feedback_type": "warning",
                                "confidence": 0.74,
                            }
                        ],
                        "repair_plan": [
                            {
                                "target": "persona",
                                "action": "repair_persona_rendering",
                                "message": "voice drift",
                                "confidence": 0.82,
                                "suggested_text": "new line",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    listed = client.get(
        f"/api/projects/{project['id']}/review-items",
        params={"path": "translation-report.json"},
    )

    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["kind"] for item in items] == ["repair", "qa"]
    assert items[0]["action"] == "repair_persona_rendering"
    assert items[0]["suggested_text"] == "new line"
    assert items[1]["message"] == "tone drift"

    decision = client.post(
        f"/api/projects/{project['id']}/review-decisions",
        json={
            **items[0],
            "report_path": "translation-report.json",
            "status": "accept",
            "rationale": "Looks right.",
        },
    )

    assert decision.status_code == 201
    payload = decision.json()
    assert payload["stage"] == "review"
    assert payload["input_ref"] == "p1/b1"
    assert payload["decision"] == "accept repair_persona_rendering for b1"
    assert payload["rationale"] == "Looks right."
    assert payload["confidence"] == 0.82
    assert payload["metadata"]["item_id"] == "repair:p1:b1:0"
    assert payload["metadata"]["status"] == "accept"

    decision_path = (
        tmp_path
        / project["id"]
        / "memory"
        / "state"
        / "decisions"
        / f"{payload['decision_id']}.json"
    )
    assert decision_path.exists()


def test_review_decision_api_rejects_invalid_status(tmp_path):
    client = TestClient(create_app(project_root=tmp_path))
    project = client.post("/api/projects", json={"name": "Glass Blade"}).json()
    (tmp_path / project["id"] / "translation-report.json").write_text(
        json.dumps({"entries": []}),
        encoding="utf-8",
    )

    response = client.post(
        f"/api/projects/{project['id']}/review-decisions",
        json={
            "report_path": "translation-report.json",
            "item_id": "qa:p1:b1:0",
            "status": "maybe",
            "page_id": "p1",
            "bubble_id": "b1",
        },
    )

    assert response.status_code == 422
