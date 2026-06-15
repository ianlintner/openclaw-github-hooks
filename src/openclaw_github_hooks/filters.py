"""Decide which webhook deliveries are worth waking the agent for."""

from dataclasses import dataclass

# event -> allowed actions (empty set = any action / no action field)
DEFAULT_ALLOWED_EVENTS: dict[str, set[str]] = {
    "pull_request": {"opened", "reopened", "synchronize", "ready_for_review"},
    "pull_request_review": {"submitted"},
    "check_suite": {"completed"},
    "workflow_run": {"completed"},
}


@dataclass
class Decision:
    forward: bool
    reason: str


def repo_allowed(full_name: str, patterns: list[str]) -> bool:
    """Exact `owner/repo` or `owner/*` wildcard match. Empty patterns = fail closed."""
    full_name = full_name.lower()
    for pattern in patterns:
        pattern = pattern.lower()
        if pattern == full_name:
            return True
        if pattern.endswith("/*") and full_name.split("/")[0] == pattern[:-2]:
            return True
    return False


def evaluate(
    event: str,
    payload: dict,
    allowed_repos: list[str],
    allowed_events: dict[str, set[str]] | None = None,
) -> Decision:
    allowed_events = allowed_events if allowed_events is not None else DEFAULT_ALLOWED_EVENTS

    if event == "ping":
        return Decision(False, "ping")

    repo = (payload.get("repository") or {}).get("full_name", "")
    if not repo_allowed(repo, allowed_repos):
        return Decision(False, f"repo-not-allowed:{repo or 'unknown'}")

    # CI-outcome events must reach the agent even when its own bot push triggered
    # them; only drop bot-authored PR/review/comment noise (its own edits).
    sender = ((payload.get("sender") or {}).get("login")) or ""
    BOT_DROP_EVENTS = {"pull_request", "pull_request_review", "issue_comment"}
    if sender.endswith("[bot]") and event in BOT_DROP_EVENTS:
        return Decision(False, f"bot-sender:{sender}")

    if event not in allowed_events:
        return Decision(False, f"event-not-allowed:{event}")

    action = payload.get("action")
    allowed_actions = allowed_events[event]
    if allowed_actions and action not in allowed_actions:
        return Decision(False, f"action-not-allowed:{event}.{action}")

    pr = payload.get("pull_request")
    if event == "pull_request" and pr and pr.get("draft"):
        return Decision(False, "draft-pr")

    return Decision(True, f"{event}.{action or 'n/a'}")
