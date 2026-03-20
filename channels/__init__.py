"""
channels/ — Messaging channel abstraction for MailMindHub.

Each channel adapter normalizes incoming messages into the same dict shape
that fetch_unread_emails() produces, allowing process_email() to work unchanged.

Message dict shape (same as email_daemon):
  {
    "id":          str,   # unique message ID (channel-prefixed, e.g. "tg:12345")
    "from":        str,   # display name of sender
    "from_email":  str,   # sender identifier (e.g. "tg:chat_id" or "dc:user_id")
    "subject":     str,   # message topic/first line
    "body":        str,   # full message text
    "attachments": list,  # [{"filename": ..., "content": bytes}]
    "message_id":  str,   # same as id, for threading
    "in_reply_to": str,   # parent message id (for reply chains)
    "references":  str,   # space-separated chain of parent ids
    "channel":     str,   # channel name (e.g. "telegram", "discord")
    "_reply_fn":   callable,  # fn(to, subject, body, **kwargs) -> str
  }
"""

from abc import ABC, abstractmethod


class BaseChannel(ABC):
    """Abstract base class for messaging channel adapters."""

    name: str = ""

    @abstractmethod
    def poll_messages(self, processed_ids: set) -> list[dict]:
        """
        Fetch new messages not in processed_ids.
        Returns a list of normalized message dicts.
        """
        ...

    @abstractmethod
    def send_reply(self, to: str, subject: str, body: str,
                   in_reply_to: str = "", **kwargs) -> str:
        """
        Send a reply to the channel.
        Returns a message ID string.
        """
        ...
