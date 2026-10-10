from pathlib import Path


ROOT = Path(__file__).parents[1]
SITE = ROOT / "site"
PAGES = ("index.html", "install.html", "privacy.html", "terms.html")


def test_static_site_has_required_bilingual_pages_and_navigation():
    for page in PAGES:
        text = (SITE / page).read_text(encoding="utf-8")
        assert 'lang="en"' in text
        assert 'lang="ko"' in text
        assert 'viewport' in text
        # The homepage has its own stylesheet; the policy pages share site.css.
        assert 'assets/home.css' in text if page == "index.html" else 'assets/site.css' in text
    home = (SITE / "index.html").read_text(encoding="utf-8")
    for page in PAGES[1:]:
        assert f'href="{page}"' in home


def test_static_site_never_becomes_an_oauth_or_secret_relay():
    text = "\n".join((SITE / page).read_text(encoding="utf-8") for page in PAGES).lower()
    assert "<form" not in text
    assert "<script" not in text
    assert "oauth callback" in text
    assert "token broker" in text
    assert "drive proxy" in text
    assert "client_secret" not in text
    assert "pkce verifier" not in text


def test_pages_deployment_is_manual_until_operator_details_are_confirmed():
    workflow = (ROOT / ".github/workflows/deploy-pages.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "path: site" in workflow


def test_privacy_page_explains_separate_local_deletion_and_provider_revocation():
    privacy = (SITE / "privacy.html").read_text(encoding="utf-8")
    assert "Delete local data and revoke access" in privacy
    assert "operating system’s file-management tools" in privacy
    assert "provider revocation are separate actions" in privacy
    assert "로컬 삭제와 제공자 권한 철회는 서로 다른 작업" in privacy
