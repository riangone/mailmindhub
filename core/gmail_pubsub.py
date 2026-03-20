"""
core/gmail_pubsub.py — Gmail Push Notifications via Google Cloud Pub/Sub.

Flow:
  Gmail → Pub/Sub topic → HTTPS push subscription → /webhook/gmail (webui/server.py)
  → historyId → Gmail API history.list() → fetch new messages → process_email()

Setup (one-time):
  1. Enable Gmail API + Pub/Sub API in your GCP project
  2. Create a Pub/Sub topic:
       gcloud pubsub topics create mailmind-gmail
  3. Grant publish permission to Gmail service account:
       gcloud pubsub topics add-iam-policy-binding mailmind-gmail \
         --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
         --role="roles/pubsub.publisher"
  4. Create a push subscription pointing to your webhook:
       gcloud pubsub subscriptions create mailmind-sub \
         --topic=mailmind-gmail \
         --push-endpoint=https://YOUR_HOST/webhook/gmail \
         --ack-deadline=30
  5. Run Gmail OAuth auth first:
       python3 email_daemon.py --mailbox gmail --auth
  6. Set env vars (see below) and start with --gmail-push flag

Environment:
  GMAIL_PUBSUB_TOPIC   — Full topic name, e.g. projects/my-project/topics/mailmind-gmail
  GMAIL_PUSH_ENDPOINT  — Public URL for the webhook (defaults to UNSUBSCRIBE_BASE_URL/webhook/gmail)

The watch expires after 7 days; call gmail_watch() periodically to renew.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("mailmindhub")

_ROOT = Path(__file__).parent.parent
_TOPIC = os.environ.get("GMAIL_PUBSUB_TOPIC", "")
_PUSH_ENDPOINT = os.environ.get("GMAIL_PUSH_ENDPOINT", "") or (
    (os.environ.get("UNSUBSCRIBE_BASE_URL", "").rstrip("/") + "/webhook/gmail")
    if os.environ.get("UNSUBSCRIBE_BASE_URL") else ""
)

_GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

_HISTORY_ID_FILE_TPL = str(_ROOT / "history_id_{mailbox}.json")


# ─── OAuth helpers ────────────────────────────────────────────────────────────

def _build_gmail_service(mailbox: dict):
    """Build an authenticated Gmail API service object."""
    try:
        from googleapiclient.discovery import build  # type: ignore
        import google.oauth2.credentials  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
    except ImportError:
        raise RuntimeError(
            "google-api-python-client is required for Gmail Push. "
            "Install with: pip install google-api-python-client google-auth google-auth-httplib2"
        )

    token_file = mailbox.get("oauth_token_file", str(_ROOT / "token_gmail.json"))
    if not os.path.exists(token_file):
        raise RuntimeError(
            f"Gmail OAuth token not found at {token_file}. "
            "Run: python3 email_daemon.py --mailbox gmail --auth"
        )

    with open(token_file) as f:
        token_data = json.load(f)

    creds = google.oauth2.credentials.Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=token_data.get("client_id"),
        client_secret=token_data.get("client_secret"),
        scopes=_GMAIL_SCOPES,
    )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            # Persist refreshed token
            token_data["token"] = creds.token
            with open(token_file, "w") as f:
                json.dump(token_data, f)
        except Exception as e:
            log.warning(f"[GmailPush] Token refresh failed: {e}")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ─── Watch registration ────────────────────────────────────────────────────────

def gmail_watch(mailbox: dict, topic_name: str = "") -> dict:
    """
    Register Gmail Push Notifications via users.watch().
    Returns {"historyId": ..., "expiration": ...}.
    Must be called at startup and renewed every ~6 days (expires after 7 days).
    """
    topic = topic_name or _TOPIC
    if not topic:
        raise ValueError(
            "GMAIL_PUBSUB_TOPIC is not set. "
            "Example: projects/my-project/topics/mailmind-gmail"
        )

    service = _build_gmail_service(mailbox)
    try:
        result = service.users().watch(userId="me", body={
            "topicName": topic,
            "labelIds": ["INBOX"],
            "labelFilterBehavior": "INCLUDE",
        }).execute()
        log.info(f"[GmailPush] Watch registered. historyId={result.get('historyId')}, "
                 f"expires={result.get('expiration')}")
        return result
    except Exception as e:
        log.error(f"[GmailPush] watch() failed: {e}")
        raise


def gmail_stop_watch(mailbox: dict):
    """Cancel Gmail Push Notifications."""
    service = _build_gmail_service(mailbox)
    try:
        service.users().stop(userId="me").execute()
        log.info("[GmailPush] Watch cancelled.")
    except Exception as e:
        log.warning(f"[GmailPush] stop() failed: {e}")


# ─── History fetch ─────────────────────────────────────────────────────────────

def gmail_fetch_history(mailbox: dict, start_history_id: str) -> list[str]:
    """
    Fetch new message IDs since start_history_id via users.history.list().
    Returns list of Gmail message ID strings (not IMAP UIDs).
    """
    service = _build_gmail_service(mailbox)
    message_ids = []
    try:
        response = service.users().history().list(
            userId="me",
            startHistoryId=start_history_id,
            historyTypes=["messageAdded"],
            labelId="INBOX",
        ).execute()

        for record in response.get("history", []):
            for added in record.get("messagesAdded", []):
                msg_id = added.get("message", {}).get("id")
                if msg_id and msg_id not in message_ids:
                    message_ids.append(msg_id)

        log.debug(f"[GmailPush] history.list found {len(message_ids)} new messages")
    except Exception as e:
        # historyId may be too old — caller should fall back to full fetch
        log.warning(f"[GmailPush] history.list failed (historyId={start_history_id}): {e}")

    return message_ids


def gmail_get_message(mailbox: dict, message_id: str) -> Optional[dict]:
    """
    Fetch a single message via Gmail API and normalize it to the standard em dict.
    Returns None on failure.
    """
    import base64
    from email import message_from_bytes

    service = _build_gmail_service(mailbox)
    try:
        raw = service.users().messages().get(
            userId="me", id=message_id, format="raw"
        ).execute()
    except Exception as e:
        log.warning(f"[GmailPush] messages.get({message_id}) failed: {e}")
        return None

    raw_bytes = base64.urlsafe_b64decode(raw.get("raw", "") + "==")
    msg = message_from_bytes(raw_bytes)

    # Decode header helper
    from email.header import decode_header as _dh

    def _decode_header(s: str) -> str:
        if not s:
            return ""
        parts = _dh(s)
        out = []
        for part, charset in parts:
            if isinstance(part, bytes):
                out.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(str(part))
        return "".join(out)

    # Extract body
    body = ""
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if ct == "text/plain" and "attachment" not in cd:
                try:
                    body += part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", errors="replace"
                    )
                except Exception:
                    pass
            elif "attachment" in cd:
                attachments.append({
                    "filename": part.get_filename() or "attachment",
                    "content": part.get_payload(decode=True) or b"",
                    "is_text": ct.startswith("text/"),
                })
    else:
        try:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", errors="replace"
            )
        except Exception:
            body = ""

    from email.utils import parseaddr
    from_raw = _decode_header(msg.get("From", ""))
    from_name, from_email = parseaddr(from_raw)

    uid = f"gmail_api:{message_id}"
    return {
        "id":          uid,
        "from":        from_name or from_email,
        "from_email":  from_email,
        "subject":     _decode_header(msg.get("Subject", "(no subject)")),
        "body":        body,
        "attachments": attachments,
        "message_id":  msg.get("Message-ID", uid),
        "in_reply_to": msg.get("In-Reply-To", ""),
        "references":  msg.get("References", ""),
    }


# ─── historyId persistence ─────────────────────────────────────────────────────

def store_history_id(mailbox_name: str, history_id: str):
    """Persist the latest historyId to disk."""
    path = _HISTORY_ID_FILE_TPL.format(mailbox=mailbox_name)
    with open(path, "w") as f:
        json.dump({"history_id": history_id, "updated_at": datetime.now().isoformat()}, f)


def load_history_id(mailbox_name: str) -> Optional[str]:
    """Load the persisted historyId. Returns None if not found."""
    path = _HISTORY_ID_FILE_TPL.format(mailbox=mailbox_name)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f).get("history_id")
    except Exception:
        return None
