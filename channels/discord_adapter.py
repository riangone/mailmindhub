"""
Discord channel adapter for MailMindHub.

Uses Discord REST API v10 via polling (no extra dependencies — pure requests).
For real-time delivery, pair with the /webhook/discord FastAPI endpoint in webui/server.py.

Setup:
  1. Discord Developer Portal → New Application → Bot → Reset Token → copy DISCORD_BOT_TOKEN
  2. Enable "Message Content Intent" under Bot → Privileged Gateway Intents
  3. Invite bot to server with permissions: Read Messages, Send Messages
  4. Set DISCORD_CHANNEL_IDS to the channel IDs to monitor (comma-separated)

Environment:
  DISCORD_BOT_TOKEN    — Bot token (required)
  DISCORD_CHANNEL_IDS  — Comma-separated channel IDs to monitor (required)
  DISCORD_GUILD_ID     — Guild (server) ID (optional, for member lookups)
"""

import os
import logging
from channels import BaseChannel

log = logging.getLogger("mailmindhub")

_TOKEN       = os.environ.get("DISCORD_BOT_TOKEN", "")
_CHANNEL_IDS = [c.strip() for c in os.environ.get("DISCORD_CHANNEL_IDS", "").split(",") if c.strip()]

_API_BASE = "https://discord.com/api/v10"


def _api_get(path: str, params: dict = None):
    import requests
    try:
        r = requests.get(
            f"{_API_BASE}{path}",
            headers={"Authorization": f"Bot {_TOKEN}"},
            params=params,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"[Discord] GET {path} error: {e}")
        return None


def _api_post(path: str, data: dict):
    import requests
    try:
        r = requests.post(
            f"{_API_BASE}{path}",
            headers={"Authorization": f"Bot {_TOKEN}", "Content-Type": "application/json"},
            json=data,
            timeout=15,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning(f"[Discord] POST {path} error: {e}")
        return None


class DiscordChannel(BaseChannel):
    name = "discord"

    def __init__(self):
        # Track last seen message ID per channel for efficient polling
        self._last_ids: dict[str, str] = {}

    def poll_messages(self, processed_ids: set) -> list[dict]:
        if not _TOKEN or not _CHANNEL_IDS:
            return []

        messages = []
        for channel_id in _CHANNEL_IDS:
            params = {"limit": 50}
            after = self._last_ids.get(channel_id)
            if after:
                params["after"] = after

            msgs = _api_get(f"/channels/{channel_id}/messages", params)
            if not msgs:
                continue

            # Discord returns newest-first; reverse for chronological order
            for msg in reversed(msgs):
                msg_id = msg["id"]
                uid    = f"dc:{channel_id}:{msg_id}"

                # Update watermark
                if not after or int(msg_id) > int(self._last_ids.get(channel_id, "0")):
                    self._last_ids[channel_id] = msg_id

                if uid in processed_ids:
                    continue

                # Skip bot messages (avoid loops)
                author = msg.get("author", {})
                if author.get("bot"):
                    continue

                content = msg.get("content", "")
                first_line = content.split("\n")[0][:100]

                # Reply threading
                ref = msg.get("message_reference", {})
                in_reply_to = f"dc:{channel_id}:{ref['message_id']}" if ref.get("message_id") else ""

                attachments = [
                    {"filename": a.get("filename", "attachment"), "content": b"", "url": a.get("url")}
                    for a in msg.get("attachments", [])
                ]

                from_name  = author.get("username", "Discord User")
                from_ident = f"dc:{author.get('id', 'unknown')}"

                messages.append({
                    "id":          uid,
                    "from":        from_name,
                    "from_email":  from_ident,
                    "subject":     first_line or "(Discord message)",
                    "body":        content,
                    "attachments": attachments,
                    "message_id":  uid,
                    "in_reply_to": in_reply_to,
                    "references":  in_reply_to,
                    "channel":     "discord",
                    "_reply_fn":   _make_reply_fn(channel_id, msg_id),
                })

        return messages

    def send_reply(self, to: str, subject: str, body: str,
                   in_reply_to: str = "", **kwargs) -> str:
        # to format: "dc:<user_id>" — find the channel from context
        # In practice, replies use _reply_fn; this handles explicit sends
        if not _CHANNEL_IDS:
            return ""

        full_text = f"**{subject}**\n\n{body}" if subject else body
        full_text = full_text[:2000]  # Discord message limit

        result = _api_post(f"/channels/{_CHANNEL_IDS[0]}/messages", {"content": full_text})
        if result:
            return f"dc:{_CHANNEL_IDS[0]}:{result['id']}"
        return ""


def _make_reply_fn(channel_id: str, msg_id: str):
    def _fn(to: str, subject: str, body: str, in_reply_to: str = "", **kwargs) -> str:
        full_text = f"**{subject}**\n\n{body}" if subject else body
        full_text = full_text[:2000]
        result = _api_post(
            f"/channels/{channel_id}/messages",
            {
                "content":           full_text,
                "message_reference": {"message_id": msg_id, "channel_id": channel_id},
            },
        )
        if result:
            return f"dc:{channel_id}:{result['id']}"
        return ""
    return _fn


CHANNEL = DiscordChannel()
