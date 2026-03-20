"""
Telegram channel adapter for MailMindHub.

Uses Telegram Bot API via long-polling (no extra dependencies — pure requests).

Setup:
  1. Create a bot via @BotFather → get TELEGRAM_BOT_TOKEN
  2. Start a chat with the bot, send any message
  3. Set TELEGRAM_ALLOWED_CHATS to your chat ID (comma-separated)

Environment:
  TELEGRAM_BOT_TOKEN    — Bot token from @BotFather (required)
  TELEGRAM_ALLOWED_CHATS — Comma-separated chat IDs that are allowed (required)
  TELEGRAM_POLL_TIMEOUT  — Long-poll timeout in seconds (default: 30)
"""

import os
import logging
from channels import BaseChannel

log = logging.getLogger("mailmindhub")

_TOKEN         = os.environ.get("TELEGRAM_BOT_TOKEN", "")
_ALLOWED_RAW   = os.environ.get("TELEGRAM_ALLOWED_CHATS", "")
_POLL_TIMEOUT  = int(os.environ.get("TELEGRAM_POLL_TIMEOUT", "30"))

_ALLOWED_CHATS: set[int] = {
    int(c.strip()) for c in _ALLOWED_RAW.split(",") if c.strip().lstrip("-").isdigit()
}

_API_BASE = f"https://api.telegram.org/bot{_TOKEN}"


def _api(method: str, **kwargs):
    import requests  # already in requirements.txt
    try:
        r = requests.post(f"{_API_BASE}/{method}", json=kwargs, timeout=_POLL_TIMEOUT + 5)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"[Telegram] API error ({method}): {e}")
        return {"ok": False}


class TelegramChannel(BaseChannel):
    name = "telegram"

    def __init__(self):
        self._offset: int = 0

    def poll_messages(self, processed_ids: set) -> list[dict]:
        if not _TOKEN:
            return []

        result = _api("getUpdates", offset=self._offset, timeout=_POLL_TIMEOUT, limit=100)
        if not result.get("ok"):
            return []

        messages = []
        for update in result.get("result", []):
            update_id = update["update_id"]
            self._offset = max(self._offset, update_id + 1)

            msg = update.get("message") or update.get("channel_post")
            if not msg:
                continue

            chat_id  = msg["chat"]["id"]
            msg_id   = msg["message_id"]
            uid      = f"tg:{update_id}"

            if uid in processed_ids:
                continue
            if _ALLOWED_CHATS and chat_id not in _ALLOWED_CHATS:
                log.debug(f"[Telegram] Ignoring message from unauthorized chat {chat_id}")
                continue

            sender    = msg.get("from", {})
            from_name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or "Telegram User"
            text      = msg.get("text") or msg.get("caption") or ""
            first_line = text.split("\n")[0][:100]

            # Handle reply threading
            reply_to_id = ""
            if msg.get("reply_to_message"):
                reply_to_id = f"tg:{msg['reply_to_message']['message_id']}"

            attachments = _extract_attachments(msg)

            messages.append({
                "id":          uid,
                "from":        from_name,
                "from_email":  f"tg:{chat_id}",
                "subject":     first_line or "(Telegram message)",
                "body":        text,
                "attachments": attachments,
                "message_id":  uid,
                "in_reply_to": reply_to_id,
                "references":  reply_to_id,
                "channel":     "telegram",
                "_reply_fn":   _make_reply_fn(chat_id, msg_id),
            })

        return messages

    def send_reply(self, to: str, subject: str, body: str,
                   in_reply_to: str = "", **kwargs) -> str:
        # to format: "tg:<chat_id>"
        chat_id = to.removeprefix("tg:")
        try:
            chat_id_int = int(chat_id)
        except ValueError:
            return ""

        reply_to_msg_id = None
        if in_reply_to:
            # in_reply_to format: "tg:<message_id>"
            raw = in_reply_to.removeprefix("tg:")
            if raw.isdigit():
                reply_to_msg_id = int(raw)

        full_text = f"*{subject}*\n\n{body}" if subject else body
        # Telegram max message length is 4096
        full_text = full_text[:4000]

        params = {
            "chat_id":    chat_id_int,
            "text":       full_text,
            "parse_mode": "Markdown",
        }
        if reply_to_msg_id:
            params["reply_to_message_id"] = reply_to_msg_id

        result = _api("sendMessage", **params)
        if result.get("ok"):
            new_id = result["result"]["message_id"]
            return f"tg:{new_id}"
        return ""


def _make_reply_fn(chat_id: int, msg_id: int):
    def _fn(to: str, subject: str, body: str, in_reply_to: str = "", **kwargs) -> str:
        full_text = f"*{subject}*\n\n{body}" if subject else body
        full_text = full_text[:4000]
        result = _api("sendMessage",
                      chat_id=chat_id,
                      text=full_text,
                      parse_mode="Markdown",
                      reply_to_message_id=msg_id)
        if result.get("ok"):
            return f"tg:{result['result']['message_id']}"
        return ""
    return _fn


def _extract_attachments(msg: dict) -> list:
    attachments = []
    # Document
    doc = msg.get("document")
    if doc:
        attachments.append({
            "filename": doc.get("file_name", "attachment"),
            "content":  b"",  # lazy: fetch via getFile if needed
            "file_id":  doc.get("file_id"),
        })
    # Photo (largest size)
    photos = msg.get("photo")
    if photos:
        largest = max(photos, key=lambda p: p.get("file_size", 0))
        attachments.append({
            "filename": "photo.jpg",
            "content":  b"",
            "file_id":  largest.get("file_id"),
        })
    return attachments


CHANNEL = TelegramChannel()
