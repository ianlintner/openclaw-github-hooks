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
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
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


def test_metrics_endpoint_serves_prometheus_text(client):
    # generate some traffic first
    _post(client, "ping", {"zen": "x"}, delivery="m-1")
    r = client.get("/metrics")
    assert r.status_code == 200
    assert "github_hooks_deliveries_total" in r.text


def test_metrics_counts_outcomes(client):
    _post(client, "ping", {"zen": "x"}, delivery="m-2")  # filtered
    _post(client, "pull_request", {"repository": {"full_name": "ianlintner/caretaker-qa"},
          "sender": {"login": "x"}}, delivery="m-2")  # duplicate? no, distinct delivery
    text = client.get("/metrics").text
    assert 'outcome="filtered"' in text


def test_bad_signature_diagnostic_logged(client, caplog):
    import logging
    caplog.set_level(logging.WARNING, logger="github-hooks")
    body = json.dumps({"zen": "x"}).encode()
    bad = "sha256=" + hmac.new(b"wrong", body, hashlib.sha256).hexdigest()
    r = client.post("/webhooks/github", content=body, headers={
        "X-GitHub-Event": "ping", "X-GitHub-Delivery": "bad-1",
        "X-Hub-Signature-256": bad, "Content-Type": "application/json",
    })
    assert r.status_code == 401
    # diagnostic line includes body length and both signatures for triage
    msg = "\n".join(rec.message for rec in caplog.records)
    assert "bad signature" in msg
    assert "body_len=" in msg
    assert "sig_computed=" in msg
