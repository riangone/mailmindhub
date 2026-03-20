"""
channels/loader.py — Auto-discover and return enabled channel adapters.

A channel is enabled if its required environment variable is set.
"""

import os
import logging
from channels import BaseChannel

log = logging.getLogger("mailmindhub")


def get_enabled_channels() -> list[BaseChannel]:
    """Return list of configured and enabled channel adapters."""
    channels = []

    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        try:
            from channels.telegram_adapter import CHANNEL as tg
            channels.append(tg)
            log.info("[Channels] Telegram channel enabled")
        except Exception as e:
            log.warning(f"[Channels] Failed to load Telegram adapter: {e}")

    if os.environ.get("DISCORD_BOT_TOKEN"):
        try:
            from channels.discord_adapter import CHANNEL as dc
            channels.append(dc)
            log.info("[Channels] Discord channel enabled")
        except Exception as e:
            log.warning(f"[Channels] Failed to load Discord adapter: {e}")

    return channels
