from pathlib import Path


ROOT = Path(__file__).parents[1] / "src" / "personal_agent" / "web"
HTML = (ROOT / "index.html").read_text(encoding="utf-8")
APP = (ROOT / "app.js").read_text(encoding="utf-8")
CSS = (ROOT / "style.css").read_text(encoding="utf-8")


def test_settings_uses_goal_oriented_owner_language():
    assert "AI 연결" in HTML
    assert "파일 · 저장" in HTML
    assert "외부 연결" in HTML
    assert "내 기록" in HTML
    assert "참고 폴더" in HTML
    assert "결과 저장 폴더" in HTML
    assert "프로젝트는 대화와 결과" in HTML
    assert "현재 상태를 먼저 확인" in HTML


def test_model_flow_tests_exact_draft_before_apply_and_requires_new_destination_key():
    assert "api('/api/model/test',value)" in APP
    assert "modelGuard.test" in APP
    assert "modelGuard.apply" in APP
    assert "credential_revision" in APP
    assert "apply-model" in HTML
    assert "require_key" in APP


def test_refresh_does_not_replace_active_editing_surfaces():
    assert "contextDraftDirty" in APP
    assert "if(!contextDraftDirty" in APP
    assert "if(!modelLoaded)" in APP


def test_mobile_checkbox_is_not_full_width_input():
    assert ".check-row input{width:auto" in CSS
    assert "@media(max-width:620px)" in CSS


def test_owner_flow_has_three_management_destinations_and_optional_projects():
    for destination in ('data-view="tasks"', 'data-view="records"', 'data-view="settings"'):
        assert HTML.count(destination) == 1
    assert 'id="chat-form"' not in HTML
    assert 'id="projects"' in HTML
    assert "setup-checklist" not in APP


def test_guidance_preserves_observed_progress_and_ai_state_boundaries():
    assert "관찰된 과정" in APP
    assert "결과 정보 없음" in APP
    assert "모델 정보 미제공" in APP
    assert "실제 실행은 작업에서 확인" in APP


def test_records_surface_each_owner_record_type():
    for label in ("메모", "기억", "임시 자료", "저장된 결과"):
        assert label in APP
    assert "recordItems" in APP
    assert "deleteKind:'results'" in APP
