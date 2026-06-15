"""Summarize accepted events and hand them to the openclaw gateway."""

import logging

import httpx

log = logging.getLogger("github-hooks")


def build_summary(event: str, payload: dict, delivery_id: str) -> dict:
    repo = (payload.get("repository") or {}).get("full_name", "")
    sender = ((payload.get("sender") or {}).get("login")) or ""
    summary = {
        "event": event,
        "action": payload.get("action"),
        "repo": repo,
        "sender": sender,
        "delivery_id": delivery_id,
        "number": None,
        "title": None,
        "url": None,
        "head_sha": None,
        "conclusion": None,
    }
    pr = payload.get("pull_request")
    if pr:
        summary.update(
            number=pr.get("number"),
            title=pr.get("title"),
            url=pr.get("html_url"),
            head_sha=(pr.get("head") or {}).get("sha"),
        )
    run = payload.get("workflow_run")
    if run:
        summary.update(
            title=run.get("name"),
            url=run.get("html_url"),
            head_sha=run.get("head_sha"),
            conclusion=run.get("conclusion"),
        )
    suite = payload.get("check_suite")
    if suite:
        prs = suite.get("pull_requests") or []
        summary.update(
            head_sha=suite.get("head_sha"),
            conclusion=suite.get("conclusion"),
            number=prs[0].get("number") if prs else None,
        )
    return summary


def build_message(summary: dict) -> str:
    parts = [f"GitHub {summary['event']}.{summary['action']}", summary["repo"]]
    if summary["number"]:
        parts.append(f"#{summary['number']}")
    if summary["title"]:
        parts.append(f"'{summary['title']}'")
    if summary["conclusion"]:
        parts.append(f"conclusion={summary['conclusion']}")
    if summary["head_sha"]:
        parts.append(f"@{summary['head_sha'][:7]}")
    if summary["sender"]:
        parts.append(f"by {summary['sender']}")
    if summary["url"]:
        parts.append(f"— {summary['url']}")
    return " ".join(str(p) for p in parts)


class Forwarder:
    def __init__(self, mode: str, url: str, token: str,
                 agent_id: str = "", model: str = ""):
        self.mode = mode
        self.url = url
        self.token = token
        self.agent_id = agent_id
        self.model = model

    def forward(self, summary: dict) -> bool:
        message = build_message(summary)
        if self.mode != "openclaw":
            log.info("FORWARD(log-only): %s", message)
            return True
        body = {"message": message, "name": "github"}
        if self.agent_id:
            body["agentId"] = self.agent_id
        if self.model:
            body["model"] = self.model
        try:
            resp = httpx.post(
                self.url,
                json=body,
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=5.0,
            )
            resp.raise_for_status()
            log.info("FORWARD(openclaw %s): %s", resp.status_code, message)
            return True
        except httpx.HTTPError as exc:
            log.error("forward failed: %s — %s", exc, message)
            return False
