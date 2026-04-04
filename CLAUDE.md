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

テストは `tests/test_email_logic.py` にあり、`decode_str`、`parse_ai_response`、`is_sender_allowed`、`get_body_and_attachments` をカバーする。`core.mail_client` と `utils.parser` から直接インポートする（`email_daemon.py` 経由ではない）。

## Architecture

コードベースはモジュール化されている。エントリポイントは `email_daemon.py` だが、ロジックは以下のパッケージに分散している:

```
email_daemon.py          # エントリポイント：メインループ・電子メール処理・引数解析
tray_app.py              # システムトレイアプリ（pystray 経由）
manage.sh                # デーモン/systemd ライフサイクル管理 + セットアップウィザード

core/
  config.py              # MAILBOXES と AI_BACKENDS 辞書、PROMPT_TEMPLATE/PROMPT_TEMPLATES
  mail_client.py         # IMAP 接続、メール取得、OAuth トークン取得、スレッドコンテキスト取得
  mail_sender.py         # SMTP 送信、アーカイブ出力（extra_headers パラメータ対応）
  one_click_unsubscribe.py  # RFC 8058 原生一键退订：HMAC トークン生成/検証、List-Unsubscribe ヘッダ構築
  validator.py           # 設定検証

ai/
  base.py                # AIBase 抽象クラス
  providers/__init__.py  # 全 AI プロバイダー実装 + get_ai_provider() ファクトリ
  mcp_weather_server.py  # MCP 天気サーバー実装

skills/
  __init__.py            # BaseSkill 抽象クラス
  loader.py              # スキル自動ロード（get_registry()、get_skill()、get_skills_hint()）
  ai_job.py              # 汎用 AI 呼び出しスキル
  translate.py           # 翻訳スキル
  summarize.py           # 要約スキル
  code_review.py         # コードレビュースキル
  shell_exec.py          # シェルコマンド実行スキル
  github_skill.py        # GitHub 操作スキル
  invoice.py             # 請求書処理スキル
  ticket.py             # チケット管理スキル
  calendar_skill.py      # カレンダー操作スキル
  chain.py               # スキルチェーン（複数スキルの順次実行）

tasks/
  scheduler.py           # TaskScheduler：SQLite (tasks.db) でタスク永続化、バックグラウンドスレッドで実行
  registry.py            # execute_task_logic()：タスクタイプごとの実行ロジック

utils/
  parser.py              # parse_ai_response()、auto_detect_tasks()、detect_lang()
  search.py              # web_search()、format_search_results()
  logger.py              # ログ設定
  mcp_client.py          # MCP プロトコルクライアント

webui/
  server.py              # FastAPI 管理パネル（デーモン制御・設定編集・ログ表示・メールボックス管理・統計）
  templates/             # Jinja2 HTML テンプレート（/tabs/stats で mail_stats ダッシュボードを表示）
  static/                # CSS/JS
```

### Mail stats dashboard

`/tabs/stats` タブで `tasks.db` の `mail_stats` テーブルから処理統計を表示する（KPI カード・7日間バーチャート・直近10件テーブル）。`record_stat()` はメール処理後に呼ばれ、DB エラーがあってもメール配信を妨げない。ローカルタイムゾーンで日境界を計算する（`datetime.now()` を使用; `time.time() % 86400` は UTC 起点のため使用しない）。

### MCP support

`ai/mcp_weather_server.py` が MCP 天気サーバーを実装し、`utils/mcp_client.py` が MCP ツール呼び出しをラップする。`MCP_SERVERS` 環境変数でサーバーを有効化し、`MCP_SERVER_<NAME>=<command>` で起動コマンドを指定する（例: `MCP_SERVER_WEATHER=python -m ai.mcp_weather_server`）。

### Configuration model

全認証情報と設定は環境変数で注入される。`manage.sh` は `.env` ファイルから読み込む（コミットしない; `.env.example` からコピー）。

