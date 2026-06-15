"""FastAPI app: verify -> dedup -> filter -> forward."""

import hashlib
import json
import logging
import os
import time

from fastapi import FastAPI, Request, Response

from .dedup import DeliveryDedup
from .filters import evaluate
from .forwarder import Forwarder, build_summary
from . import observability as obs
from .verify import compute_signature, verify_signature

logging.basicConfig(level=os.environ.get("GH_HOOKS_LOG_LEVEL", "INFO"))
log = logging.getLogger("github-hooks")


def create_app() -> FastAPI:
    secret = os.environ["GITHUB_WEBHOOK_SECRET"]
    allowed_repos = [
        p.strip() for p in os.environ.get("GH_HOOKS_ALLOWED_REPOS", "").split(",") if p.strip()
    ]
    forwarder = Forwarder(
        mode=os.environ.get("GH_HOOKS_FORWARD_MODE", "log"),
        url=os.environ.get("GH_HOOKS_OPENCLAW_URL", "http://127.0.0.1:18789/hooks/agent"),
        token=os.environ.get("GH_HOOKS_OPENCLAW_TOKEN", ""),
        agent_id=os.environ.get("GH_HOOKS_AGENT_ID", ""),
        model=os.environ.get("GH_HOOKS_MODEL", ""),
    )
    dedup = DeliveryDedup()
    stats = {
        "received": 0, "bad_signature": 0, "duplicate": 0,
        "filtered": 0, "forwarded": 0, "forward_errors": 0,
    }

    app = FastAPI()
    obs.setup_tracing(app)

    def finish(outcome: str, event: str, started: float):
        stats[outcome] += 1
        obs.record(outcome, event, time.monotonic() - started)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/stats")
    async def get_stats():
        return stats

    @app.get("/metrics")
    async def metrics():
        body, content_type = obs.metrics_response()
        return Response(content=body, media_type=content_type)

    @app.post("/webhooks/github")
    async def github_webhook(request: Request):
        started = time.monotonic()
        body = await request.body()
        stats["received"] += 1
        event = request.headers.get("X-GitHub-Event", "")
        delivery_id = request.headers.get("X-GitHub-Delivery", "")

        received_sig = request.headers.get("X-Hub-Signature-256")
        if not verify_signature(body, secret, received_sig):
            # Diagnostic: a signature mismatch is almost always (a) a secret that
            # differs between GitHub and this sidecar, or (b) a body altered in
            # transit (length != Content-Length). Log enough to tell them apart
            # without leaking the secret — the signature is a MAC, not the key.
            content_length = request.headers.get("Content-Length", "?")
            computed = compute_signature(body, secret)
            log.warning(
                "bad signature delivery=%s event=%s body_len=%d content_length=%s "
                "body_sha256=%s sig_received=%s sig_computed=%s match_len=%s",
                delivery_id, event, len(body), content_length,
                hashlib.sha256(body).hexdigest()[:12],
                received_sig, computed,
                str(content_length) == str(len(body)),
            )
            finish("bad_signature", event, started)
            return Response(status_code=401)

        payload = json.loads(body or b"{}")

        if delivery_id and dedup.seen_before(delivery_id):
            log.info("duplicate delivery %s", delivery_id)
            finish("duplicate", event, started)
            return {"status": "duplicate"}

        decision = evaluate(event, payload, allowed_repos)
        if not decision.forward:
            log.info("filtered %s (%s) delivery=%s", event, decision.reason, delivery_id)
            finish("filtered", event, started)
            return {"status": "filtered", "reason": decision.reason}

        summary = build_summary(event, payload, delivery_id)
        if forwarder.forward(summary):
            finish("forwarded", event, started)
            return {"status": "forwarded", "reason": decision.reason}
        finish("forward_errors", event, started)
        # 200 anyway: GitHub retries don't help if openclaw is down; dedup would block them.
        return {"status": "forward-error", "reason": decision.reason}

    return app
