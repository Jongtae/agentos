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
    assert "Confirm ${preview.id}" in APP  # internal API text remains unreachable as primary IA


def test_model_flow_tests_exact_draft_before_apply_and_requires_new_destination_key():
    assert "api('/api/model/test',draft)" in APP
    assert "modelDraftVerified!==modelDraftFingerprint(draft)" in APP
    assert "apply-model" in HTML
    assert "require_key" in APP


def test_refresh_does_not_replace_active_editing_surfaces():
    assert "contextDraftDirty" in APP
    assert "conversationSettingsFingerprint" in APP
    assert "if(settingsFingerprint!==conversationSettingsFingerprint)" in APP
    assert "if(!contextDraftDirty" in APP


def test_mobile_checkbox_is_not_full_width_input():
    assert ".check-row input[type=checkbox]{width:auto" in CSS
    assert "@media(max-width:520px)" in CSS


def test_owner_flow_has_five_destinations_and_three_step_first_use_path():
    assert "renderOwnerFlow" in APP
    for label in ("대화", "작업 현황", "내 기록", "프로젝트", "설정"):
        assert label in APP
    for label in ("AI 연결", "파일 위치 설정", "첫 요청 실행"):
        assert label in APP
    assert "home.model_connected" in APP
    assert "state.settings.file_workspace" in APP
    assert "home.conversation?.length" in APP


def test_guidance_preserves_observed_progress_and_ai_state_boundaries():
    assert "관찰된 과정" in APP
    assert "예상 시간은 추정하지 않고" in APP
    assert "저장된 설정" in APP
    assert "테스트한 설정" in APP
    assert "최근 응답 모델" in APP


def test_records_surface_each_owner_record_type():
    for label in ("메모", "기억", "임시 자료", "저장된 결과", "활동 기록"):
        assert label in APP
    assert "showRecordCategories" in APP
    assert "space.result_count" in APP
