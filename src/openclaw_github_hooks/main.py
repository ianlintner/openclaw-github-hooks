"""FastAPI app: verify -> dedup -> filter -> forward."""

import json
import logging
import os

from fastapi import FastAPI, Request, Response

from .dedup import DeliveryDedup
from .filters import evaluate
from .forwarder import Forwarder, build_summary
from .verify import verify_signature

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
    )
    dedup = DeliveryDedup()
    stats = {
        "received": 0, "bad_signature": 0, "duplicate": 0,
        "filtered": 0, "forwarded": 0, "forward_errors": 0,
    }

    app = FastAPI()

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/stats")
    async def get_stats():
        return stats

    @app.post("/webhooks/github")
    async def github_webhook(request: Request):
        body = await request.body()
        stats["received"] += 1

        if not verify_signature(body, secret, request.headers.get("X-Hub-Signature-256")):
            stats["bad_signature"] += 1
            log.warning("rejected delivery with bad signature")
            return Response(status_code=401)

        event = request.headers.get("X-GitHub-Event", "")
        delivery_id = request.headers.get("X-GitHub-Delivery", "")
        payload = json.loads(body or b"{}")

        if delivery_id and dedup.seen_before(delivery_id):
            stats["duplicate"] += 1
            log.info("duplicate delivery %s", delivery_id)
            return {"status": "duplicate"}

        decision = evaluate(event, payload, allowed_repos)
        if not decision.forward:
            stats["filtered"] += 1
            log.info("filtered %s (%s) delivery=%s", event, decision.reason, delivery_id)
            return {"status": "filtered", "reason": decision.reason}

        summary = build_summary(event, payload, delivery_id)
        if forwarder.forward(summary):
            stats["forwarded"] += 1
            return {"status": "forwarded", "reason": decision.reason}
        stats["forward_errors"] += 1
        # 200 anyway: GitHub retries don't help if openclaw is down; dedup would block them.
        return {"status": "forward-error", "reason": decision.reason}

    return app
