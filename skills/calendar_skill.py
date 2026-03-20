"""
calendar skill — Create or query calendar events.

Backends (in priority order):
  1. Google Calendar API  — requires google-api-python-client + Google OAuth
  2. .ics file generation — no dependencies, always available as fallback

Supported actions:
  create  — Create a new event
  list    — List upcoming events
  ics     — Generate an .ics file (returned as attachment hint)

Environment:
  GOOGLE_CALENDAR_ID  — Calendar ID (default: 'primary')
  CALENDAR_BACKEND    — 'google' or 'ics' (default: auto-detect)
"""

import os
from datetime import datetime, timedelta
from skills import BaseSkill
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider

_CALENDAR_BACKEND = os.environ.get("CALENDAR_BACKEND", "auto")
_GOOGLE_CAL_ID    = os.environ.get("GOOGLE_CALENDAR_ID", "primary")


class CalendarSkill(BaseSkill):
    name = "calendar"
    description = "创建或查询日历事件（Google Calendar / .ics 文件）"
    description_ja = "カレンダーイベントの作成・照会（Google Calendar / .ics ファイル）"
    description_en = "Create or query calendar events (Google Calendar / .ics file output)"
    keywords = ["日历", "calendar", "会议", "提醒", "event", "カレンダー", "일정", "schedule", "meeting", "appointment"]

    def run(self, payload: dict, ai_caller=None) -> str:
        action  = payload.get("action", "create")
        backend = _CALENDAR_BACKEND

        if backend == "auto":
            backend = "google" if _try_google_available() else "ics"

        if backend == "google":
            return _google_calendar_action(payload, action)
        else:
            return _ics_action(payload, action)


def _try_google_available() -> bool:
    try:
        import googleapiclient  # type: ignore  # noqa: F401
        return True
    except ImportError:
        return False


# ── Google Calendar ───────────────────────────────────────────────────────────

def _google_calendar_action(payload: dict, action: str) -> str:
    try:
        from googleapiclient.discovery import build  # type: ignore
        import google.oauth2.credentials  # type: ignore
        import json as _json

        # Reuse existing Gmail OAuth token if available
        token_file = os.path.join(os.path.dirname(__file__), "..", "token_gmail.json")
        if not os.path.exists(token_file):
            return "⚠️ Google Calendar 需要 Google OAuth 认证。请先运行 Gmail OAuth 认证，或设置 CALENDAR_BACKEND=ics"

        with open(token_file) as f:
            token_data = _json.load(f)

        creds = google.oauth2.credentials.Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=token_data.get("client_id"),
            client_secret=token_data.get("client_secret"),
        )
        service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    except ImportError:
        return "⚠️ 未安装 google-api-python-client。请运行：pip install google-api-python-client\n或设置 CALENDAR_BACKEND=ics 使用 .ics 文件模式。"
    except Exception as e:
        return f"❌ Google Calendar 认证失败：{e}"

    if action == "create":
        title    = payload.get("title") or payload.get("summary", "")
        start    = payload.get("start", "")
        end      = payload.get("end", "")
        location = payload.get("location", "")
        desc     = payload.get("description") or payload.get("body", "")

        if not title or not start:
            return "⚠️ 请提供 title 和 start（ISO 格式，如：2026-03-21T10:00:00+09:00）"

        if not end:
            # Default: 1 hour after start
            try:
                dt = datetime.fromisoformat(start)
                end = (dt + timedelta(hours=1)).isoformat()
            except Exception:
                end = start

        event = {
            "summary": title,
            "location": location,
            "description": desc,
            "start": {"dateTime": start, "timeZone": payload.get("timezone", "Asia/Tokyo")},
            "end":   {"dateTime": end,   "timeZone": payload.get("timezone", "Asia/Tokyo")},
        }
        attendees = payload.get("attendees", [])
        if attendees:
            event["attendees"] = [{"email": a} for a in attendees]

        try:
            result = service.events().insert(calendarId=_GOOGLE_CAL_ID, body=event).execute()
            return f"✅ Google Calendar 事件已创建：{result.get('summary')}\n链接：{result.get('htmlLink', '')}"
        except Exception as e:
            return f"❌ 创建事件失败：{e}"

    elif action == "list":
        now = datetime.utcnow().isoformat() + "Z"
        try:
            result = service.events().list(
                calendarId=_GOOGLE_CAL_ID,
                timeMin=now,
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            events = result.get("items", [])
            if not events:
                return "📭 没有即将到来的日历事件。"
            lines = ["📅 即将到来的事件："]
            for e in events:
                start_dt = e["start"].get("dateTime", e["start"].get("date", ""))
                lines.append(f"  {start_dt[:16]}  {e.get('summary', '（无标题）')}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ 获取事件失败：{e}"

    return f"⚠️ 未知 action：{action}。支持：create / list / ics"


# ── .ics generation ───────────────────────────────────────────────────────────

def _ics_action(payload: dict, action: str) -> str:
    if action == "list":
        return "⚠️ .ics 模式不支持 list 操作。请配置 Google Calendar。"

    title    = payload.get("title") or payload.get("summary", "新事件")
    start    = payload.get("start", "")
    end      = payload.get("end", "")
    location = payload.get("location", "")
    desc     = payload.get("description") or payload.get("body", "")

    if not start:
        return "⚠️ 请提供 start（ISO 格式，如：2026-03-21T10:00:00）"

    try:
        dt_start = datetime.fromisoformat(start.replace("Z", "+00:00"))
        if not end:
            dt_end = dt_start + timedelta(hours=1)
        else:
            dt_end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except Exception as e:
        return f"⚠️ 日期格式解析失败：{e}"

    def _fmt(dt: datetime) -> str:
        return dt.strftime("%Y%m%dT%H%M%SZ")

    uid = f"{_fmt(dt_start)}-mailmind@local"
    ics = "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//MailMindHub//calendar_skill//EN",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"SUMMARY:{_escape_ics(title)}",
        f"DTSTART:{_fmt(dt_start)}",
        f"DTEND:{_fmt(dt_end)}",
        f"LOCATION:{_escape_ics(location)}",
        f"DESCRIPTION:{_escape_ics(desc)}",
        "END:VEVENT",
        "END:VCALENDAR",
    ])

    filename = f"event_{dt_start.strftime('%Y%m%d_%H%M')}.ics"
    return (
        f"📅 日历事件已生成（.ics 格式）\n\n"
        f"标题：{title}\n"
        f"开始：{start}\n"
        f"结束：{end or (dt_start + timedelta(hours=1)).isoformat()}\n"
        f"地点：{location or '—'}\n\n"
        f"[附件文件名：{filename}]\n\n"
        f"```ics\n{ics}\n```"
    )


def _escape_ics(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


SKILL = CalendarSkill()