- **`MAILBOXES`** (`core/config.py`) — メールボックスプリセット辞書。キー: `126`/`163`/`qq`/`gmail`/`outlook`/`icloud`/`proton`/`custom`。各エントリに IMAP/SMTP サーバー、ポート、認証タイプ、環境変数名を含む。`sort`/`sort2`/`sort3` は `manage_only: True` フラグを持つ管理専用メールボックスで、メール返信は行わず移動・削除・ラベル付けのみ実行する。
- **`AI_BACKENDS`** (`core/config.py`) — AI バックエンドプリセット辞書。`type` フィールドが `cli`/`api_anthropic`/`api_openai`/`api_gemini`/`api_qwen`/`api_cohere`/`api_spark`/`api_ernie` のどれかを指定。

追加環境変数:
- `PROMPT_LANG` — プロンプト言語: `zh`（デフォルト）/ `ja` / `en` / `ko`。`PROMPT_TEMPLATES` に対応する多言語テンプレートが定義されている。
- `AI_CONCURRENCY` — AI 呼び出し並列数（デフォルト: 3）
- `AI_MODIFY_SUBJECT` — `true` にすると AI が返信の件名を変更可能（デフォルト: false）
- `MAX_EMAIL_CHARS` — AI に渡すメール本文の最大文字数（デフォルト: 4000）
- `TASK_MAX_RETRIES` — タスク失敗時の最大リトライ回数（デフォルト: 3）
- `CONTEXT_MAX_DEPTH` — スレッドコンテキスト取得の最大深度（デフォルト: 5）
- `ATTACHMENT_MAX_SIZE_MB` — 添付ファイル最大サイズ MB（デフォルト: 10）
- `AI_CLI_TIMEOUT` — CLI AI プロセスのタイムアウト秒数（デフォルト: 600）
- `AI_PROGRESS_INTERVAL` — CLI AI 実行中の進捗メール送信間隔秒数（デフォルト: 120、0 で無効）
- `WORKSPACE_DIR` — CLI AI の操作を制限するワークスペースディレクトリ
- `SHOW_FILE_CHANGES` — CLI AI 実行後のファイル変更差分を返信に含める（デフォルト: true）
- `POLL_INTERVAL` — ポーリングモード時のチェック間隔秒数（デフォルト: 60）
- `CACHE_ENABLED` / `CACHE_MAX_SIZE` / `CACHE_TTL` — クエリキャッシュ設定（デフォルト: true / 100 / 3600秒）
- モデルオーバーライド: `ANTHROPIC_MODEL`、`OPENAI_MODEL`、`GEMINI_MODEL`、`DEEPSEEK_MODEL`、`QWEN_MODEL` など各 API バックエンドのデフォルトモデルを変更可能

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
  "schedule_every": "optional interval like 5m/2h/1d",
  "schedule_cron": "cron expression e.g. '0 9 * * *' (mutually exclusive with schedule_every)",
  "schedule_until": "optional ISO",
  "attachments": [{"filename": "report.md", "content": "..."}],
  "task_type": "email|ai_job|weather|news|web_search|report|system_status|email_manage|task_manage|ai_skill|<skill名>",
  "task_payload": {
    "query": "...", "location": "...", "prompt": "...",
    "skill": "weather|news|stock|web_search",
    "action": "move|delete|mark_read|mark_unread (email_manage) or list|cancel|pause|resume|delete (task_manage)",
    "task_id": 3,
    "filter": {"type": "news", "subject": "...", "status": "pending|paused"},
    "target_folder": "..."
  },
  "output": {"email": true, "archive": true, "archive_dir": "reports"}
}
```

- `schedule_at`/`schedule_every`/`schedule_cron` は三択（同時設定不可）; タスクは `tasks.db` に保存されスケジューラが実行
- AI が `task_type` を指定しない場合、`auto_detect_tasks()` がキーワードと時刻表現から自動判定
- `email_manage` — メール整理（移動・削除・既読マーク）; `task_payload` に `action` と `filter` が必須
- `task_manage` — スケジュールタスク管理（一覧・キャンセル・一時停止・再開・削除）
- `ai_skill` — 統一スキル呼び出し; `task_payload.skill` にスキル名、`task_payload.payload` にパラメータ

### Scheduled tasks

`TaskScheduler` (`tasks/scheduler.py`) は SQLite (`tasks.db`) にタスクを永続化し、バックグラウンドスレッドで10秒ごとに実行チェックを行う。`mail_stats` テーブルも同 DB に保持され、メール処理統計（成功/エラー件数・AI 応答時間）を記録する。

実行ロジックは `tasks/registry.py` の `execute_task_logic()` が担当:
- `email` — そのまま送信
- `weather` / `news` / `ai_job` — AI バックエンドを呼び出し
- `web_search` — `utils/search.py` でウェブ検索
- `system_status` — `/proc/meminfo`、`/proc/stat`、`/proc/uptime` から収集
- `report` — 上記を組み合わせて日報生成
- `email_manage` — IMAP 操作（移動・削除・既読マーク）
- `task_manage` — スケジュールタスクの管理操作
- `ai_skill` — 統一スキル呼び出しインターフェース

出力先:
- `email: true` — SMTP で送信
- `archive: true` — `reports/` ディレクトリに保存

### External data

環境変数:
- `WEATHER_API_KEY` (WeatherAPI) / `WEATHER_DEFAULT_LOCATION` (デフォルト: `Tokyo`)
- `NEWS_API_KEY` (NewsAPI) / `NEWS_DEFAULT_QUERY` / `NEWS_DEFAULT_LANGUAGE` / `NEWS_DEFAULT_PAGE_SIZE`
- `BING_API_KEY` / `BRAVE_API_KEY` / `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` (ウェブ検索)
- `TASK_DEFAULT_AI` (スケジュールタスクのデフォルト AI)

インライン AI コンテキスト用ウェブ検索:
- `WEB_SEARCH=true` — 有効化
- `WEB_SEARCH_ENGINE` — `google`（デフォルト）/ `duckduckgo` / `wikipedia` / `bing` / `brave`
- `SEARCH_RESULTS_COUNT` — 注入する検索結果数（デフォルト: 5）
- `WEB_SEARCH_TIMEOUT` — タイムアウト秒数（デフォルト: 10）

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
| `yi` | API | `YI_API_KEY` |
| `ollama` | API (local) | `OLLAMA_BASE_URL` + `OLLAMA_MODEL` |
| `vllm` | API (local) | `VLLM_BASE_URL` + `VLLM_MODEL` |

### Skills plugin system

`skills/` ディレクトリのスキルは起動時に自動ロードされる。各スキルは `BaseSkill` を継承し、モジュールレベルの `SKILL = MySkill()` を定義する。スキルの `name` が `task_type` として AI レスポンスから参照される。`get_skills_hint()` が AI プロンプトにスキル一覧を注入する。

新しいスキルの追加:
```python
# skills/my_skill.py
from skills import BaseSkill

class MySkill(BaseSkill):
    name = "my_skill"
    description = "説明"
    description_ja = "Japanese description"
    description_en = "English description"
    keywords = ["keyword1", "keyword2"]  # auto_detect_tasks() で使用

    def run(self, payload: dict, ai_caller=None) -> str:
        return "result"

SKILL = MySkill()
```

### Adding a new mailbox or AI backend

- 新しいメールボックス → `core/config.py` の `MAILBOXES` に追加
- 新しい AI バックエンド → `core/config.py` の `AI_BACKENDS` に追加し、`ai/providers/__init__.py` の `get_ai_provider()` に対応プロバイダーを追加

## Systemd

```bash
bash manage.sh install    # サービスファイルを生成してインストール（現在の .env を読み込む）
bash manage.sh uninstall  # サービスを削除
```

**注意:** `manage.sh install` は `MAIL_126_*` の環境変数のみを自動インライン化する。他のメールボックスを使う場合は、`/etc/systemd/system/email-daemon.service` に手動で `Environment=` 行を追加する。
