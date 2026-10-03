"""Suite-wide guards."""
import pytest


@pytest.fixture(autouse=True)
def _no_automatic_phone_login(monkeypatch):
    """#953: a login prompt never starts a real ngrok tunnel in a test; a test that wants it opts in with a fake."""
    from personal_agent import quickstart_service
    monkeypatch.setattr(quickstart_service.AgentService, 'AUTO_PHONE_LOGIN', False)
    monkeypatch.setattr(quickstart_service.AgentService, 'SESSION_KEEPALIVE', False)
