# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MailMind is an email-to-AI bridge daemon. Users send emails with instructions; the daemon polls via IMAP, passes the instruction to an AI backend, and replies via SMTP.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt     # installs requests, imapclient
# Optional for Gmail OAuth:
pip install google-auth google-auth-oauthlib google-auth-httplib2
# Optional for Outlook OAuth:
pip install msal
```

## Running

```bash
# Daemon lifecycle (recommended)
bash manage.sh start | stop | restart | status | log

# Direct invocation
python3 email_daemon.py --mailbox gmail --ai claude          # IMAP IDLE mode (default)
python3 email_daemon.py --mailbox 126 --ai anthropic --poll  # polling mode
python3 email_daemon.py --list                               # show config status
python3 email_daemon.py --mailbox gmail --auth               # one-time OAuth flow
```

Receive mode is controlled by `MODE` in `.env` (or `--poll` flag):
- `MODE=idle` — IMAP IDLE, server pushes notification on new mail (default)
- `MODE=poll` — timed polling every `POLL_INTERVAL` seconds

## Architecture

Everything lives in two files:

- **`email_daemon.py`** — the core daemon (~720 lines)
- **`manage.sh`** — wrapper for background process/systemd lifecycle + all configuration

### Configuration model

All credentials and settings are injected via environment variables. `manage.sh` loads them from a `.env` file (not committed; copy from `.env.example`). There are no config files — just env vars.

### Key data structures in `email_daemon.py`

- **`MAILBOXES`** (line ~29) — dict of mailbox presets keyed by name (`126`, `163`, `qq`, `gmail`, `outlook`), each with IMAP/SMTP servers, ports, auth type, and env var names to read credentials from.
- **`AI_BACKENDS`** (line ~99) — dict of AI backend presets keyed by name, each with `type` (`cli` or `api`), command/URL, and model. API types: `api_anthropic`, `api_openai` (also used for DeepSeek), `api_gemini`, `api_qwen`, `api_copilot` (GitHub Copilot).

### Main loop flow

```
fetch_unread_emails() → process_email() → call_ai() → send_reply()
```

- **IMAP IDLE** (default): server pushes notification on new mail; `run_idle()` handles auto-reconnect
- **Poll mode** (`--poll` / `MODE=poll`): `run_poll()` checks every `POLL_INTERVAL` seconds (default 60)
- Per-mailbox sender whitelist checked before processing
- AI response expected as JSON (`PROMPT_TEMPLATE` hardcoded in Chinese; instructs AI to respond only as JSON):
  ```json
  {
    "subject": "...",
    "body": "...",
    "schedule_at": "optional ISO or seconds",
    "schedule_every": "optional interval like 5m/2h",
    "schedule_until": "optional ISO",
    "attachments": [{"filename": "report.md", "content": "..."}],
    "task_type": "email|ai_job|weather|news|web_search|report",
    "task_payload": {"location": "...", "query": "...", "prompt": "..."},
    "output": {"email": true, "archive": true, "archive_dir": "reports"}
  }
  ```
- `attachments` is optional — only include when the AI needs to return file content
- If `schedule_at`/`schedule_every` is set, the task is persisted and executed by the scheduler
- `task_type` controls scheduled task behavior; default is `email`
- Processed email IDs tracked in `processed_ids` (in-memory set) — resets on daemon restart, so previously seen unread emails may be reprocessed after a restart

### Scheduled tasks

`TaskScheduler` persists tasks in `tasks.json` and executes them in a background thread.
Supported types: `email`, `ai_job`, `weather`, `news`, `web_search`, `report`.

Outputs:
- `email`: send result via SMTP
- `archive`: save to `reports/` (default when scheduled tasks are auto-detected)

### Auto-detect (natural language)

If AI does not specify `task_type`, the daemon auto-detects tasks and schedules them:
- Keywords: weather/news/search/report/AI
- Time parsing: `today/tomorrow/tonight/morning/afternoon`, `every X`, `every week`, `YYYY-MM-DD HH:MM`
- Multi-task: split by `;` or newline into separate scheduled tasks

### External data (default setup)

Environment variables:
- `WEATHER_API_KEY` (WeatherAPI)
- `NEWS_API_KEY` (NewsAPI)
- `BING_API_KEY` (Bing Web Search)
- `TASK_DEFAULT_AI` (default AI for scheduled jobs)

`.env.example` contains the full list and defaults.

### Attachment support

**Receiving:** `get_body_and_attachments()` extracts both the email body and any attachments.
- Text-based attachments (`.txt`, `.md`, `.csv`, etc.) are decoded and appended inline to the AI prompt
- Binary attachments (PDF, images, etc.) are noted by filename only (content not passed to AI)

**Sending:** `send_reply()` accepts an `attachments` list and encodes each entry as a MIME attachment.
- AI returns file content as plain text in the `attachments` JSON field
- Each entry is base64-encoded and attached to the reply email

### Adding a new mailbox or AI backend

Add an entry to `MAILBOXES` or `AI_BACKENDS` in `email_daemon.py` — the rest of the logic is generic and routes by config.

### Auth types

| Mailbox | Auth |
|---------|------|
| 126, 163, qq | password (app password via env var) |
| gmail | `oauth_google` (browser flow) or `password` |
| outlook | `oauth_microsoft` (device code flow) |

OAuth tokens are cached as `token_<mailbox>.json` (gitignored).

## Systemd

```bash
bash manage.sh install    # Generate and install service (reads current .env at install time)
bash manage.sh uninstall  # Remove service
```

`manage.sh install` dynamically generates the service file using env vars from `.env`. **Caveat:** only `MAIL_126_*` vars are inlined; if using other mailboxes, manually add their `Environment=` lines to the generated service file at `/etc/systemd/system/email-daemon.service`.
