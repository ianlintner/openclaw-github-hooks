from openclaw_github_hooks.filters import Decision, evaluate, repo_allowed

ALLOW = ["ianlintner/caretaker-qa"]


def _pr_payload(repo="ianlintner/caretaker-qa", sender="ianlintner", draft=False, action="opened"):
    return {
        "action": action,
        "repository": {"full_name": repo},
        "sender": {"login": sender},
        "pull_request": {"number": 5, "title": "t", "html_url": "u", "draft": draft,
                         "head": {"sha": "abc1234", "ref": "feat/x"}, "base": {"ref": "main"}},
    }


def test_repo_allowed_exact_and_wildcard():
    assert repo_allowed("ianlintner/caretaker-qa", ["ianlintner/caretaker-qa"]) is True
    assert repo_allowed("ianlintner/anything", ["ianlintner/*"]) is True
    assert repo_allowed("someoneelse/repo", ["ianlintner/*"]) is False


def test_empty_allowlist_fails_closed():
    assert repo_allowed("ianlintner/caretaker-qa", []) is False


def test_ping_never_forwards():
    d = evaluate("ping", {"zen": "x"}, ALLOW)
    assert d.forward is False and d.reason == "ping"


def test_pr_opened_on_allowed_repo_forwards():
    d = evaluate("pull_request", _pr_payload(), ALLOW)
    assert d.forward is True


def test_unlisted_repo_drops():
    d = evaluate("pull_request", _pr_payload(repo="ianlintner/other"), ALLOW)
    assert d.forward is False and d.reason.startswith("repo-not-allowed")


def test_bot_sender_drops():
    d = evaluate("pull_request", _pr_payload(sender="dependabot[bot]"), ALLOW)
    assert d.forward is False and d.reason.startswith("bot-sender")


def test_unlisted_event_drops():
    d = evaluate("star", {"repository": {"full_name": ALLOW[0]}, "sender": {"login": "x"}}, ALLOW)
    assert d.forward is False and d.reason.startswith("event-not-allowed")


def test_unlisted_action_drops():
    d = evaluate("pull_request", _pr_payload(action="labeled"), ALLOW)
    assert d.forward is False and d.reason.startswith("action-not-allowed")


def test_draft_pr_drops():
    d = evaluate("pull_request", _pr_payload(draft=True), ALLOW)
    assert d.forward is False and d.reason == "draft-pr"
