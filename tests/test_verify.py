import hashlib
import hmac

from openclaw_github_hooks.verify import verify_signature

SECRET = "test-secret"
BODY = b'{"zen": "Design for failure."}'


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_passes():
    assert verify_signature(BODY, SECRET, _sign(BODY, SECRET)) is True


def test_wrong_secret_fails():
    assert verify_signature(BODY, SECRET, _sign(BODY, "other-secret")) is False


def test_tampered_body_fails():
    assert verify_signature(b"{}", SECRET, _sign(BODY, SECRET)) is False


def test_missing_header_fails():
    assert verify_signature(BODY, SECRET, None) is False


def test_wrong_prefix_fails():
    sig = _sign(BODY, SECRET).replace("sha256=", "sha1=")
    assert verify_signature(BODY, SECRET, sig) is False
