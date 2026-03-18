"""
one_click_unsubscribe.py — RFC 8058 one-click List-Unsubscribe support.

When MailMindHub sends scheduled/recurring emails (news digests, reminders, etc.),
it embeds signed List-Unsubscribe and List-Unsubscribe-Post headers so that
compliant email clients (Gmail, Outlook, Apple Mail, etc.) display a native
one-click "Unsubscribe" button.

The token encodes (task_id, recipient) and is HMAC-signed with UNSUBSCRIBE_SECRET
to prevent tampering.  The Web UI's FastAPI server exposes the POST endpoint that
email clients call when the user clicks the button.

Environment variables:
    UNSUBSCRIBE_BASE_URL   — Public HTTPS URL of the Web UI, e.g.
                             https://mailmind.example.com
                             If empty, List-Unsubscribe headers are omitted.
    UNSUBSCRIBE_SECRET     — HMAC secret (auto-generated and cached in
                             .unsubscribe_secret if not set).
"""

import hashlib
import hmac
import json
import os
import time
import base64
from typing import Optional

from utils.logger import log

# ─── Secret key ──────────────────────────────────────────────────────────────

_SECRET_FILE = os.path.join(os.path.dirname(__file__), "..", ".unsubscribe_secret")


def _load_secret() -> bytes:
    """Return the HMAC secret, generating and persisting it on first use."""
    env_secret = os.environ.get("UNSUBSCRIBE_SECRET", "").strip()
    if env_secret:
        return env_secret.encode()

    if os.path.isfile(_SECRET_FILE):
        try:
            with open(_SECRET_FILE, "rb") as f:
                secret = f.read().strip()
            if secret:
                return secret
        except Exception:
            pass

    # Generate a new random secret and persist it
    secret = base64.urlsafe_b64encode(os.urandom(32))
    try:
        with open(_SECRET_FILE, "wb") as f:
            f.write(secret)
        os.chmod(_SECRET_FILE, 0o600)
    except Exception as e:
        log.warning(f"无法保存 unsubscribe secret: {e}")
    return secret


_SECRET: bytes = _load_secret()

# ─── Base URL ─────────────────────────────────────────────────────────────────

UNSUBSCRIBE_BASE_URL: str = os.environ.get("UNSUBSCRIBE_BASE_URL", "").rstrip("/")

# ─── Token helpers ────────────────────────────────────────────────────────────

_TOKEN_VERSION = "1"
_TOKEN_TTL = 365 * 24 * 3600  # tokens valid for 1 year


def make_token(task_id: int, recipient: str) -> str:
    """Generate a signed, URL-safe token encoding task_id and recipient."""
    payload = json.dumps(
        {"v": _TOKEN_VERSION, "t": task_id, "r": recipient, "ts": int(time.time())},
        separators=(",", ":"),
    )
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    sig = hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    """
    Verify and decode a token.

    Returns the decoded payload dict on success, or None if invalid/expired.
    Payload keys: v, t (task_id), r (recipient), ts (issued-at epoch).
    """
    try:
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return None
        payload_b64, sig = parts

        expected_sig = hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None

        # Restore padding for base64 decoding
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload = json.loads(base64.urlsafe_b64decode(payload_b64).decode())

        if payload.get("v") != _TOKEN_VERSION:
            return None
        if time.time() - payload.get("ts", 0) > _TOKEN_TTL:
            log.warning(f"unsubscribe token 已过期 (task_id={payload.get('t')})")
            return None

        return payload
    except Exception as e:
        log.warning(f"unsubscribe token 解码失败: {e}")
        return None


def unsubscribe_url(task_id: int, recipient: str) -> Optional[str]:
    """Return the one-click unsubscribe URL, or None if base URL not configured."""
    if not UNSUBSCRIBE_BASE_URL:
        return None
    token = make_token(task_id, recipient)
    return f"{UNSUBSCRIBE_BASE_URL}/unsubscribe?token={token}"


def list_unsubscribe_headers(task_id: int, recipient: str) -> dict:
    """
    Build the List-Unsubscribe and List-Unsubscribe-Post headers for a message.

    Returns an empty dict if UNSUBSCRIBE_BASE_URL is not configured.

    Per RFC 2369 / RFC 8058:
      List-Unsubscribe: <https://...>
      List-Unsubscribe-Post: List-Unsubscribe=One-Click
    """
    url = unsubscribe_url(task_id, recipient)
    if not url:
        return {}
    return {
        "List-Unsubscribe": f"<{url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }
