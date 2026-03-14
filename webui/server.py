"""
MailMind Web UI — FastAPI admin panel for the email-to-AI daemon.

Start:
    python3 webui/server.py [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import html
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import AsyncGenerator, Optional

import httpx
import uvicorn
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
ENV_FILE = ROOT / ".env"
LOG_FILE = ROOT / "daemon.log"
PID_FILE = ROOT / "daemon.pid"
WEBUI_DIR = Path(__file__).parent

# ─── AI Backends ──────────────────────────────────────────────────────────────
AI_BACKENDS: dict[str, dict] = {
    "deepseek":   {"label": "DeepSeek",         "key": "DEEPSEEK_API_KEY",      "type": "api"},
    "openai":     {"label": "OpenAI (gpt-4o)",   "key": "OPENAI_API_KEY",        "type": "api"},
    "anthropic":  {"label": "Anthropic Claude",  "key": "ANTHROPIC_API_KEY",     "type": "api"},
    "gemini-api": {"label": "Gemini API",        "key": "GEMINI_API_KEY",        "type": "api"},
    "qwen-api":   {"label": "Qwen API",          "key": "QWEN_API_KEY",          "type": "api"},
    "copilot":    {"label": "GitHub Copilot",    "key": "GITHUB_COPILOT_TOKEN",  "type": "api"},
    "claude":     {"label": "Claude CLI",        "key": None,                    "type": "cli"},
    "gemini":     {"label": "Gemini CLI",        "key": None,                    "type": "cli"},
    "codex":      {"label": "Codex CLI",         "key": None,                    "type": "cli"},
    "qwen":       {"label": "Qwen CLI",          "key": None,                    "type": "cli"},
}

# ─── Domain → mailbox type mapping ────────────────────────────────────────────
DOMAIN_MAP: dict[str, str] = {
    "gmail.com": "gmail",
    "outlook.com": "outlook",
    "hotmail.com": "outlook",
    "live.com": "outlook",
    "live.cn": "outlook",
    "msn.com": "outlook",
    "126.com": "126",
    "163.com": "163",
    "yeah.net": "163",
    "qq.com": "qq",
    "foxmail.com": "qq",
    "icloud.com": "icloud",
    "me.com": "icloud",
    "mac.com": "icloud",
    "protonmail.com": "proton",
    "proton.me": "proton",
    "pm.me": "proton",
}

# ─── Prefix per mailbox type ──────────────────────────────────────────────────
MAILBOX_PREFIX: dict[str, str] = {
    "126": "MAIL_126",
    "163": "MAIL_163",
    "qq": "MAIL_QQ",
    "gmail": "MAIL_GMAIL",
    "outlook": "MAIL_OUTLOOK",
    "icloud": "MAIL_ICLOUD",
    "proton": "MAIL_PROTON",
    "custom": "MAIL_CUSTOM",
}

# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="MailMind Web UI")

app.mount("/static", StaticFiles(directory=str(WEBUI_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(WEBUI_DIR / "templates"))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def read_env() -> dict[str, str]:
    """Parse .env file into a dict, correctly handling inline comments and quotes."""
    result: dict[str, str] = {}
    if not ENV_FILE.exists():
        return result
    with ENV_FILE.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if value and value[0] in ('"', "'"):
                # Quoted value: extract content up to the matching closing quote
                q = value[0]
                end = value.find(q, 1)
                value = value[1:end] if end != -1 else value[1:]
            else:
                # Unquoted value: strip inline comment
                value = value.split("#")[0].strip()
            result[key] = value
    return result


def write_env(updates: dict[str, str]) -> None:
    """Update keys in .env, preserving structure and comments. Append new keys at end."""
    lines: list[str] = []
    if ENV_FILE.exists():
        with ENV_FILE.open("r", encoding="utf-8") as f:
            lines = f.readlines()

    handled: set[str] = set()

    # Update existing keys in-place (including commented-out lines)
    for i, raw_line in enumerate(lines):
        line = raw_line.rstrip("\n")
        # Match both active and commented-out key assignments
        m = re.match(r'^(#\s*)?([A-Z_][A-Z0-9_]*)\s*=', line)
        if m:
            key = m.group(2)
            if key in updates:
                value = updates[key]
                # Escape double-quotes in value
                safe_value = value.replace('"', '\\"')
                lines[i] = f'{key}="{safe_value}"\n'
                handled.add(key)

    # Append new keys that weren't in the file
    new_keys = [k for k in updates if k not in handled]
    if new_keys:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append("\n# ─── Web UI additions ────────────────────────────────\n")
        for key in new_keys:
            value = updates[key]
            safe_value = value.replace('"', '\\"')
            lines.append(f'{key}="{safe_value}"\n')

    with ENV_FILE.open("w", encoding="utf-8") as f:
        f.writelines(lines)


def get_status() -> dict:
    """Check PID file and process state, return status dict."""
    status = {"running": False, "pid": None, "mailbox": "—", "ai": "—", "mode": "—"}
    if not PID_FILE.exists():
        return status
    try:
        pid_text = PID_FILE.read_text().strip()
        if not pid_text:
            return status
        pid = int(pid_text)
        # Check if process is alive
        os.kill(pid, 0)
        status["running"] = True
        status["pid"] = pid
        # Read env for display values
        env = read_env()
        status["mailbox"] = env.get("MAILBOX", "?")
        status["ai"] = env.get("AI", "?")
        status["mode"] = env.get("MODE", "idle")
    except (ValueError, OSError, ProcessLookupError):
        pass
    return status


def get_mail_config(env: dict[str, str]) -> dict:
    """Extract mail config based on current MAILBOX type."""
    mailbox_type = env.get("MAILBOX", "")
    prefix = MAILBOX_PREFIX.get(mailbox_type, "MAIL_CUSTOM")

    return {
        "mailbox_type": mailbox_type,
        "prefix": prefix,
        "address": env.get(f"{prefix}_ADDRESS", ""),
        "password": env.get(f"{prefix}_PASSWORD", ""),
        "allowed": env.get(f"{prefix}_ALLOWED", ""),
    }


async def autoconfig_lookup(domain: str) -> Optional[dict]:
    """
    Query Mozilla autoconfig service for the given domain.
    Returns {imap_server, imap_port, smtp_server, smtp_port, smtp_ssl} or None.
    """
    urls = [
        f"https://autoconfig.{domain}/mail/config-v1.1.xml",
        f"https://{domain}/.well-known/autoconfig/mail/config-v1.1.xml",
        f"https://autoconfig.thunderbird.net/v1.1/{domain}",
    ]
    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                text = resp.text

                # Parse IMAP
                imap_m = re.search(
                    r'<incomingServer\s+type="imap"[^>]*>.*?<hostname>([^<]+)</hostname>.*?<port>([^<]+)</port>',
                    text, re.DOTALL | re.IGNORECASE
                )
                # Parse SMTP
                smtp_m = re.search(
                    r'<outgoingServer\s+type="smtp"[^>]*>.*?<hostname>([^<]+)</hostname>.*?<port>([^<]+)</port>.*?<socketType>([^<]*)</socketType>',
                    text, re.DOTALL | re.IGNORECASE
                )

                if imap_m and smtp_m:
                    smtp_port = smtp_m.group(2).strip()
                    socket_type = smtp_m.group(3).strip().upper()
                    smtp_ssl = "true" if socket_type in ("SSL", "SSL/TLS") else "false"
                    return {
                        "imap_server": imap_m.group(1).strip(),
                        "imap_port": imap_m.group(2).strip(),
                        "smtp_server": smtp_m.group(1).strip(),
                        "smtp_port": smtp_port,
                        "smtp_ssl": smtp_ssl,
                    }
            except Exception:
                continue
    return None


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from a string."""
    return re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', text)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    env = read_env()
    status = get_status()
    mail_config = get_mail_config(env)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "env": env,
        "status": status,
        "ai_backends": AI_BACKENDS,
        "mail_config": mail_config,
    })


@app.get("/partials/header_status", response_class=HTMLResponse)
async def header_status(request: Request):
    status = get_status()
    return templates.TemplateResponse("partials/header_status.html", {
        "request": request,
        "status": status,
        "message": None,
        "success": True,
    })


@app.get("/tabs/mail", response_class=HTMLResponse)
async def tab_mail(request: Request):
    env = read_env()
    mail_config = get_mail_config(env)
    return templates.TemplateResponse("partials/tab_mail.html", {
        "request": request,
        "env": env,
        "mail_config": mail_config,
        "feedback": None,
    })


@app.get("/tabs/ai", response_class=HTMLResponse)
async def tab_ai(request: Request):
    env = read_env()
    return templates.TemplateResponse("partials/tab_ai.html", {
        "request": request,
        "env": env,
        "ai_backends": AI_BACKENDS,
        "feedback": None,
    })


@app.get("/tabs/logs", response_class=HTMLResponse)
async def tab_logs(request: Request):
    return templates.TemplateResponse("partials/tab_logs.html", {
        "request": request,
    })


@app.post("/autoconfig", response_class=HTMLResponse)
async def autoconfig(request: Request, email_input: str = Form("")):
    email_address = email_input.strip()
    domain = ""
    mailbox_type = ""
    ac_result = None
    prefix = "MAIL_CUSTOM"
    env = read_env()

    if "@" in email_address:
        domain = email_address.split("@", 1)[1].lower()
        mailbox_type = DOMAIN_MAP.get(domain, "")

        if not mailbox_type:
            # Unknown domain → try autoconfig
            mailbox_type = "custom"
            ac_result = await autoconfig_lookup(domain)

        prefix = MAILBOX_PREFIX.get(mailbox_type, "MAIL_CUSTOM")

    return templates.TemplateResponse("partials/autoconfig_result.html", {
        "request": request,
        "domain": domain,
        "mailbox_type": mailbox_type,
        "ac_result": ac_result,
        "prefix": prefix,
        "env": env,
        "email": email_address,
    })


@app.post("/config/mail", response_class=HTMLResponse)
async def config_mail(request: Request):
    form = await request.form()
    data = dict(form)
    env = read_env()

    # Build updates dict — skip internal/private fields and critical empty values
    updates: dict[str, str] = {}
    for key, value in data.items():
        if key.startswith("_"):
            continue
        if not isinstance(value, str):
            continue
        # Don't overwrite critical keys with empty string
        if key in ("MAILBOX", "AI") and not value.strip():
            continue
        updates[key] = value

    # Determine final mailbox type
    mailbox = updates.get("MAILBOX") or env.get("MAILBOX", "")
    email_input = data.get("_email_input", "").strip()
    if email_input and "@" in email_input:
        if not mailbox:
            domain = email_input.split("@", 1)[1].lower()
            mailbox = DOMAIN_MAP.get(domain, "custom")
            updates["MAILBOX"] = mailbox
        prefix = MAILBOX_PREFIX.get(mailbox, "MAIL_CUSTOM")
        updates[f"{prefix}_ADDRESS"] = email_input

    # Re-map password/allowed to correct prefix if MAILBOX changed
    # (e.g. form had MAIL_CUSTOM_PASSWORD but MAILBOX is now 126)
    if mailbox:
        correct_prefix = MAILBOX_PREFIX.get(mailbox, "MAIL_CUSTOM")
        for suffix in ("_PASSWORD", "_ALLOWED"):
            correct_key = f"{correct_prefix}{suffix}"
            if correct_key in updates:
                continue  # already correct
            # Look for the value under any other prefix
            for pfx in MAILBOX_PREFIX.values():
                wrong_key = f"{pfx}{suffix}"
                if wrong_key in updates and wrong_key != correct_key:
                    updates[correct_key] = updates.pop(wrong_key)
                    break

    try:
        write_env(updates)
        feedback = {"ok": True, "message": "邮件设置已保存"}
    except Exception as e:
        feedback = {"ok": False, "message": f"保存失败: {e}"}

    env = read_env()
    mail_config = get_mail_config(env)
    return templates.TemplateResponse("partials/tab_mail.html", {
        "request": request,
        "env": env,
        "mail_config": mail_config,
        "feedback": feedback,
    })


@app.post("/config/ai", response_class=HTMLResponse)
async def config_ai(request: Request):
    form = await request.form()
    data = dict(form)
    env = read_env()

    updates: dict[str, str] = {}
    for key, value in data.items():
        if key.startswith("_"):
            continue
        if isinstance(value, str):
            # Skip empty API key fields (don't clear existing keys)
            if key.endswith("_API_KEY") or key.endswith("_TOKEN"):
                if not value.strip():
                    continue
            updates[key] = value

    # Handle WEB_SEARCH checkbox — if not in form data, it was unchecked
    if "WEB_SEARCH" not in data:
        updates["WEB_SEARCH"] = "false"

    try:
        write_env(updates)
        feedback = {"ok": True, "message": "AI 设置已保存"}
    except Exception as e:
        feedback = {"ok": False, "message": f"保存失败: {e}"}

    env = read_env()
    return templates.TemplateResponse("partials/tab_ai.html", {
        "request": request,
        "env": env,
        "ai_backends": AI_BACKENDS,
        "feedback": feedback,
    })


@app.post("/daemon/{action}", response_class=HTMLResponse)
async def daemon_action(request: Request, action: str):
    if action not in ("start", "stop", "restart"):
        status = get_status()
        return templates.TemplateResponse("partials/header_status.html", {
            "request": request,
            "status": status,
            "message": f"未知操作: {action}",
            "success": False,
        })

    try:
        result = subprocess.run(
            ["bash", str(ROOT / "manage.sh"), action],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(ROOT),
        )
        raw_output = result.stdout + result.stderr
        output = strip_ansi(raw_output).strip()
        # Take last meaningful line as message
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        message = lines[-1] if lines else f"{action} 完成"
        # Trim message to reasonable length
        if len(message) > 80:
            message = message[:77] + "..."
        success = result.returncode == 0
    except subprocess.TimeoutExpired:
        message = "操作超时"
        success = False
    except Exception as e:
        message = str(e)
        success = False

    # Brief pause to let daemon actually start/stop
    await asyncio.sleep(0.8)
    status = get_status()

    return templates.TemplateResponse("partials/header_status.html", {
        "request": request,
        "status": status,
        "message": message,
        "success": success,
    })


@app.get("/logs/stream")
async def logs_stream(request: Request):
    """SSE endpoint: tail daemon.log and push each new line to client."""

    async def event_generator() -> AsyncGenerator[str, None]:
        # Start from end of file
        if LOG_FILE.exists():
            offset = LOG_FILE.stat().st_size
        else:
            offset = 0

        last_keepalive = time.monotonic()

        while True:
            if await request.is_disconnected():
                break

            now = time.monotonic()

            if LOG_FILE.exists():
                try:
                    current_size = LOG_FILE.stat().st_size
                    if current_size < offset:
                        # File was rotated/truncated
                        offset = 0
                    if current_size > offset:
                        with LOG_FILE.open("r", encoding="utf-8", errors="replace") as f:
                            f.seek(offset)
                            new_data = f.read()
                            offset = f.tell()

                        for line in new_data.splitlines():
                            line = line.rstrip()
                            if not line:
                                continue
                            # Classify line for CSS
                            lower = line.lower()
                            if any(w in lower for w in ("error", "exception", "traceback", "failed", "critical")):
                                css_class = "ll error"
                            elif any(w in lower for w in ("warn", "warning")):
                                css_class = "ll warn"
                            else:
                                css_class = "ll"

                            escaped = html.escape(line)
                            div = f'<div class="{css_class}">{escaped}</div>'
                            yield f"data: {div}\n\n"
                            last_keepalive = now
                except Exception:
                    pass

            # Keepalive comment every 25 seconds
            if now - last_keepalive >= 25:
                yield ": keepalive\n\n"
                last_keepalive = now

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MailMind Web UI")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    args = parser.parse_args()

    print(f"  MailMind Web UI → http://{args.host}:{args.port}")
    uvicorn.run(
        "webui.server:app" if not args.reload else "webui.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(ROOT),
        log_level="info",
    )
