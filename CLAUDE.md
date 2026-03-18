# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MailMindHub is an email-to-AI bridge daemon. Users send emails with instructions; the daemon polls via IMAP, passes the instruction to an AI backend, and replies via SMTP.

## Setup

```bash
# 首次使用：一键配置向导（自动创建 venv、安装依赖、生成 .env）
bash manage.sh setup

# 向导完成后启动
bash manage.sh start
```

手動設定（上級者向け）:
```bash
cp .env.example .env   # 編集して認証情報を記入
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# Gmail OAuth 追加依存: pip install google-auth google-auth-oauthlib google-auth-httplib2
# Outlook OAuth 追加依存: pip install msal
```

## Running

```bash
# デーモン管理
bash manage.sh start | stop | restart | status | log

# 直接起動
python3 email_daemon.py --mailbox gmail --ai claude          # IMAP IDLE モード（デフォルト）
python3 email_daemon.py --mailbox 126 --ai anthropic --poll  # ポーリングモード
python3 email_daemon.py --list                               # 設定状態を表示
python3 email_daemon.py --mailbox gmail --auth               # OAuth 認証（初回のみ）

# Web UI（管理パネル）
python3 webui/server.py [--host HOST] [--port PORT]
```

受信モードは `.env` の `MODE` で制御（または `--poll` フラグ）:
- `MODE=idle` — IMAP IDLE、サーバーがプッシュ通知（デフォルト）
- `MODE=poll` — `POLL_INTERVAL` 秒ごとにポーリング

## Testing

```bash
# 全テスト実行
python -m pytest tests/

# 単一テストファイル実行
python -m unittest tests/test_email_logic.py
```

テストは `tests/test_email_logic.py` にあり、`decode_str`、`parse_ai_response`、`is_sender_allowed`、`get_body_and_attachments` をカバーする。`email_daemon.py` から直接インポートする。

## Architecture

コードベースはモジュール化されている。エントリポイントは `email_daemon.py` だが、ロジックは以下のパッケージに分散している:

```
email_daemon.py          # エントリポイント：メインループ・電子メール処理・引数解析
manage.sh                # デーモン/systemd ライフサイクル管理 + セットアップウィザード

core/
  config.py              # MAILBOXES と AI_BACKENDS 辞書、PROMPT_TEMPLATE
  mail_client.py         # IMAP 接続、メール取得、OAuth トークン取得
  mail_sender.py         # SMTP 送信、アーカイブ出力（extra_headers パラメータ対応）
  one_click_unsubscribe.py  # RFC 8058 原生一键退订：HMAC トークン生成/検証、List-Unsubscribe ヘッダ構築
  validator.py           # 設定検証

ai/
  base.py                # AIBase 抽象クラス
  providers/__init__.py  # 全 AI プロバイダー実装 + get_ai_provider() ファクトリ

tasks/
  scheduler.py           # TaskScheduler：SQLite (tasks.db) でタスク永続化、バックグラウンドスレッドで実行
  registry.py            # execute_task_logic()：タスクタイプごとの実行ロジック

utils/
  parser.py              # parse_ai_response()、auto_detect_tasks()
  search.py              # web_search()、format_search_results()
  logger.py              # ログ設定

webui/
  server.py              # FastAPI 管理パネル（デーモン制御・設定編集・ログ表示）
  templates/             # Jinja2 HTML テンプレート
  static/                # CSS/JS
```

### Configuration model

全認証情報と設定は環境変数で注入される。`manage.sh` は `.env` ファイルから読み込む（コミットしない; `.env.example` からコピー）。

- **`MAILBOXES`** (`core/config.py`) — メールボックスプリセット辞書。キー: `126`/`163`/`qq`/`gmail`/`outlook`/`icloud`/`proton`/`custom`。各エントリに IMAP/SMTP サーバー、ポート、認証タイプ、環境変数名を含む。
- **`AI_BACKENDS`** (`core/config.py`) — AI バックエンドプリセット辞書。`type` フィールドが `cli`/`api_anthropic`/`api_openai`/`api_gemini`/`api_qwen`/`api_cohere`/`api_spark`/`api_ernie` のどれかを指定。

### Main loop flow

```
fetch_unread_emails() → process_email() → call_ai() → parse_ai_response() → send_reply() / scheduler.add_task()
```

- **IMAP IDLE**（デフォルト）: 新着メール通知をサーバーからプッシュ受信; `run_idle()` が自動再接続を処理
- **ポーリングモード** (`--poll` / `MODE=poll`): `run_poll()` が `POLL_INTERVAL` 秒ごとにチェック
- メールボックスごとに送信者ホワイトリストをチェック
- メール受信スレッドは `ThreadPoolExecutor`（最大5スレッド）で並列処理
- 処理済みメール ID は `processed_ids_<mailbox>.json` に永続化（デーモン再起動でも保持）

### AI response format

AI は以下の JSON 形式で回答する（`PROMPT_TEMPLATE` は中国語でハードコード）:
```json
{
  "subject": "...",
  "body": "...",
  "schedule_at": "optional ISO or seconds",
  "schedule_every": "optional interval like 5m/2h",
  "schedule_until": "optional ISO",
  "attachments": [{"filename": "report.md", "content": "..."}],
  "task_type": "email|ai_job|weather|news|web_search|report|system_status",
  "task_payload": {"location": "...", "query": "...", "prompt": "..."},
  "output": {"email": true, "archive": true, "archive_dir": "reports"}
}
```

- `schedule_at`/`schedule_every` が設定された場合、タスクは `tasks.db` に保存されスケジューラが実行
- AI が `task_type` を指定しない場合、`auto_detect_tasks()` がキーワードと時刻表現から自動判定

### Scheduled tasks

`TaskScheduler` (`tasks/scheduler.py`) は SQLite (`tasks.db`) にタスクを永続化し、バックグラウンドスレッドで10秒ごとに実行チェックを行う。

実行ロジックは `tasks/registry.py` の `execute_task_logic()` が担当:
- `email` — そのまま送信
- `weather` / `news` / `ai_job` — AI バックエンドを呼び出し
- `web_search` — `utils/search.py` でウェブ検索
- `system_status` — `/proc/meminfo`、`/proc/stat`、`/proc/uptime` から収集
- `report` — 上記を組み合わせて日報生成

出力先:
- `email: true` — SMTP で送信
- `archive: true` — `reports/` ディレクトリに保存

### External data

環境変数:
- `WEATHER_API_KEY` (WeatherAPI)
- `NEWS_API_KEY` (NewsAPI)
- `BING_API_KEY` / `BRAVE_API_KEY` / `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` (ウェブ検索)
- `TASK_DEFAULT_AI` (スケジュールタスクのデフォルト AI)

インライン AI コンテキスト用ウェブ検索:
- `WEB_SEARCH=true` — 有効化
- `WEB_SEARCH_ENGINE` — `duckduckgo`（デフォルト）/ `wikipedia` / `google` / `bing` / `brave`
- `SEARCH_RESULTS_COUNT` — 注入する検索結果数

原生一键退订（RFC 8058 List-Unsubscribe）:
- `UNSUBSCRIBE_BASE_URL` — Web UI の公開 HTTPS URL（例: `https://mailmind.example.com`）。設定すると定期タスクメールに `List-Unsubscribe` / `List-Unsubscribe-Post` ヘッダが付与され、Gmail・Outlook・Apple Mail などで「退订」ボタンが表示される。
- `UNSUBSCRIBE_SECRET` — HMAC 署名シークレット（省略時は `.unsubscribe_secret` に自動生成・保存）。
- 退订エンドポイント: `POST /unsubscribe?token=<signed-token>` — トークンを検証し、対応するスケジュールタスクを自動キャンセルする（`core/one_click_unsubscribe.py` + `webui/server.py`）。

### Auth types

| Mailbox | Auth |
|---------|------|
| 126, 163, qq, icloud, proton, custom | password (アプリパスワード / 認証コード) |
| gmail | `oauth_google`（ブラウザフロー）または `password`（`MAIL_GMAIL_AUTH=password`）|
| outlook | `oauth_microsoft`（デバイスコードフロー）|

OAuth トークンは `token_<mailbox>.json` にキャッシュ（gitignore 済み）。

### Supported AI backends

| Name | Type | Required |
|------|------|----------|
| `claude` | CLI | Claude Code installed |
| `codex` | CLI | Codex CLI installed |
| `gemini` | CLI | Gemini CLI installed |
| `qwen` | CLI | Qwen CLI installed |
| `copilot` | CLI | GitHub Copilot CLI (`COPILOT_CMD` or VSCode bundled) |
| `anthropic` | API | `ANTHROPIC_API_KEY` |
| `openai` | API | `OPENAI_API_KEY` |
| `gemini-api` | API | `GEMINI_API_KEY` |
| `qwen-api` | API | `QWEN_API_KEY` |
| `deepseek` | API | `DEEPSEEK_API_KEY` |
| `groq` | API | `GROQ_API_KEY` |
| `perplexity` | API | `PERPLEXITY_API_KEY` |
| `cohere` | API | `COHERE_API_KEY` |
| `moonshot` | API | `MOONSHOT_API_KEY` |
| `glm` | API | `GLM_API_KEY` |
| `spark` | API | `SPARK_API_KEY` |
| `ernie` | API | `ERNIE_API_KEY` (`API_KEY:SECRET_KEY` 形式) |

### Adding a new mailbox or AI backend

- 新しいメールボックス → `core/config.py` の `MAILBOXES` に追加
- 新しい AI バックエンド → `core/config.py` の `AI_BACKENDS` に追加し、`ai/providers/__init__.py` の `get_ai_provider()` に対応プロバイダーを追加

## Systemd

```bash
bash manage.sh install    # サービスファイルを生成してインストール（現在の .env を読み込む）
bash manage.sh uninstall  # サービスを削除
```

**注意:** `manage.sh install` は `MAIL_126_*` の環境変数のみを自動インライン化する。他のメールボックスを使う場合は、`/etc/systemd/system/email-daemon.service` に手動で `Environment=` 行を追加する。
