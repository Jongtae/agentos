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
