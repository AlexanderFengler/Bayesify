"""The contact form is unavailable (503) unless a Resend key AND a recipient are configured —
the recipient has no default, so a fresh deploy never mails anyone by accident."""

from fastapi.testclient import TestClient

from bayesify.api.app import app

MSG = {"name": "Ada", "email": "ada@example.com", "message": "hello"}


def test_contact_disabled_without_recipient(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.delenv("CONTACT_TO_EMAIL", raising=False)
    assert TestClient(app).post("/api/contact", json=MSG).status_code == 503


def test_contact_disabled_without_provider(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("CONTACT_TO_EMAIL", "team@example.com")
    assert TestClient(app).post("/api/contact", json=MSG).status_code == 503
