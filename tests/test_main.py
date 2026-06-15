import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from openclaw_github_hooks.main import create_app

SECRET = "test-secret"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("GH_HOOKS_ALLOWED_REPOS", "ianlintner/caretaker-qa")
    monkeypatch.setenv("GH_HOOKS_FORWARD_MODE", "log")
    return TestClient(create_app())


def _post(client, event, payload, delivery="d-1", secret=SECRET):
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/github",
        content=body,
        headers={
            "X-GitHub-Event": event,
            "X-GitHub-Delivery": delivery,
            "X-Hub-Signature-256": sig,
            "Content-Type": "application/json",
        },
    )


def _pr_payload():
    return {
        "action": "opened",
        "repository": {"full_name": "ianlintner/caretaker-qa"},
        "sender": {"login": "ianlintner"},
        "pull_request": {"number": 5, "title": "t", "html_url": "u", "draft": False,
                         "head": {"sha": "abc1234", "ref": "f"}, "base": {"ref": "main"}},
    }


def test_healthz(client):
    assert client.get("/healthz").status_code == 200


def test_bad_signature_is_401(client):
    r = _post(client, "pull_request", _pr_payload(), secret="wrong")
    assert r.status_code == 401


def test_ping_is_200_filtered(client):
    r = _post(client, "ping", {"zen": "x"})
    assert r.status_code == 200
    assert r.json()["status"] == "filtered"


def test_pr_opened_forwards(client):
    r = _post(client, "pull_request", _pr_payload())
    assert r.status_code == 200
    assert r.json()["status"] == "forwarded"


def test_duplicate_delivery_skipped(client):
    _post(client, "pull_request", _pr_payload(), delivery="same")
    r = _post(client, "pull_request", _pr_payload(), delivery="same")
    assert r.json()["status"] == "duplicate"


def test_stats_counters(client):
    _post(client, "pull_request", _pr_payload(), delivery="s-1")
    _post(client, "star", {"repository": {"full_name": "ianlintner/caretaker-qa"},
                           "sender": {"login": "x"}}, delivery="s-2")
    stats = client.get("/stats").json()
    assert stats["received"] == 2
    assert stats["forwarded"] == 1
    assert stats["filtered"] == 1


def test_forwarder_built_with_agent_and_model(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("GH_HOOKS_ALLOWED_REPOS", "ianlintner/caretaker-qa")
    monkeypatch.setenv("GH_HOOKS_FORWARD_MODE", "log")
    monkeypatch.setenv("GH_HOOKS_AGENT_ID", "pr-reviewer")
    monkeypatch.setenv("GH_HOOKS_MODEL", "claude-sonnet-4-6")
    import openclaw_github_hooks.main as m
    captured = {}
    real = m.Forwarder
    def _spy(*a, **k):
        captured.update(k)
        return real(*a, **k)
    monkeypatch.setattr(m, "Forwarder", _spy)
    m.create_app()
    assert captured.get("agent_id") == "pr-reviewer"
    assert captured.get("model") == "claude-sonnet-4-6"
