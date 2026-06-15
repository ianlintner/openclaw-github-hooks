"""GitHub webhook HMAC-SHA256 signature verification."""

import hashlib
import hmac


def compute_signature(payload: bytes, secret: str) -> str:
    """Return the X-Hub-Signature-256 value GitHub should send for this body."""
    return "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify_signature(payload: bytes, secret: str, signature_header: str | None) -> bool:
    """Validate the X-Hub-Signature-256 header against the raw request body."""
    if not secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = compute_signature(payload, secret)
    return hmac.compare_digest(expected, signature_header)
