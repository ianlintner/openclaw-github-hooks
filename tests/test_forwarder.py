from openclaw_github_hooks.forwarder import Forwarder, build_message, build_summary


def test_build_summary_pull_request():
    payload = {
        "action": "opened",
        "repository": {"full_name": "ianlintner/caretaker-qa"},
        "sender": {"login": "ianlintner"},
        "pull_request": {"number": 5, "title": "Fix bug", "html_url": "https://x/pull/5",
                         "draft": False, "head": {"sha": "abc1234def", "ref": "feat/x"},
                         "base": {"ref": "main"}},
    }
    s = build_summary("pull_request", payload, "deliv-1")
    assert s["repo"] == "ianlintner/caretaker-qa"
    assert s["number"] == 5
    assert s["url"] == "https://x/pull/5"


def test_build_summary_workflow_run():
    payload = {
        "action": "completed",
        "repository": {"full_name": "ianlintner/caretaker-qa"},
        "sender": {"login": "ianlintner"},
        "workflow_run": {"name": "CI", "conclusion": "failure", "head_sha": "abc1234def",
                         "html_url": "https://x/runs/9"},
    }
    s = build_summary("workflow_run", payload, "deliv-2")
    assert s["conclusion"] == "failure"
    assert "CI" in build_message(s)


def test_log_mode_forward_returns_true_without_network():
    fwd = Forwarder(mode="log", url="http://127.0.0.1:1/hooks/agent", token="t")
    assert fwd.forward({"event": "pull_request", "action": "opened",
                        "repo": "r", "number": 1, "title": "t", "url": "u",
                        "sender": "s", "head_sha": "h", "conclusion": None,
                        "delivery_id": "d"}) is True


def test_openclaw_mode_failure_returns_false():
    # Nothing listens on port 1 — the POST must fail gracefully, not raise.
    fwd = Forwarder(mode="openclaw", url="http://127.0.0.1:1/hooks/agent", token="t")
    assert fwd.forward({"event": "pull_request", "action": "opened",
                        "repo": "r", "number": 1, "title": "t", "url": "u",
                        "sender": "s", "head_sha": "h", "conclusion": None,
                        "delivery_id": "d"}) is False


def test_openclaw_payload_includes_agent_and_model(monkeypatch):
    captured = {}

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass

    def _fake_post(url, json, headers, timeout):
        captured["json"] = json
        return _Resp()

    import openclaw_github_hooks.forwarder as fwd_mod
    monkeypatch.setattr(fwd_mod.httpx, "post", _fake_post)

    fwd = fwd_mod.Forwarder(mode="openclaw", url="http://x/hooks/agent", token="t",
                            agent_id="pr-reviewer", model="claude-sonnet-4-6")
    ok = fwd.forward({"event": "pull_request", "action": "opened", "repo": "r",
                      "number": 1, "title": "t", "url": "u", "sender": "s",
                      "head_sha": "h", "conclusion": None, "delivery_id": "d"})
    assert ok is True
    assert captured["json"]["agentId"] == "pr-reviewer"
    assert captured["json"]["model"] == "claude-sonnet-4-6"
    assert captured["json"]["name"] == "github"
    assert "message" in captured["json"]
