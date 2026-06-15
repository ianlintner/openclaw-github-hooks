"""Metrics and tracing for the github-hooks sidecar.

Both Prometheus metrics and OpenTelemetry tracing are optional and degrade
gracefully: if the libraries aren't installed (e.g. minimal test env) or the
OTLP endpoint isn't configured, the helpers become no-ops so the core webhook
path always works.
"""

import logging
import os

log = logging.getLogger("github-hooks")

# --- Prometheus metrics (optional) -----------------------------------------
try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

    _PROM = True
    deliveries_total = Counter(
        "github_hooks_deliveries_total",
        "Webhook deliveries received, labelled by outcome and event type.",
        ["outcome", "event"],
    )
    processing_seconds = Histogram(
        "github_hooks_processing_seconds",
        "Time spent handling a webhook delivery.",
        ["outcome"],
    )
except Exception:  # pragma: no cover - exercised only when dep is missing
    _PROM = False
    CONTENT_TYPE_LATEST = "text/plain"

    class _NoopMetric:
        def labels(self, *_, **__):
            return self

        def inc(self, *_):
            pass

        def observe(self, *_):
            pass

    deliveries_total = _NoopMetric()
    processing_seconds = _NoopMetric()


def record(outcome: str, event: str, elapsed: float) -> None:
    """Increment delivery counters for one handled webhook."""
    deliveries_total.labels(outcome=outcome, event=event or "none").inc()
    processing_seconds.labels(outcome=outcome).observe(elapsed)


def metrics_response():
    """Return (body, content_type) for the /metrics endpoint."""
    if not _PROM:
        return b"# prometheus_client not installed\n", CONTENT_TYPE_LATEST
    return generate_latest(), CONTENT_TYPE_LATEST


# --- OpenTelemetry tracing (optional) --------------------------------------
def setup_tracing(app) -> bool:
    """Wire OTLP tracing onto the FastAPI app if an endpoint is configured.

    Returns True if tracing was enabled. Controlled by OTEL_EXPORTER_OTLP_ENDPOINT
    (matches the cluster convention used by other services).
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return False
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        service_name = os.environ.get("OTEL_SERVICE_NAME", "github-hooks")
        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        FastAPIInstrumentor.instrument_app(app)
        log.info("OpenTelemetry tracing enabled -> %s (service=%s)", endpoint, service_name)
        return True
    except Exception as exc:  # pragma: no cover - depends on optional deps
        log.warning("tracing setup failed (%s); continuing without tracing", exc)
        return False


def tracer():
    """Return an OTel tracer, or None if tracing isn't available."""
    try:
        from opentelemetry import trace

        return trace.get_tracer("github-hooks")
    except Exception:  # pragma: no cover
        return None
