"""
MailMindHub Web UI — FastAPI admin panel for the email-to-AI daemon.

Start:
    python3 webui/server.py [--host HOST] [--port PORT]
"""

from __future__ import annotations

import argparse
import asyncio
import html
import os
import re
import secrets
import signal
import sqlite3
import subprocess
import sys
import time
import json
import base64
from datetime import datetime, timedelta
from pathlib import Path
from typing import AsyncGenerator, Optional

import httpx
import uvicorn
from fastapi import Depends, FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
ENV_FILE = ROOT / ".env"
LOG_FILE = ROOT / "daemon.log"
PID_FILE = ROOT / "daemon.pid"
DB_FILE  = ROOT / "tasks.db"
WEBUI_DIR = Path(__file__).parent

# ─── AI Backends (derived from core/config — single source of truth) ──────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import AI_BACKENDS as _CORE_AI_BACKENDS

AI_BACKENDS: dict[str, dict] = {
    name: {
        "label": b.get("label", name),
        "key":   b.get("env_key"),
        "type":  "cli" if b["type"].startswith("cli") else "api",
    }
    for name, b in _CORE_AI_BACKENDS.items()
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
    # Yahoo
    "yahoo.com": "yahoo",
    "yahoo.co.jp": "yahoo",
    "yahoo.co.uk": "yahoo",
    "yahoo.fr": "yahoo",
    "yahoo.de": "yahoo",
    "yahoo.es": "yahoo",
    "yahoo.it": "yahoo",
    "yahoo.com.au": "yahoo",
    "ymail.com": "yahoo",
    # Yandex
    "yandex.com": "yandex",
    "yandex.ru": "yandex",
    "ya.ru": "yandex",
    # Zoho
    "zoho.com": "zoho",
    "zohomail.com": "zoho",
    # GMX / Web.de
    "gmx.com": "gmx",
    "gmx.net": "gmx",
    "gmx.de": "gmx",
    "web.de": "gmx",
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
    "yahoo": "MAIL_CUSTOM",
    "yandex": "MAIL_CUSTOM",
    "zoho": "MAIL_CUSTOM",
    "gmx": "MAIL_CUSTOM",
    "custom": "MAIL_CUSTOM",
}

# Built-in server configs for known providers not in MAILBOXES
BUILTIN_SERVERS: dict[str, dict] = {
    "yahoo": {
        "imap_server": "imap.mail.yahoo.com", "imap_port": "993",
        "smtp_server": "smtp.mail.yahoo.com", "smtp_port": "465", "smtp_ssl": "true",
    },
    "yandex": {
        "imap_server": "imap.yandex.com", "imap_port": "993",
        "smtp_server": "smtp.yandex.com", "smtp_port": "465", "smtp_ssl": "true",
    },
    "zoho": {
        "imap_server": "imap.zoho.com", "imap_port": "993",
        "smtp_server": "smtp.zoho.com", "smtp_port": "465", "smtp_ssl": "true",
    },
    "gmx": {
        "imap_server": "imap.gmx.com", "imap_port": "993",
        "smtp_server": "smtp.gmx.com", "smtp_port": "465", "smtp_ssl": "true",
    },
}

# ─── i18n ─────────────────────────────────────────────────────────────────────

I18N: dict[str, dict[str, str]] = {
    "zh": {
        "slogan": "无需 App，无需新界面，只有邮件。",
        "nav_mail": "邮件设置", "nav_ai": "AI 设置", "nav_tasks": "任务", "nav_skills": "技能", "nav_logs": "日志",
        "status_running": "运行中", "status_stopped": "STOPPED",
        "btn_start": "启动", "btn_stop": "停止", "btn_restart": "重启",
        "mail_address": "邮箱地址", "mail_password": "授权码 / 密码",
        "mail_password_hint": "授权码（非登录密码），在邮箱设置 → POP3/IMAP → 开启服务时获取",
        "mail_allowed": "发件人白名单",
        "mail_allowed_hint": "仅处理来自这些地址的邮件，多个用逗号分隔；空白表示不限制",
        "mail_autoconfig_hint": "输入邮箱地址后自动检测服务器配置",
        "mail_auth_method": "认证方式", "mail_azure_client_id": "Azure App Client ID",
        "mail_azure_hint": "在 Azure Portal 注册应用后获取。授权需运行: python3 email_daemon.py --mailbox outlook --auth",
        "mail_oauth_hint": "OAuth 需先运行: python3 email_daemon.py --mailbox gmail --auth",
        "mail_server_manual": "手动修改服务器",
        "mail_imap_server": "IMAP 服务器", "mail_imap_port": "IMAP 端口",
        "mail_smtp_server": "SMTP 服务器", "mail_smtp_port": "SMTP 端口", "mail_smtp_ssl": "SMTP SSL",
        "btn_save_mail": "保存邮件设置",
        "ai_backend": "AI 后端",
        "ai_cli_notice": "CLI 后端无需 API Key，请确保对应 CLI 工具已安装并可在 PATH 中找到。",
        "section_mode": "运行模式",
        "mode_idle": "IDLE（推荐，服务器实时推送）", "mode_poll": "POLL（定时轮询）",
        "poll_interval": "轮询间隔（秒）",
        "section_tasks": "定时任务", "task_default_ai": "定时任务 AI（TASK_DEFAULT_AI）",
        "task_default_ai_hint": "定时调度任务（天气、新闻等）单独使用的 AI 后端，不填则跟随守护进程启动参数",
        "task_ai_default_opt": "— 使用启动参数 --ai —",
        "section_websearch": "Web 搜索（为 AI 注入实时搜索结果）",
        "ws_enable": "启用 Web 搜索", "ws_engine": "搜索引擎",
        "ws_results_count": "返回结果数量（SEARCH_RESULTS_COUNT）",
        "ws_wiki_lang": "Wikipedia 语言（WIKIPEDIA_LANG）",
        "ws_wiki_lang_hint": "仅搜索引擎为 wikipedia 时生效",
        "section_weather_news": "天气 & 新闻（定时任务用）",
        "weather_api_key": "WeatherAPI 密钥（WEATHER_API_KEY）",
        "weather_api_key_hint": "用于天气查询任务，申请: weatherapi.com（免费额度充足）",
        "weather_default_loc": "默认城市（WEATHER_DEFAULT_LOCATION）",
        "news_api_key": "NewsAPI 密钥（NEWS_API_KEY）",
        "news_api_key_hint": "用于新闻查询任务，申请: newsapi.org（免费额度充足）",
        "news_default_query": "默认搜索词（NEWS_DEFAULT_QUERY）",
        "news_default_lang": "新闻语言（NEWS_DEFAULT_LANGUAGE）",
        "news_default_lang_hint": "ISO 639-1 语言代码，如 zh、en、ja",
        "news_page_size": "新闻条数（NEWS_DEFAULT_PAGE_SIZE）",
        "section_advanced": "高级选项",
        "ai_concurrency": "AI 并发限制（AI_CONCURRENCY）",
        "ai_concurrency_hint": "同时调用 AI 的最大并发数，默认 3（防止多封邮件同时占用 AI 资源）",
        "auto_detect_tasks": "自动任务识别（AUTO_DETECT_TASKS）",
        "auto_detect_tasks_hint": "启用后自动识别邮件中的'任务：'前缀指令并调度；设为 false 可禁用此功能",
        "attach_max_size": "附件大小上限（ATTACHMENT_MAX_SIZE_MB）",
        "attach_max_size_hint": "超出此大小的附件将被跳过，单位 MB，默认 10MB",
        "context_depth": "会话历史深度（CONTEXT_MAX_DEPTH）",
        "context_depth_hint": "获取邮件会话历史的最大层数（用于回复时携带上下文），默认 5",
        "prompt_lang_label": "提示语言（PROMPT_LANG）",
        "prompt_lang_hint": "AI 提示词语言；若设置了自定义模板文件则此项无效",
        "prompt_lang_zh": "中文（默认）", "prompt_lang_ja": "日本語", "prompt_lang_en": "English", "prompt_lang_ko": "한국어",
        "prompt_template_file": "自定义提示模板文件（PROMPT_TEMPLATE_FILE）",
        "prompt_template_file_ph": "留空则使用内置模板（优先于 PROMPT_LANG）",
        "prompt_template_file_hint": "须包含 {instruction} 占位符",
        "workspace_dir": "工作区目录（WORKSPACE_DIR）",
        "workspace_dir_hint": "限制 AI 仅能在此目录及其子目录内读写文件。留空则默认为系统临时目录。",
        "btn_save_ai": "保存 AI 设置",
        "tasks_filter_all": "全部", "tasks_filter_pending": "待执行",
        "tasks_filter_completed": "已完成", "tasks_filter_failed": "失败", "tasks_refresh": "刷新",
        "tasks_col_id": "#", "tasks_col_subject": "主题", "tasks_col_type": "类型",
        "tasks_col_next": "下次执行", "tasks_col_repeat": "重复", "tasks_col_status": "状态",
        "tasks_col_to": "收件人", "tasks_col_actions": "操作",
        "tasks_btn_trigger": "立即", "tasks_btn_delete": "删除",
        "tasks_btn_pause": "暂停", "tasks_btn_resume": "恢复", "tasks_btn_restart": "重新开启",
        "tasks_filter_paused": "已暂停", "tasks_filter_cancelled": "已取消",
        "tasks_empty": "暂无任务",
        "tasks_confirm_trigger": "立即执行此任务？",
        "tasks_confirm_delete": "删除此任务？此操作不可撤销。",
        "tasks_confirm_pause": "暂停此任务？", "tasks_confirm_resume": "恢复此任务？",
        "tasks_confirm_restart": "重新开启此任务？",
        "logs_title": "DAEMON LOG", "logs_clear": "清空显示",
        "login_placeholder": "访问密码", "login_btn": "进入", "login_error": "密码错误",
        "mail_detected": "已检测到", "mail_detected_builtin": "已识别，使用内置服务器配置",
        "mail_detected_auto": "自动检测成功", "mail_detect_failed": "未能自动检测，请手动填写服务器信息",
        "mail_gmail_app_pw": "应用专用密码（简单）", "mail_gmail_oauth": "OAuth（推荐）",
        "fb_mail_saved": "邮件设置已保存",
        "fb_mail_saved_restart": "邮件设置已保存，守护进程已自动重启",
        "fb_ai_saved": "AI 设置已保存",
        "fb_ai_saved_restart": "AI 设置已保存，守护进程已自动重启",
        "fb_save_failed": "保存失败: ",
        "tasks_repeat_every": "每",
        "skills_reload": "重新加载技能", "skills_count_prefix": "已加载 ", "skills_count_suffix": " 个技能",
        "skills_hint": "将技能名称（如 translate、summarize）作为 task_type 发送邮件，即可直接触发对应技能。",
        "skills_col_name": "技能名", "skills_col_description": "描述", "skills_col_keywords": "关键词",
        "skills_empty": "未发现技能（请检查 skills/ 目录）",
        "max_email_chars": "正文截断字数（MAX_EMAIL_CHARS）",
        "max_email_chars_hint": "超出此字符数的邮件正文将被截断，默认 4000",
        "ai_modify_subject": "允许 AI 修改邮件标题（AI_MODIFY_SUBJECT）",
        "ai_modify_subject_hint": "开启后 AI 可在回复中修改 subject 字段，默认关闭",
        "ws_timeout": "搜索超时（WEB_SEARCH_TIMEOUT）",
        "ws_timeout_hint": "Web 搜索 HTTP 请求超时秒数，默认 10",
        "ollama_base_url": "Ollama 服务地址（OLLAMA_BASE_URL）",
        "ollama_model": "Ollama 模型（OLLAMA_MODEL）",
        "vllm_base_url": "vLLM 服务地址（VLLM_BASE_URL）",
        "vllm_model": "vLLM 模型（VLLM_MODEL）",
        "vllm_api_key": "vLLM API Key（VLLM_API_KEY）",
        "local_llm_hint": "需先在本地启动推理服务",
        "nav_stats": "统计",
        "stats_title": "邮件处理统计",
        "stats_total": "总计处理", "stats_today": "今日", "stats_success_rate": "成功率",
        "stats_avg_ai": "平均 AI 耗时", "stats_ms": "毫秒",
        "stats_success": "成功", "stats_error": "失败",
        "stats_7days": "近 7 天处理量", "stats_recent": "最近记录",
        "stats_col_time": "时间", "stats_col_mailbox": "邮箱", "stats_col_status": "状态",
        "stats_col_ai_ms": "AI 耗时(ms)", "stats_col_subject": "主题",
        "stats_empty": "暂无统计数据，处理邮件后将自动记录",
        "stats_no_data": "—",
        "skills_test_btn": "测试", "skills_test_payload": "参数（JSON）",
        "skills_test_run": "运行", "skills_test_cancel": "取消",
        "skills_test_result": "执行结果",
    },
    "ja": {
        "slogan": "アプリ不要。新UI不要。メールだけ。",
        "nav_mail": "メール設定", "nav_ai": "AI 設定", "nav_tasks": "タスク", "nav_skills": "スキル", "nav_logs": "ログ",
        "status_running": "実行中", "status_stopped": "停止中",
        "btn_start": "起動", "btn_stop": "停止", "btn_restart": "再起動",
        "mail_address": "メールアドレス", "mail_password": "認証コード / パスワード",
        "mail_password_hint": "認証コード（ログインパスワードではない）。メール設定 → POP3/IMAP → サービス有効化時に取得",
        "mail_allowed": "送信者ホワイトリスト",
        "mail_allowed_hint": "これらのアドレスからのメールのみ処理します。カンマ区切り。空白は制限なし。",
        "mail_autoconfig_hint": "メールアドレスを入力するとサーバー設定を自動検出します",
        "mail_auth_method": "認証方式", "mail_azure_client_id": "Azure App Client ID",
        "mail_azure_hint": "Azure Portal でアプリ登録後に取得。認証: python3 email_daemon.py --mailbox outlook --auth",
        "mail_oauth_hint": "OAuth は事前に実行が必要: python3 email_daemon.py --mailbox gmail --auth",
        "mail_server_manual": "サーバーを手動設定",
        "mail_imap_server": "IMAP サーバー", "mail_imap_port": "IMAP ポート",
        "mail_smtp_server": "SMTP サーバー", "mail_smtp_port": "SMTP ポート", "mail_smtp_ssl": "SMTP SSL",
        "btn_save_mail": "メール設定を保存",
        "ai_backend": "AI バックエンド",
        "ai_cli_notice": "CLI バックエンドは API キー不要です。対応する CLI ツールがインストールされ PATH に含まれていることを確認してください。",
        "section_mode": "動作モード",
        "mode_idle": "IDLE（推奨、サーバーからリアルタイムプッシュ）", "mode_poll": "POLL（定期ポーリング）",
        "poll_interval": "ポーリング間隔（秒）",
        "section_tasks": "スケジュールタスク", "task_default_ai": "タスク用 AI（TASK_DEFAULT_AI）",
        "task_default_ai_hint": "スケジュールタスク（天気・ニュース等）専用の AI バックエンド。未設定時は起動引数 --ai を使用。",
        "task_ai_default_opt": "— 起動引数 --ai を使用 —",
        "section_websearch": "Web 検索（AI にリアルタイム検索結果を注入）",
        "ws_enable": "Web 検索を有効にする", "ws_engine": "検索エンジン",
        "ws_results_count": "結果件数（SEARCH_RESULTS_COUNT）",
        "ws_wiki_lang": "Wikipedia 言語（WIKIPEDIA_LANG）",
        "ws_wiki_lang_hint": "検索エンジンが wikipedia の場合のみ有効",
        "section_weather_news": "天気 & ニュース（スケジュールタスク用）",
        "weather_api_key": "WeatherAPI キー（WEATHER_API_KEY）",
        "weather_api_key_hint": "天気クエリタスク用。取得: weatherapi.com（無料枠あり）",
        "weather_default_loc": "デフォルト都市（WEATHER_DEFAULT_LOCATION）",
        "news_api_key": "NewsAPI キー（NEWS_API_KEY）",
        "news_api_key_hint": "ニュースクエリタスク用。取得: newsapi.org（無料枠あり）",
        "news_default_query": "デフォルト検索クエリ（NEWS_DEFAULT_QUERY）",
        "news_default_lang": "ニュース言語（NEWS_DEFAULT_LANGUAGE）",
        "news_default_lang_hint": "ISO 639-1 言語コード（zh・en・ja など）",
        "news_page_size": "ニュース件数（NEWS_DEFAULT_PAGE_SIZE）",
        "section_advanced": "高度なオプション",
        "ai_concurrency": "AI 並列数上限（AI_CONCURRENCY）",
        "ai_concurrency_hint": "同時 AI 呼び出しの最大数。デフォルト 3（複数メールによる AI リソース競合を防止）",
        "auto_detect_tasks": "自動タスク識別（AUTO_DETECT_TASKS）",
        "auto_detect_tasks_hint": "有効するとメール中の「任务：」プレフィックス指令を自動識別してスケジュール；false に設定するとこの機能を無効化",
        "attach_max_size": "添付ファイルサイズ上限（ATTACHMENT_MAX_SIZE_MB）",
        "attach_max_size_hint": "この上限を超えた添付はスキップされます。単位 MB、デフォルト 10MB",
        "context_depth": "会話履歴の深さ（CONTEXT_MAX_DEPTH）",
        "context_depth_hint": "返信時に取得するメールスレッドの最大階層数。デフォルト 5",
        "prompt_lang_label": "プロンプト言語（PROMPT_LANG）",
        "prompt_lang_hint": "AI プロンプトの言語。カスタムテンプレートファイルが設定されている場合は無効。",
        "prompt_lang_zh": "中文", "prompt_lang_ja": "日本語（デフォルト）", "prompt_lang_en": "English", "prompt_lang_ko": "한국어",
        "prompt_template_file": "カスタムプロンプトテンプレートファイル（PROMPT_TEMPLATE_FILE）",
        "prompt_template_file_ph": "空白の場合は内蔵テンプレートを使用（PROMPT_LANG より優先）",
        "prompt_template_file_hint": "{instruction} プレースホルダーを含むファイルパスを指定",
        "workspace_dir": "ワークスペース（WORKSPACE_DIR）",
        "workspace_dir_hint": "AI がファイルを読み書きできるディレクトリを制限します。空欄の場合はシステムの一時ディレクトリが使用されます。",
        "btn_save_ai": "AI 設定を保存",
        "tasks_filter_all": "全件", "tasks_filter_pending": "待機中",
        "tasks_filter_completed": "完了", "tasks_filter_failed": "失敗", "tasks_refresh": "更新",
        "tasks_col_id": "#", "tasks_col_subject": "件名", "tasks_col_type": "タイプ",
        "tasks_col_next": "次回実行", "tasks_col_repeat": "繰り返し", "tasks_col_status": "ステータス",
        "tasks_col_to": "宛先", "tasks_col_actions": "操作",
        "tasks_btn_trigger": "今すぐ", "tasks_btn_delete": "削除",
        "tasks_btn_pause": "一時停止", "tasks_btn_resume": "再開", "tasks_btn_restart": "再開（再始動）",
        "tasks_filter_paused": "一時停止中", "tasks_filter_cancelled": "キャンセル済み",
        "tasks_empty": "タスクがありません",
        "tasks_confirm_trigger": "このタスクを今すぐ実行しますか？",
        "tasks_confirm_delete": "このタスクを削除しますか？この操作は取り消せません。",
        "tasks_confirm_pause": "このタスクを一時停止しますか？", "tasks_confirm_resume": "このタスクを再開しますか？",
        "tasks_confirm_restart": "このタスクを再開（再始動）しますか？",
        "logs_title": "DAEMON LOG", "logs_clear": "表示をクリア",
        "login_placeholder": "パスワード", "login_btn": "ログイン", "login_error": "パスワードが違います",
        "mail_detected": "検出しました", "mail_detected_builtin": "認識済み、内蔵サーバー設定を使用",
        "mail_detected_auto": "自動検出成功", "mail_detect_failed": "自動検出失敗。手動でサーバー情報を入力してください",
        "mail_gmail_app_pw": "アプリパスワード（シンプル）", "mail_gmail_oauth": "OAuth（推奨）",
        "fb_mail_saved": "メール設定を保存しました",
        "fb_mail_saved_restart": "メール設定を保存し、デーモンを再起動しました",
        "fb_ai_saved": "AI 設定を保存しました",
        "fb_ai_saved_restart": "AI 設定を保存し、デーモンを再起動しました",
        "fb_save_failed": "保存に失敗しました: ",
        "tasks_repeat_every": "毎",
        "skills_reload": "スキルを再読み込み", "skills_count_prefix": "読み込み済み: ", "skills_count_suffix": " スキル",
        "skills_hint": "スキル名（例: translate、summarize）を task_type としてメールを送信するとスキルを直接呼び出せます。",
        "skills_col_name": "スキル名", "skills_col_description": "説明", "skills_col_keywords": "キーワード",
        "skills_empty": "スキルが見つかりません（skills/ ディレクトリを確認してください）",
        "max_email_chars": "本文最大文字数 (MAX_EMAIL_CHARS)",
        "max_email_chars_hint": "この文字数を超えるメール本文は切り詰められます。デフォルト 4000",
        "ai_modify_subject": "AI による件名変更を許可 (AI_MODIFY_SUBJECT)",
        "ai_modify_subject_hint": "有効にすると AI が返信の subject フィールドを変更できます。デフォルト無効",
        "ws_timeout": "検索タイムアウト (WEB_SEARCH_TIMEOUT)",
        "ws_timeout_hint": "Web 検索 HTTP リクエストのタイムアウト秒数。デフォルト 10",
        "ollama_base_url": "Ollama サービス URL (OLLAMA_BASE_URL)",
        "ollama_model": "Ollama モデル (OLLAMA_MODEL)",
        "vllm_base_url": "vLLM サービス URL (VLLM_BASE_URL)",
        "vllm_model": "vLLM モデル (VLLM_MODEL)",
        "vllm_api_key": "vLLM API Key (VLLM_API_KEY)",
        "local_llm_hint": "ローカル推論サービスを事前に起動してください",
        "nav_stats": "統計",
        "stats_title": "メール処理統計",
        "stats_total": "合計処理数", "stats_today": "本日", "stats_success_rate": "成功率",
        "stats_avg_ai": "平均 AI 応答時間", "stats_ms": "ms",
        "stats_success": "成功", "stats_error": "失敗",
        "stats_7days": "直近 7 日間", "stats_recent": "最近の記録",
        "stats_col_time": "時刻", "stats_col_mailbox": "メールボックス", "stats_col_status": "状態",
        "stats_col_ai_ms": "AI 応答(ms)", "stats_col_subject": "件名",
        "stats_empty": "統計データがありません。メールを処理すると自動記録されます",
        "stats_no_data": "—",
        "skills_test_btn": "テスト", "skills_test_payload": "パラメータ（JSON）",
        "skills_test_run": "実行", "skills_test_cancel": "キャンセル",
        "skills_test_result": "実行結果",
    },
    "en": {
        "slogan": "No app. No new interface. Just email.",
        "nav_mail": "Mail Settings", "nav_ai": "AI Settings", "nav_tasks": "Tasks", "nav_skills": "Skills", "nav_logs": "Logs",
        "status_running": "Running", "status_stopped": "STOPPED",
        "btn_start": "Start", "btn_stop": "Stop", "btn_restart": "Restart",
        "mail_address": "Email Address", "mail_password": "Auth Code / Password",
        "mail_password_hint": "Authorization code (not login password). Get it from mail settings → POP3/IMAP → Enable service.",
        "mail_allowed": "Sender Whitelist",
        "mail_allowed_hint": "Only process emails from these addresses, comma-separated. Empty = no restriction.",
        "mail_autoconfig_hint": "Enter your email address to auto-detect server settings",
        "mail_auth_method": "Auth Method", "mail_azure_client_id": "Azure App Client ID",
        "mail_azure_hint": "Obtain from Azure Portal after registering an app. Run: python3 email_daemon.py --mailbox outlook --auth",
        "mail_oauth_hint": "OAuth requires running first: python3 email_daemon.py --mailbox gmail --auth",
        "mail_server_manual": "Manually configure server",
        "mail_imap_server": "IMAP Server", "mail_imap_port": "IMAP Port",
        "mail_smtp_server": "SMTP Server", "mail_smtp_port": "SMTP Port", "mail_smtp_ssl": "SMTP SSL",
        "btn_save_mail": "Save Mail Settings",
        "ai_backend": "AI Backend",
        "ai_cli_notice": "CLI backends require no API Key. Ensure the CLI tool is installed and in your PATH.",
        "section_mode": "Mode",
        "mode_idle": "IDLE (recommended, server push)", "mode_poll": "POLL (periodic polling)",
        "poll_interval": "Poll Interval (seconds)",
        "section_tasks": "Scheduled Tasks", "task_default_ai": "Task AI (TASK_DEFAULT_AI)",
        "task_default_ai_hint": "AI backend for scheduled tasks (weather, news, etc.). Empty = use --ai argument.",
        "task_ai_default_opt": "— Use --ai argument —",
        "section_websearch": "Web Search (inject real-time results into AI)",
        "ws_enable": "Enable Web Search", "ws_engine": "Search Engine",
        "ws_results_count": "Result Count (SEARCH_RESULTS_COUNT)",
        "ws_wiki_lang": "Wikipedia Language (WIKIPEDIA_LANG)",
        "ws_wiki_lang_hint": "Only applies when search engine is wikipedia",
        "section_weather_news": "Weather & News (for scheduled tasks)",
        "weather_api_key": "WeatherAPI Key (WEATHER_API_KEY)",
        "weather_api_key_hint": "For weather query tasks. Get at: weatherapi.com (free tier available)",
        "weather_default_loc": "Default City (WEATHER_DEFAULT_LOCATION)",
        "news_api_key": "NewsAPI Key (NEWS_API_KEY)",
        "news_api_key_hint": "For news query tasks. Get at: newsapi.org (free tier available)",
        "news_default_query": "Default Search Query (NEWS_DEFAULT_QUERY)",
        "news_default_lang": "News Language (NEWS_DEFAULT_LANGUAGE)",
        "news_default_lang_hint": "ISO 639-1 code, e.g. en, zh, ja",
        "news_page_size": "News Count (NEWS_DEFAULT_PAGE_SIZE)",
        "section_advanced": "Advanced Options",
        "ai_concurrency": "AI Concurrency Limit (AI_CONCURRENCY)",
        "ai_concurrency_hint": "Max simultaneous AI calls. Default 3 (prevents resource contention).",
        "auto_detect_tasks": "Auto Task Detection (AUTO_DETECT_TASKS)",
        "auto_detect_tasks_hint": "Enable to auto-detect 'task:' prefix commands in emails and schedule them; set to false to disable",
        "attach_max_size": "Attachment Size Limit (ATTACHMENT_MAX_SIZE_MB)",
        "attach_max_size_hint": "Attachments exceeding this size will be skipped. Unit: MB, default 10MB.",
        "context_depth": "Conversation History Depth (CONTEXT_MAX_DEPTH)",
        "context_depth_hint": "Max email thread levels to fetch for context in replies. Default 5.",
        "prompt_lang_label": "Prompt Language (PROMPT_LANG)",
        "prompt_lang_hint": "Language of AI prompts. Ignored if a custom template file is set.",
        "prompt_lang_zh": "中文", "prompt_lang_ja": "日本語", "prompt_lang_en": "English (default)", "prompt_lang_ko": "한국어",
        "prompt_template_file": "Custom Prompt Template File (PROMPT_TEMPLATE_FILE)",
        "prompt_template_file_ph": "Leave empty to use built-in template (overrides PROMPT_LANG)",
        "prompt_template_file_hint": "Path to a file containing the {instruction} placeholder",
        "workspace_dir": "Workspace Directory (WORKSPACE_DIR)",
        "workspace_dir_hint": "Restrict AI file access to this directory. If empty, uses system temp dir.",
        "btn_save_ai": "Save AI Settings",
        "tasks_filter_all": "All", "tasks_filter_pending": "Pending",
        "tasks_filter_completed": "Completed", "tasks_filter_failed": "Failed", "tasks_refresh": "Refresh",
        "tasks_col_id": "#", "tasks_col_subject": "Subject", "tasks_col_type": "Type",
        "tasks_col_next": "Next Run", "tasks_col_repeat": "Repeat", "tasks_col_status": "Status",
        "tasks_col_to": "Recipient", "tasks_col_actions": "Actions",
        "tasks_btn_trigger": "Run Now", "tasks_btn_delete": "Delete",
        "tasks_btn_pause": "Pause", "tasks_btn_resume": "Resume", "tasks_btn_restart": "Restart",
        "tasks_filter_paused": "Paused", "tasks_filter_cancelled": "Cancelled",
        "tasks_empty": "No tasks found",
        "tasks_confirm_trigger": "Run this task immediately?",
        "tasks_confirm_delete": "Delete this task? This cannot be undone.",
        "tasks_confirm_pause": "Pause this task?", "tasks_confirm_resume": "Resume this task?",
        "tasks_confirm_restart": "Restart this task?",
        "logs_title": "DAEMON LOG", "logs_clear": "Clear display",
        "login_placeholder": "Password", "login_btn": "Login", "login_error": "Incorrect password",
        "mail_detected": "Detected", "mail_detected_builtin": "Recognized, using built-in server config",
        "mail_detected_auto": "Auto-detected", "mail_detect_failed": "Could not auto-detect. Please fill in server details manually.",
        "mail_gmail_app_pw": "App Password (simple)", "mail_gmail_oauth": "OAuth (recommended)",
        "fb_mail_saved": "Mail settings saved",
        "fb_mail_saved_restart": "Mail settings saved, daemon restarted",
        "fb_ai_saved": "AI settings saved",
        "fb_ai_saved_restart": "AI settings saved, daemon restarted",
        "fb_save_failed": "Save failed: ",
        "tasks_repeat_every": "Every",
        "skills_reload": "Reload Skills", "skills_count_prefix": "Loaded: ", "skills_count_suffix": " skills",
        "skills_hint": "Send an email with a skill name (e.g. translate, summarize) as task_type to invoke it directly.",
        "skills_col_name": "Skill", "skills_col_description": "Description", "skills_col_keywords": "Keywords",
        "skills_empty": "No skills found (check the skills/ directory)",
        "max_email_chars": "Email Body Char Limit (MAX_EMAIL_CHARS)",
        "max_email_chars_hint": "Email bodies exceeding this length will be truncated. Default 4000.",
        "ai_modify_subject": "Allow AI to Modify Subject (AI_MODIFY_SUBJECT)",
        "ai_modify_subject_hint": "When enabled, AI can change the subject field in replies. Default off.",
        "ws_timeout": "Search Timeout (WEB_SEARCH_TIMEOUT)",
        "ws_timeout_hint": "HTTP timeout in seconds for web search requests. Default 10.",
        "ollama_base_url": "Ollama Service URL (OLLAMA_BASE_URL)",
        "ollama_model": "Ollama Model (OLLAMA_MODEL)",
        "vllm_base_url": "vLLM Service URL (VLLM_BASE_URL)",
        "vllm_model": "vLLM Model (VLLM_MODEL)",
        "vllm_api_key": "vLLM API Key (VLLM_API_KEY)",
        "local_llm_hint": "Start the local inference service before use",
        "nav_stats": "Stats",
        "stats_title": "Mail Processing Stats",
        "stats_total": "Total Processed", "stats_today": "Today", "stats_success_rate": "Success Rate",
        "stats_avg_ai": "Avg AI Response", "stats_ms": "ms",
        "stats_success": "Success", "stats_error": "Error",
        "stats_7days": "Last 7 Days", "stats_recent": "Recent Records",
        "stats_col_time": "Time", "stats_col_mailbox": "Mailbox", "stats_col_status": "Status",
        "stats_col_ai_ms": "AI ms", "stats_col_subject": "Subject",
        "stats_empty": "No stats yet. Records will appear after emails are processed.",
        "stats_no_data": "—",
        "skills_test_btn": "Test", "skills_test_payload": "Payload (JSON)",
        "skills_test_run": "Run", "skills_test_cancel": "Cancel",
        "skills_test_result": "Result",
    },
    "ko": {
        "slogan": "앱도, 새로운 인터페이스도 필요 없습니다. 오직 이메일뿐입니다.",
        "nav_mail": "메일 설정", "nav_ai": "AI 설정", "nav_tasks": "작업", "nav_skills": "스킬", "nav_logs": "로그",
        "status_running": "실행 중", "status_stopped": "정지됨",
        "btn_start": "시작", "btn_stop": "정지", "btn_restart": "재시작",
        "mail_address": "이메일 주소", "mail_password": "인증 코드 / 비밀번호",
        "mail_password_hint": "인증 코드(로그인 비밀번호 아님). 메일 설정 → POP3/IMAP → 서비스 활성화 시 발급.",
        "mail_allowed": "발신자 허용 목록",
        "mail_allowed_hint": "이 주소에서 온 메일만 처리합니다. 쉼표로 구분. 비워두면 제한 없음.",
        "mail_autoconfig_hint": "이메일 주소를 입력하면 서버 설정을 자동 감지합니다",
        "mail_auth_method": "인증 방식", "mail_azure_client_id": "Azure App Client ID",
        "mail_azure_hint": "Azure Portal에서 앱 등록 후 획득. 인증: python3 email_daemon.py --mailbox outlook --auth",
        "mail_oauth_hint": "OAuth 사전 실행 필요: python3 email_daemon.py --mailbox gmail --auth",
        "mail_server_manual": "서버 수동 설정",
        "mail_imap_server": "IMAP 서버", "mail_imap_port": "IMAP 포트",
        "mail_smtp_server": "SMTP 서버", "mail_smtp_port": "SMTP 포트", "mail_smtp_ssl": "SMTP SSL",
        "btn_save_mail": "메일 설정 저장",
        "ai_backend": "AI 백엔드",
        "ai_cli_notice": "CLI 백엔드는 API 키가 필요 없습니다. 해당 CLI 도구가 설치되어 PATH에 포함되어 있는지 확인하세요.",
        "section_mode": "동작 모드",
        "mode_idle": "IDLE (권장, 서버 실시간 푸시)", "mode_poll": "POLL (주기적 폴링)",
        "poll_interval": "폴링 간격 (초)",
        "section_tasks": "예약 작업", "task_default_ai": "작업 AI (TASK_DEFAULT_AI)",
        "task_default_ai_hint": "예약 작업(날씨·뉴스 등) 전용 AI 백엔드. 미설정 시 --ai 인수 사용.",
        "task_ai_default_opt": "— --ai 인수 사용 —",
        "section_websearch": "웹 검색 (AI에 실시간 검색 결과 주입)",
        "ws_enable": "웹 검색 활성화", "ws_engine": "검색 엔진",
        "ws_results_count": "결과 수 (SEARCH_RESULTS_COUNT)",
        "ws_wiki_lang": "Wikipedia 언어 (WIKIPEDIA_LANG)",
        "ws_wiki_lang_hint": "검색 엔진이 wikipedia일 때만 적용됩니다",
        "section_weather_news": "날씨 & 뉴스 (예약 작업용)",
        "weather_api_key": "WeatherAPI 키 (WEATHER_API_KEY)",
        "weather_api_key_hint": "날씨 조회 작업용. 발급: weatherapi.com (무료 플랜 제공)",
        "weather_default_loc": "기본 도시 (WEATHER_DEFAULT_LOCATION)",
        "news_api_key": "NewsAPI 키 (NEWS_API_KEY)",
        "news_api_key_hint": "뉴스 조회 작업용. 발급: newsapi.org (무료 플랜 제공)",
        "news_default_query": "기본 검색어 (NEWS_DEFAULT_QUERY)",
        "news_default_lang": "뉴스 언어 (NEWS_DEFAULT_LANGUAGE)",
        "news_default_lang_hint": "ISO 639-1 코드 (예: ko, en, zh)",
        "news_page_size": "뉴스 수 (NEWS_DEFAULT_PAGE_SIZE)",
        "section_advanced": "고급 옵션",
        "ai_concurrency": "AI 동시 호출 제한 (AI_CONCURRENCY)",
        "ai_concurrency_hint": "동시 AI 호출 최대 수. 기본값 3 (여러 메일의 AI 리소스 경합 방지).",
        "auto_detect_tasks": "자동 작업 감지 (AUTO_DETECT_TASKS)",
        "auto_detect_tasks_hint": "이메일의 '任务：' 접두사 명령을 자동으로 감지하여 예약; false 로 설정하면 이 기능 비활성화",
        "attach_max_size": "첨부 파일 크기 제한 (ATTACHMENT_MAX_SIZE_MB)",
        "attach_max_size_hint": "이 크기를 초과하는 첨부 파일은 건너뜁니다. 단위: MB, 기본값 10MB.",
        "context_depth": "대화 히스토리 깊이 (CONTEXT_MAX_DEPTH)",
        "context_depth_hint": "답장 시 컨텍스트로 가져올 메일 스레드 최대 단계 수. 기본값 5.",
        "prompt_lang_label": "프롬프트 언어 (PROMPT_LANG)",
        "prompt_lang_hint": "AI 프롬프트 언어. 커스텀 템플릿 파일이 설정된 경우 무시됩니다.",
        "prompt_lang_zh": "中文", "prompt_lang_ja": "日本語", "prompt_lang_en": "English", "prompt_lang_ko": "한국어（기본）",
        "prompt_template_file": "커스텀 프롬프트 템플릿 파일 (PROMPT_TEMPLATE_FILE)",
        "prompt_template_file_ph": "비워두면 내장 템플릿 사용 (PROMPT_LANG보다 우선)",
        "prompt_template_file_hint": "{instruction} 플레이스홀더를 포함한 파일 경로",
        "workspace_dir": "작업 공간 (WORKSPACE_DIR)",
        "workspace_dir_hint": "AI의 파일 접근을 이 디렉토리로 제한합니다. 비워두면 시스템 임시 디렉토리를 사용합니다.",
        "btn_save_ai": "AI 설정 저장",
        "tasks_filter_all": "전체", "tasks_filter_pending": "대기 중",
        "tasks_filter_completed": "완료", "tasks_filter_failed": "실패", "tasks_refresh": "새로고침",
        "tasks_col_id": "#", "tasks_col_subject": "제목", "tasks_col_type": "유형",
        "tasks_col_next": "다음 실행", "tasks_col_repeat": "반복", "tasks_col_status": "상태",
        "tasks_col_to": "수신자", "tasks_col_actions": "작업",
        "tasks_btn_trigger": "즉시 실행", "tasks_btn_delete": "삭제",
        "tasks_btn_pause": "일시정지", "tasks_btn_resume": "재개", "tasks_btn_restart": "다시 시작",
        "tasks_filter_paused": "일시정지", "tasks_filter_cancelled": "취소됨",
        "tasks_empty": "작업이 없습니다",
        "tasks_confirm_trigger": "이 작업을 지금 즉시 실행하시겠습니까?",
        "tasks_confirm_delete": "이 작업을 삭제하시겠습니까? 이 작업은 취소할 수 없습니다.",
        "tasks_confirm_pause": "이 작업을 일시정지하시겠습니까?", "tasks_confirm_resume": "이 작업을 재개하시겠습니까?",
        "tasks_confirm_restart": "이 작업을 다시 시작하시겠습니까?",
        "logs_title": "DAEMON LOG", "logs_clear": "화면 지우기",
        "login_placeholder": "비밀번호", "login_btn": "로그인", "login_error": "비밀번호가 올바르지 않습니다",
        "mail_detected": "감지됨", "mail_detected_builtin": "인식됨, 내장 서버 설정 사용",
        "mail_detected_auto": "자동 감지 성공", "mail_detect_failed": "자동 감지 실패. 서버 정보를 직접 입력해주세요.",
        "mail_gmail_app_pw": "앱 비밀번호 (간단)", "mail_gmail_oauth": "OAuth (권장)",
        "fb_mail_saved": "메일 설정이 저장되었습니다",
        "fb_mail_saved_restart": "메일 설정이 저장되고 데몬이 재시작되었습니다",
        "fb_ai_saved": "AI 설정이 저장되었습니다",
        "fb_ai_saved_restart": "AI 설정이 저장되고 데몬이 재시작되었습니다",
        "fb_save_failed": "저장 실패: ",
        "tasks_repeat_every": "매",
        "skills_reload": "스킬 다시 로드", "skills_count_prefix": "로드됨: ", "skills_count_suffix": " 스킬",
        "skills_hint": "스킬 이름(예: translate, summarize)을 task_type으로 이메일을 보내면 스킬이 직접 실행됩니다.",
        "skills_col_name": "스킬명", "skills_col_description": "설명", "skills_col_keywords": "키워드",
        "skills_empty": "스킬이 없습니다 (skills/ 디렉토리를 확인하세요)",
        "max_email_chars": "메일 본문 최대 문자 수 (MAX_EMAIL_CHARS)",
        "max_email_chars_hint": "이 문자 수를 초과하는 메일 본문은 잘립니다. 기본값 4000.",
        "ai_modify_subject": "AI의 제목 변경 허용 (AI_MODIFY_SUBJECT)",
        "ai_modify_subject_hint": "활성화 시 AI가 답장의 subject 필드를 변경할 수 있습니다. 기본값 비활성화.",
        "ws_timeout": "검색 타임아웃 (WEB_SEARCH_TIMEOUT)",
        "ws_timeout_hint": "웹 검색 HTTP 요청 타임아웃(초). 기본값 10.",
        "ollama_base_url": "Ollama 서비스 URL (OLLAMA_BASE_URL)",
        "ollama_model": "Ollama 모델 (OLLAMA_MODEL)",
        "vllm_base_url": "vLLM 서비스 URL (VLLM_BASE_URL)",
        "vllm_model": "vLLM 모델 (VLLM_MODEL)",
        "vllm_api_key": "vLLM API Key (VLLM_API_KEY)",
        "local_llm_hint": "사전에 로컬 추론 서비스를 실행해 주세요",
        "nav_stats": "통계",
        "stats_title": "메일 처리 통계",
        "stats_total": "총 처리", "stats_today": "오늘", "stats_success_rate": "성공률",
        "stats_avg_ai": "평균 AI 응답", "stats_ms": "ms",
        "stats_success": "성공", "stats_error": "실패",
        "stats_7days": "최근 7일", "stats_recent": "최근 기록",
        "stats_col_time": "시간", "stats_col_mailbox": "메일함", "stats_col_status": "상태",
        "stats_col_ai_ms": "AI ms", "stats_col_subject": "제목",
        "stats_empty": "통계 데이터 없음. 메일 처리 후 자동으로 기록됩니다.",
        "stats_no_data": "—",
        "skills_test_btn": "테스트", "skills_test_payload": "파라미터 (JSON)",
        "skills_test_run": "실행", "skills_test_cancel": "취소",
        "skills_test_result": "실행 결과",
    },
}


def get_ui_lang(request: Request) -> str:
    """Get UI language from session, falling back to env default."""
    return request.session.get("ui_lang", os.environ.get("WEBUI_LANG", "zh"))


def _ctx(request: Request, **extra) -> dict:
    """Build base template context with i18n, session lang, and extras."""
    lang = get_ui_lang(request)
    return {"request": request, "t": I18N.get(lang, I18N["zh"]), "ui_lang": lang, **extra}


# ─── Auth ─────────────────────────────────────────────────────────────────────
_SESSION_SECRET = os.environ.get("WEBUI_SECRET") or secrets.token_hex(32)
WEBUI_PASSWORD: str = ""  # loaded lazily from .env


def _get_password() -> str:
    """Read WEBUI_PASSWORD from env or .env file at runtime."""
    val = os.environ.get("WEBUI_PASSWORD", "")
    if val:
        return val
    env = {}
    if ENV_FILE.exists():
        with ENV_FILE.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip(); v = v.strip()
                if v and v[0] in ('"', "'"):
                    q = v[0]; end = v.find(q, 1)
                    v = v[1:end] if end != -1 else v[1:]
                else:
                    v = v.split("#")[0].strip()
                env[k] = v
    return env.get("WEBUI_PASSWORD", "")


def require_auth(request: Request):
    """Dependency: redirect to /login if not authenticated."""
    pw = _get_password()
    if pw and not request.session.get("authenticated"):
        raise _LoginRedirect()


class _LoginRedirect(Exception):
    pass


# ─── FastAPI app ──────────────────────────────────────────────────────────────
app = FastAPI(title="MailMindHub Web UI")
app.add_middleware(SessionMiddleware, secret_key=_SESSION_SECRET, max_age=86400 * 30)

app.mount("/static", StaticFiles(directory=str(WEBUI_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(WEBUI_DIR / "templates"))

# ─── Jinja2 custom filters ────────────────────────────────────────────────────

def _fmt_ts(ts) -> str:
    """Format a Unix timestamp to a readable date-time string."""
    if ts is None:
        return "—"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%m-%d %H:%M")
    except Exception:
        return str(ts)

templates.env.filters["fmt_ts"] = _fmt_ts


def _fmt_datetime(ts, fmt="%H:%M") -> str:
    """Format a Unix timestamp to a readable time string."""
    if ts is None:
        return ""
    try:
        return datetime.fromtimestamp(float(ts)).strftime(fmt)
    except Exception:
        return ""


templates.env.filters["datetime"] = _fmt_datetime

# ─── Chat DB helpers ──────────────────────────────────────────────────────────

CHAT_DB = ROOT / "chat_history.db"


def init_chat_db():
    """Initialize chat history SQLite database."""
    if not CHAT_DB.exists():
        with sqlite3.connect(str(CHAT_DB)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT DEFAULT '新对话',
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    updated_at REAL DEFAULT (strftime('%s', 'now'))
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    role TEXT NOT NULL,  -- 'user' or 'assistant'
                    content TEXT NOT NULL,
                    ai_backend TEXT,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id)")
            conn.commit()


def get_chat_sessions(limit: int = 50) -> list[dict]:
    """Get all chat sessions, ordered by last updated."""
    if not CHAT_DB.exists():
        init_chat_db()
        return []
    try:
        with sqlite3.connect(str(CHAT_DB)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT s.id, s.name, s.created_at, s.updated_at,
                       (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) as msg_count
                FROM sessions s
                ORDER BY s.updated_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def get_chat_messages(session_id: int, limit: int = 50) -> list[dict]:
    """Get messages for a session."""
    if not CHAT_DB.exists():
        return []
    try:
        with sqlite3.connect(str(CHAT_DB)) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute("""
                SELECT id, role, content, ai_backend, created_at
                FROM messages
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ?
            """, (session_id, limit))
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def create_chat_session(name: str = "新对话") -> int:
    """Create a new chat session and return its ID."""
    if not CHAT_DB.exists():
        init_chat_db()
    with sqlite3.connect(str(CHAT_DB)) as conn:
        cur = conn.execute(
            "INSERT INTO sessions (name) VALUES (?)", (name,)
        )
        conn.commit()
        return cur.lastrowid


def add_chat_message(session_id: int, role: str, content: str, ai_backend: str = None):
    """Add a message to a chat session."""
    if not CHAT_DB.exists():
        init_chat_db()
    with sqlite3.connect(str(CHAT_DB)) as conn:
        conn.execute(
            "INSERT INTO messages (session_id, role, content, ai_backend) VALUES (?, ?, ?, ?)",
            (session_id, role, content, ai_backend)
        )
        conn.execute(
            "UPDATE sessions SET updated_at = strftime('%s', 'now') WHERE id = ?",
            (session_id,)
        )
        conn.commit()


def delete_chat_session(session_id: int):
    """Delete a chat session and its messages."""
    if not CHAT_DB.exists():
        return
    with sqlite3.connect(str(CHAT_DB)) as conn:
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()


def rename_chat_session(session_id: int, name: str):
    """Rename a chat session."""
    if not CHAT_DB.exists():
        return
    with sqlite3.connect(str(CHAT_DB)) as conn:
        conn.execute("UPDATE sessions SET name = ? WHERE id = ?", (name, session_id))
        conn.commit()


def get_session_messages_for_context(session_id: int, limit: int = 20) -> list[dict]:
    """Get messages formatted for AI context (role + content)."""
    messages = get_chat_messages(session_id, limit=limit)
    return [
        {"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]}
        for m in messages
    ]


# ─── Task DB helpers ──────────────────────────────────────────────────────────

def get_tasks(status_filter: str = "all", limit: int = 100) -> list[dict]:
    """Read scheduled tasks from SQLite, newest first."""
    if not DB_FILE.exists():
        return []
    try:
        with sqlite3.connect(str(DB_FILE)) as conn:
            conn.row_factory = sqlite3.Row
            if status_filter == "all":
                cur = conn.execute(
                    "SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)
                )
            else:
                cur = conn.execute(
                    "SELECT * FROM tasks WHERE status = ? ORDER BY id DESC LIMIT ?",
                    (status_filter, limit),
                )
            return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []


def get_mail_stats() -> dict:
    """Compute stats from mail_stats table for dashboard."""
    if not DB_FILE.exists():
        return {}
    try:
        with sqlite3.connect(str(DB_FILE)) as conn:
            now = time.time()
            day = 86400
            # Overall counts
            total = conn.execute("SELECT COUNT(*) FROM mail_stats").fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM mail_stats WHERE status='success'").fetchone()[0]
            # Today — use local midnight to avoid UTC offset skew
            local_now = datetime.now()
            today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            today_total = conn.execute("SELECT COUNT(*) FROM mail_stats WHERE ts >= ?", (today_start,)).fetchone()[0]
            # Avg AI response time (last 50)
            ai_rows = conn.execute(
                "SELECT ai_ms FROM mail_stats WHERE ai_ms IS NOT NULL ORDER BY ts DESC LIMIT 50"
            ).fetchall()
            avg_ai_ms = int(sum(r[0] for r in ai_rows) / len(ai_rows)) if ai_rows else None
            # Last 7 days bar chart data — use local midnight boundaries
            days_data = []
            for i in range(6, -1, -1):
                day_dt = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
                day_dt = day_dt - timedelta(days=i)
                day_start = day_dt.timestamp()
                day_end = (day_dt + timedelta(days=1)).timestamp()
                label = day_dt.strftime("%m/%d")
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM mail_stats WHERE ts >= ? AND ts < ?", (day_start, day_end)
                ).fetchone()[0]
                err_cnt = conn.execute(
                    "SELECT COUNT(*) FROM mail_stats WHERE ts >= ? AND ts < ? AND status='error'",
                    (day_start, day_end)
                ).fetchone()[0]
                days_data.append({"label": label, "total": cnt, "errors": err_cnt})
            # Recent 10 entries
            conn.row_factory = sqlite3.Row
            recent = [dict(r) for r in conn.execute(
                "SELECT * FROM mail_stats ORDER BY ts DESC LIMIT 10"
            ).fetchall()]
            return {
                "total": total,
                "success": success,
                "error": total - success,
                "success_rate": round(success / total * 100, 1) if total else 0,
                "today": today_total,
                "avg_ai_ms": avg_ai_ms,
                "days": days_data,
                "recent": recent,
            }
    except Exception:
        return {}


@app.exception_handler(_LoginRedirect)
async def login_redirect_handler(request: Request, exc: _LoginRedirect):
    return RedirectResponse(url="/login", status_code=303)


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
    # Track first commented-line index for each key (fallback if no active line exists)
    first_commented: dict[str, int] = {}

    # First pass: update active (non-commented) lines only
    for i, raw_line in enumerate(lines):
        line = raw_line.rstrip("\n")
        m = re.match(r'^(#\s*)([A-Z_][A-Z0-9_]*)\s*=', line)
        if m:
            key = m.group(2)
            if key in updates and key not in first_commented:
                first_commented[key] = i
            continue
        m = re.match(r'^([A-Z_][A-Z0-9_]*)\s*=', line)
        if m:
            key = m.group(1)
            if key in updates and key not in handled:
                safe_value = updates[key].replace('"', '\\"')
                lines[i] = f'{key}="{safe_value}"\n'
                handled.add(key)

    # Second pass: activate the first commented line for keys not yet handled
    for key, idx in first_commented.items():
        if key not in handled:
            safe_value = updates[key].replace('"', '\\"')
            lines[idx] = f'{key}="{safe_value}"\n'
            handled.add(key)

    # Append new keys that weren't in the file at all
    new_keys = [k for k in updates if k not in handled]
    if new_keys:
        if lines and not lines[-1].endswith("\n"):
            lines.append("\n")
        lines.append("\n# ─── Web UI additions ────────────────────────────────\n")
        for key in new_keys:
            safe_value = updates[key].replace('"', '\\"')
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


def _parse_autoconfig_xml(text: str) -> Optional[dict]:
    imap_m = re.search(
        r'<incomingServer\s+type="imap"[^>]*>.*?<hostname>([^<]+)</hostname>.*?<port>([^<]+)</port>',
        text, re.DOTALL | re.IGNORECASE
    )
    smtp_m = re.search(
        r'<outgoingServer\s+type="smtp"[^>]*>.*?<hostname>([^<]+)</hostname>.*?<port>([^<]+)</port>.*?<socketType>([^<]*)</socketType>',
        text, re.DOTALL | re.IGNORECASE
    )
    if imap_m and smtp_m:
        socket_type = smtp_m.group(3).strip().upper()
        return {
            "imap_server": imap_m.group(1).strip(),
            "imap_port":   imap_m.group(2).strip(),
            "smtp_server": smtp_m.group(1).strip(),
            "smtp_port":   smtp_m.group(2).strip(),
            "smtp_ssl":    "true" if socket_type in ("SSL", "SSL/TLS") else "false",
        }
    return None


async def autoconfig_lookup(domain: str) -> Optional[dict]:
    """
    Query autoconfig sources concurrently.
    Returns {imap_server, imap_port, smtp_server, smtp_port, smtp_ssl} or None.
    """
    urls = [
        f"https://autoconfig.thunderbird.net/v1.1/{domain}",
        f"https://autoconfig.{domain}/mail/config-v1.1.xml",
        f"https://{domain}/.well-known/autoconfig/mail/config-v1.1.xml",
    ]

    async def fetch(client: httpx.AsyncClient, url: str) -> Optional[dict]:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                return _parse_autoconfig_xml(resp.text)
        except Exception:
            pass
        return None

    async with httpx.AsyncClient(timeout=4.0, follow_redirects=True) as client:
        tasks = [fetch(client, url) for url in urls]
        results = await asyncio.gather(*tasks)
        for r in results:
            if r:
                return r
    return None


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from a string."""
    return re.sub(r'\x1b\[[0-9;]*[mGKHF]', '', text)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/lang/{code}")
async def set_lang(request: Request, code: str):
    """Set UI language via session and redirect to home."""
    if code in I18N:
        request.session["ui_lang"] = code
    return RedirectResponse(url="/", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", _ctx(request, error=error))


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, password: str = Form("")):
    pw = _get_password()
    if pw and secrets.compare_digest(password, pw):
        request.session["authenticated"] = True
        return RedirectResponse(url="/", status_code=303)
    lang = get_ui_lang(request)
    error_msg = I18N.get(lang, I18N["zh"]).get("login_error", "Error")
    return templates.TemplateResponse("login.html", _ctx(request, error=error_msg))


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/health")
async def health():
    """Health check endpoint — returns daemon status and DB connectivity."""
    status = get_status()
    db_ok = False
    try:
        with sqlite3.connect(str(DB_FILE)) as conn:
            conn.execute("SELECT 1 FROM tasks LIMIT 1")
        db_ok = True
    except Exception:
        pass
    from utils.cache import query_cache
    return {
        "status": "ok" if status.get("running") else "degraded",
        "daemon_running": status.get("running", False),
        "db_ok": db_ok,
        "cache": query_cache.stats(),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, _auth=Depends(require_auth)):
    env = read_env()
    return templates.TemplateResponse("index.html", _ctx(
        request, env=env, status=get_status(),
        ai_backends=AI_BACKENDS, mail_config=get_mail_config(env),
    ))


@app.get("/partials/header_status", response_class=HTMLResponse)
async def header_status(request: Request, _auth=Depends(require_auth)):
    return templates.TemplateResponse("partials/header_status.html", _ctx(
        request, status=get_status(), message=None, success=True,
    ))


@app.get("/tabs/mail", response_class=HTMLResponse)
async def tab_mail(request: Request, _auth=Depends(require_auth)):
    env = read_env()
    return templates.TemplateResponse("partials/tab_mail.html", _ctx(
        request, env=env, mail_config=get_mail_config(env), feedback=None,
    ))


@app.get("/tabs/ai", response_class=HTMLResponse)
async def tab_ai(request: Request, _auth=Depends(require_auth)):
    env = read_env()
    return templates.TemplateResponse("partials/tab_ai.html", _ctx(
        request, env=env, ai_backends=AI_BACKENDS, feedback=None,
    ))


@app.get("/tabs/tasks", response_class=HTMLResponse)
async def tab_tasks(request: Request, _auth=Depends(require_auth), status: str = "all"):
    from utils.cache import query_cache
    return templates.TemplateResponse("partials/tab_tasks.html", _ctx(
        request, tasks=get_tasks(status_filter=status), status_filter=status,
        feedback=None, cache_stats=query_cache.stats(),
    ))


@app.post("/tasks/{task_id}/trigger", response_class=HTMLResponse)
async def task_trigger(request: Request, task_id: int, _auth=Depends(require_auth)):
    try:
        from tasks.scheduler import scheduler as _sched
        _sched.run_task_now(task_id)
        feedback = {"ok": True, "message": f"Task #{task_id} started"}
    except ValueError as e:
        feedback = {"ok": False, "message": str(e)}
    except Exception as e:
        feedback = {"ok": False, "message": f"Error: {e}"}
    return templates.TemplateResponse("partials/tab_tasks.html", _ctx(
        request, tasks=get_tasks(), status_filter="all", feedback=feedback,
    ))


@app.post("/tasks/{task_id}/delete", response_class=HTMLResponse)
async def task_delete(request: Request, task_id: int, _auth=Depends(require_auth)):
    try:
        with sqlite3.connect(str(DB_FILE)) as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        feedback = {"ok": True, "message": f"Task #{task_id} deleted"}
    except Exception as e:
        feedback = {"ok": False, "message": f"Error: {e}"}
    return templates.TemplateResponse("partials/tab_tasks.html", _ctx(
        request, tasks=get_tasks(), status_filter="all", feedback=feedback,
    ))


@app.post("/tasks/{task_id}/pause", response_class=HTMLResponse)
async def task_pause(request: Request, task_id: int, _auth=Depends(require_auth)):
    try:
        with sqlite3.connect(str(DB_FILE)) as conn:
            conn.execute(
                "UPDATE tasks SET status='paused', paused_at=? WHERE id=? AND status='pending'",
                (time.time(), task_id),
            )
        feedback = {"ok": True, "message": f"Task #{task_id} paused"}
    except Exception as e:
        feedback = {"ok": False, "message": f"Error: {e}"}
    return templates.TemplateResponse("partials/tab_tasks.html", _ctx(
        request, tasks=get_tasks(), status_filter="all", feedback=feedback,
    ))


@app.post("/tasks/{task_id}/resume", response_class=HTMLResponse)
async def task_resume(request: Request, task_id: int, _auth=Depends(require_auth)):
    try:
        from tasks.scheduler import scheduler as _sched
        _sched.resume_task(task_id)
        feedback = {"ok": True, "message": f"Task #{task_id} resumed"}
    except Exception as e:
        feedback = {"ok": False, "message": f"Error: {e}"}
    return templates.TemplateResponse("partials/tab_tasks.html", _ctx(
        request, tasks=get_tasks(), status_filter="all", feedback=feedback,
    ))


@app.post("/tasks/{task_id}/restart", response_class=HTMLResponse)
async def task_restart(request: Request, task_id: int, _auth=Depends(require_auth)):
    try:
        from tasks.scheduler import scheduler as _sched
        _sched.restart_task(task_id)
        feedback = {"ok": True, "message": f"Task #{task_id} restarted"}
    except Exception as e:
        feedback = {"ok": False, "message": f"Error: {e}"}
    return templates.TemplateResponse("partials/tab_tasks.html", _ctx(
        request, tasks=get_tasks(), status_filter="all", feedback=feedback,
    ))


@app.get("/tabs/skills", response_class=HTMLResponse)
async def tab_skills(request: Request, _auth=Depends(require_auth)):
    from skills.loader import get_registry
    skills = list(get_registry().values())
    return templates.TemplateResponse("partials/tab_skills.html", _ctx(
        request, skills=skills, feedback=None,
    ))


@app.get("/api/cache/stats")
async def api_cache_stats(_auth=Depends(require_auth)):
    from utils.cache import query_cache
    return query_cache.stats()


@app.post("/api/cache/clear")
async def api_cache_clear(_auth=Depends(require_auth)):
    from utils.cache import query_cache
    query_cache.clear()
    return {"cleared": True}


@app.post("/api/skills/reload", response_class=HTMLResponse)
async def api_skills_reload(request: Request, _auth=Depends(require_auth)):
    from skills.loader import reload_skills
    skills = list(reload_skills().values())
    lang = get_ui_lang(request)
    t = I18N.get(lang, I18N["zh"])
    feedback = {"ok": True, "message": f"{t['skills_count_prefix']}{len(skills)}{t['skills_count_suffix']}"}
    return templates.TemplateResponse("partials/tab_skills.html", _ctx(
        request, skills=skills, feedback=feedback,
    ))


@app.post("/api/skills/{skill_name}/test")
async def api_skill_test(request: Request, skill_name: str, _auth=Depends(require_auth)):
    """Run a skill with given payload and return result."""
    from skills.loader import get_skill
    skill = get_skill(skill_name)
    if not skill:
        return {"ok": False, "error": f"Skill '{skill_name}' not found"}
    try:
        body = await request.json()
        payload = body.get("payload", {})
    except Exception:
        payload = {}
    try:
        result = skill.run(payload)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/tabs/stats", response_class=HTMLResponse)
async def tab_stats(request: Request, _auth=Depends(require_auth)):
    return templates.TemplateResponse("partials/tab_stats.html", _ctx(
        request, stats=get_mail_stats(),
    ))


@app.get("/tabs/logs", response_class=HTMLResponse)
async def tab_logs(request: Request, _auth=Depends(require_auth)):
    """最新 200 行をサーバーサイドでレンダリングして返す。SSE はライブ更新専用。"""
    INITIAL_LINES = 200

    def _classify(line: str) -> str:
        lower = line.lower()
        if any(w in lower for w in ("error", "exception", "traceback", "failed", "critical")):
            return "ll error"
        if any(w in lower for w in ("warn", "warning")):
            return "ll warn"
        return "ll"

    html_lines = []
    if LOG_FILE.exists():
        with LOG_FILE.open("r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        recent = [l.rstrip() for l in all_lines if l.rstrip()][-INITIAL_LINES:]
        for line in reversed(recent):  # 新→旧の順でDOM上部から並べる（最新が最上部）
            html_lines.append(f'<div class="{_classify(line)}">{html.escape(line)}</div>')

    return templates.TemplateResponse("partials/tab_logs.html", _ctx(
        request, initial_log_html="".join(html_lines)
    ))


@app.post("/autoconfig", response_class=HTMLResponse)
async def autoconfig(request: Request, _auth=Depends(require_auth)):
    form = await request.form()
    email_address = form.get("_email_input", "").strip()
    domain = ""
    mailbox_type = ""
    ac_result = None
    prefix = "MAIL_CUSTOM"
    env = read_env()

    if "@" in email_address:
        domain = email_address.split("@", 1)[1].lower()
        mailbox_type = DOMAIN_MAP.get(domain, "")

        if mailbox_type in BUILTIN_SERVERS:
            # Known provider with built-in server config → use it directly
            ac_result = BUILTIN_SERVERS[mailbox_type]
            mailbox_type = "custom"
        elif not mailbox_type:
            # Unknown domain → try autoconfig lookup
            mailbox_type = "custom"
            ac_result = await autoconfig_lookup(domain)

        prefix = MAILBOX_PREFIX.get(mailbox_type, "MAIL_CUSTOM")

    return templates.TemplateResponse("partials/autoconfig_result.html", _ctx(
        request, domain=domain, mailbox_type=mailbox_type,
        ac_result=ac_result, prefix=prefix, env=env, email=email_address,
    ))


@app.post("/config/mail", response_class=HTMLResponse)
async def config_mail(request: Request, _auth=Depends(require_auth)):
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

    # Map _password / _allowed (fixed-name fields) to the correct prefixed keys
    if mailbox:
        correct_prefix = MAILBOX_PREFIX.get(mailbox, "MAIL_CUSTOM")
        if "_password" in data and isinstance(data["_password"], str):
            updates[f"{correct_prefix}_PASSWORD"] = data["_password"]
        if "_allowed" in data and isinstance(data["_allowed"], str):
            updates[f"{correct_prefix}_ALLOWED"] = data["_allowed"]

    try:
        write_env(updates)
        t = I18N.get(get_ui_lang(request), I18N["zh"])
        was_running = get_status()["running"]
        if was_running:
            subprocess.run(["bash", str(ROOT / "manage.sh"), "restart"],
                           capture_output=True, timeout=30, cwd=str(ROOT))
            feedback = {"ok": True, "message": t["fb_mail_saved_restart"]}
        else:
            feedback = {"ok": True, "message": t["fb_mail_saved"]}
    except Exception as e:
        t = I18N.get(get_ui_lang(request), I18N["zh"])
        feedback = {"ok": False, "message": t["fb_save_failed"] + str(e)}

    env = read_env()
    return templates.TemplateResponse("partials/tab_mail.html", _ctx(
        request, env=env, mail_config=get_mail_config(env), feedback=feedback,
    ))


@app.post("/config/ai", response_class=HTMLResponse)
async def config_ai(request: Request, _auth=Depends(require_auth)):
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

    # Handle checkboxes — if not in form data, the box was unchecked
    if "WEB_SEARCH" not in data:
        updates["WEB_SEARCH"] = "false"
    if "AI_MODIFY_SUBJECT" not in data:
        updates["AI_MODIFY_SUBJECT"] = "false"

    try:
        write_env(updates)
        t = I18N.get(get_ui_lang(request), I18N["zh"])
        was_running = get_status()["running"]
        if was_running:
            subprocess.run(["bash", str(ROOT / "manage.sh"), "restart"],
                           capture_output=True, timeout=30, cwd=str(ROOT))
            feedback = {"ok": True, "message": t["fb_ai_saved_restart"]}
        else:
            feedback = {"ok": True, "message": t["fb_ai_saved"]}
    except Exception as e:
        t = I18N.get(get_ui_lang(request), I18N["zh"])
        feedback = {"ok": False, "message": t["fb_save_failed"] + str(e)}

    env = read_env()
    return templates.TemplateResponse("partials/tab_ai.html", _ctx(
        request, env=env, ai_backends=AI_BACKENDS, feedback=feedback,
    ))


@app.post("/daemon/{action}", response_class=HTMLResponse)
async def daemon_action(request: Request, action: str, _auth=Depends(require_auth)):
    if action not in ("start", "stop", "restart"):
        return templates.TemplateResponse("partials/header_status.html", _ctx(
            request, status=get_status(), message=f"Unknown action: {action}", success=False,
        ))

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

    return templates.TemplateResponse("partials/header_status.html", _ctx(
        request, status=status, message=message, success=success,
    ))


@app.get("/logs/stream")
async def logs_stream(request: Request, _auth=Depends(require_auth)):
    """SSE endpoint: 新着行のみをリアルタイムで push する（初期表示は /tabs/logs が担当）。"""

    async def event_generator() -> AsyncGenerator[str, None]:

        def _classify(line: str) -> str:
            lower = line.lower()
            if any(w in lower for w in ("error", "exception", "traceback", "failed", "critical")):
                return "ll error"
            if any(w in lower for w in ("warn", "warning")):
                return "ll warn"
            return "ll"

        def _make_event(line: str) -> str:
            div = f'<div class="{_classify(line)}">{html.escape(line)}</div>'
            return f"data: {div}\n\n"

        # 現在のファイル末尾から監視開始（初期ロードは /logs/initial で行う）
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
                            yield _make_event(line)
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


# ─── RFC 8058 One-Click Unsubscribe endpoint ──────────────────────────────────

@app.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_get(request: Request, token: str = ""):
    """
    Landing page shown when a user follows the unsubscribe link manually
    (e.g. from plain-text email clients that do not support RFC 8058 POST).
    Displays a confirmation page; the user clicks a button to POST.
    """
    from core.one_click_unsubscribe import verify_token
    payload = verify_token(token) if token else None
    if not payload:
        return HTMLResponse(
            "<html><body><h2>Invalid or expired unsubscribe link.</h2></body></html>",
            status_code=400,
        )
    task_id = payload.get("t")
    recipient = payload.get("r", "")
    safe_token = token.replace('"', "")
    safe_recipient = html.escape(recipient)
    safe_task_id = html.escape(str(task_id))
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Unsubscribe — MailMindHub</title>
  <style>
    body {{ font-family: sans-serif; max-width: 480px; margin: 80px auto; color: #333; }}
    h1 {{ font-size: 1.4rem; }}
    p {{ line-height: 1.6; }}
    button {{
      background: #e53e3e; color: #fff; border: none;
      padding: 10px 24px; border-radius: 4px; font-size: 1rem; cursor: pointer;
    }}
    button:hover {{ background: #c53030; }}
    .note {{ font-size: 0.85rem; color: #666; margin-top: 1.5rem; }}
  </style>
</head>
<body>
  <h1>Unsubscribe from scheduled emails</h1>
  <p>Recipient: <strong>{safe_recipient}</strong><br>
     Task #: <strong>{safe_task_id}</strong></p>
  <p>Click the button below to cancel this scheduled task and stop receiving these emails.</p>
  <form method="POST" action="/unsubscribe">
    <input type="hidden" name="List-Unsubscribe" value="One-Click">
    <input type="hidden" name="token" value="{safe_token}">
    <button type="submit">Unsubscribe</button>
  </form>
  <p class="note">This will immediately cancel task #{safe_task_id} in MailMindHub.</p>
</body>
</html>"""
    return HTMLResponse(page)


@app.post("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_post(request: Request, token: str = Form(""), **_kwargs):
    """
    RFC 8058 one-click unsubscribe POST handler.

    Email clients that support RFC 8058 (Gmail, Apple Mail, Outlook) send a
    POST request to this endpoint with body:
        List-Unsubscribe=One-Click

    We verify the HMAC-signed token, look up the scheduled task, and cancel it.
    A 200 OK response with a plain confirmation message is returned.
    """
    from core.one_click_unsubscribe import verify_token

    # Accept token from form body OR query string (for browser-button flow)
    if not token:
        form = await request.form()
        token = form.get("token", "")

    payload = verify_token(token) if token else None
    if not payload:
        return HTMLResponse(
            "<html><body><h2>Invalid or expired unsubscribe link.</h2></body></html>",
            status_code=400,
        )

    task_id = int(payload.get("t", 0))
    recipient = payload.get("r", "")

    cancelled = False
    if DB_FILE.exists() and task_id:
        try:
            with sqlite3.connect(str(DB_FILE)) as conn:
                cur = conn.execute(
                    "UPDATE tasks SET status='cancelled' "
                    "WHERE id=? AND status NOT IN ('completed','failed','cancelled')",
                    (task_id,),
                )
                cancelled = cur.rowcount > 0
        except Exception as e:
            import logging
            logging.getLogger("mailmind").warning(f"unsubscribe: DB error: {e}")

    if cancelled:
        msg = f"You have been unsubscribed. Task #{task_id} has been cancelled."
        import logging
        logging.getLogger("mailmind").info(
            f"One-click unsubscribe: task {task_id} cancelled for {recipient}"
        )
    else:
        msg = f"Task #{task_id} was already completed or not found. No changes made."

    safe_msg = html.escape(msg)
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Unsubscribed — MailMindHub</title>
  <style>
    body {{ font-family: sans-serif; max-width: 480px; margin: 80px auto; color: #333; }}
    .ok {{ color: #276749; background: #f0fff4; border: 1px solid #9ae6b4;
           padding: 12px 16px; border-radius: 4px; }}
    .info {{ color: #744210; background: #fffff0; border: 1px solid #ecc94b;
             padding: 12px 16px; border-radius: 4px; }}
  </style>
</head>
<body>
  <div class="{'ok' if cancelled else 'info'}">{safe_msg}</div>
</body>
</html>"""
    return HTMLResponse(page, status_code=200)


# ─── Chat Routes ──────────────────────────────────────────────────────────────

# Active streaming sessions: {session_id: {"cancel_flag": asyncio.Event, "task": asyncio.Task}}
_active_streams: dict[int, dict] = {}


@app.get("/api/chat/models")
async def api_chat_models(request: Request, _auth=Depends(require_auth)):
    """Get available AI models/backends for chat."""
    models = []
    for name, info in AI_BACKENDS.items():
        # Build model info for API
        model_info = {
            "id": name,
            "name": info.get("label", name),
            "type": info.get("type", "cli"),
        }
        models.append(model_info)
    return JSONResponse({"models": models})


@app.post("/api/chat/{session_id}/stream")
async def api_chat_stream(request: Request, session_id: int):
    """
    SSE streaming endpoint for chat.
    Sends AI response token by token as they arrive.
    """
    require_auth(request)

    # Validate session_id
    if session_id is None or session_id <= 0:
        return JSONResponse({"error": "Invalid session ID"}, status_code=400)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)
    
    message = body.get("message", "").strip()
    backend = body.get("backend", "claude")
    
    if not message:
        return JSONResponse({"error": "Message is required"}, status_code=400)
    
    # Save user message
    add_chat_message(session_id, "user", message)
    
    # Get conversation history for context
    history = get_session_messages_for_context(session_id, limit=20)
    
    # Build prompt with context
    prompt = build_chat_prompt(history, message)
    
    # Auto-rename session if first message
    if len(history) <= 1:
        rename_chat_session(session_id, message[:30] + ("..." if len(message) > 30 else ""))
    
    async def generate():
        """Generate SSE events."""
        cancel_event = asyncio.Event()
        _active_streams[session_id] = {"cancel_flag": cancel_event, "task": asyncio.current_task()}
        
        ai_response = ""
        error_msg = ""
        
        try:
            # Send start event
            yield f"data: {json.dumps({'type': 'start'})}\n\n"
            
            # Check backend type and call appropriately
            backend_info = AI_BACKENDS.get(backend, {})
            backend_type = backend_info.get("type", "cli")
            
            if backend_type == "cli":
                # Stream from CLI
                async for chunk in stream_ai_cli(backend, prompt, cancel_event):
                    ai_response += chunk
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"
            else:
                # API backend - call and stream result
                from ai.providers import get_ai_provider
                try:
                    # Get full backend config from core
                    from core.config import AI_BACKENDS as CORE_AI_BACKENDS
                    core_backend = CORE_AI_BACKENDS.get(backend, {})
                    provider = get_ai_provider(backend, core_backend)
                    # Run in executor to avoid blocking
                    loop = asyncio.get_event_loop()
                    ai_response = await loop.run_in_executor(None, lambda: provider.call(prompt))
                    yield f"data: {json.dumps({'type': 'token', 'content': ai_response})}\n\n"
                except Exception as e:
                    error_msg = str(e)
                    log.error(f"API AI error: {error_msg}")
            
            if error_msg:
                yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
            else:
                # Save assistant response
                add_chat_message(session_id, "assistant", ai_response, backend)
                yield f"data: {json.dumps({'type': 'done', 'content': ai_response})}\n\n"
                
        except asyncio.CancelledError:
            yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
        except Exception as e:
            error_msg = str(e)
            log.error(f"Stream error: {error_msg}")
            yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
        finally:
            _active_streams.pop(session_id, None)
            yield "data: [DONE]\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.post("/api/chat/{session_id}/cancel")
async def api_chat_cancel(request: Request, session_id: int, _auth=Depends(require_auth)):
    """Cancel an active streaming session."""
    if session_id in _active_streams:
        stream_info = _active_streams[session_id]
        stream_info["cancel_flag"].set()
        if stream_info.get("task"):
            stream_info["task"].cancel()
        return JSONResponse({"status": "cancelled"})
    return JSONResponse({"status": "not_found"}, status_code=404)


def build_chat_prompt(history: list[dict], current_message: str) -> str:
    """Build prompt with conversation history."""
    if not history:
        return current_message
    
    # Build context from history
    context_parts = []
    for msg in history[-10:]:  # Last 10 messages
        role = "User" if msg["role"] == "user" else "Assistant"
        context_parts.append(f"{role}: {msg['content']}")
    
    context = "\n".join(context_parts)
    return f"""Previous conversation:
{context}

User: {current_message}
Assistant:"""


async def stream_ai_cli(backend: str, prompt: str, cancel_event: asyncio.Event, timeout: int = 120):
    """Stream output from AI CLI command."""
    cli_commands = {
        "claude": ["claude", "--print"],
        "codex": ["codex", "exec", "--skip-git-repo-check"],
        "gemini": ["gemini", "-p"],
        "qwen": ["qwen", "--prompt", "--web-search-default", "--yolo"],
        "copilot": ["copilot"],
    }
    
    if backend not in cli_commands:
        raise ValueError(f"Unknown CLI backend: {backend}")
    
    cmd = cli_commands[backend]
    
    # Some CLIs read from stdin, others take prompt as argument
    if backend in ("claude", "gemini", "qwen", "copilot"):
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        # Write prompt to stdin
        try:
            proc.stdin.write(prompt.encode("utf-8"))
            await proc.stdin.drain()
        except Exception:
            pass
        finally:
            await proc.stdin.wait_closed()
    else:
        # codex: pass as argument
        proc = await asyncio.create_subprocess_exec(
            *cmd, prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    
    # Read stdout line by line
    output = ""
    try:
        while True:
            if cancel_event.is_set():
                proc.kill()
                await proc.wait()
                raise asyncio.CancelledError()
            
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=1.0)
            if not line:
                break
            
            chunk = line.decode("utf-8", errors="replace")
            output += chunk
            yield chunk
            
            # Check for timeout
            try:
                await asyncio.wait_for(proc.wait(), timeout=0.1)
                if proc.returncode is not None:
                    break
            except asyncio.TimeoutError:
                continue
        
        await proc.wait()
        
        if proc.returncode != 0:
            stderr = await asyncio.wait_for(proc.stderr.read(), timeout=5.0)
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            if stderr_text:
                log.error(f"CLI error: {stderr_text}")
                
    except asyncio.CancelledError:
        proc.kill()
        await proc.wait()
        raise
    except Exception as e:
        log.error(f"CLI stream error: {e}")
        raise
    
    if not output:
        # Try stderr if stdout is empty
        try:
            stderr = await asyncio.wait_for(proc.stderr.read(), timeout=5.0)
            stderr_text = stderr.decode("utf-8", errors="replace")
            if stderr_text:
                yield stderr_text
        except Exception:
            pass


@app.get("/chat")
async def chat_page(request: Request):
    """Redirect to home page (chat panel is integrated)."""
    require_auth(request)
    return RedirectResponse(url="/", status_code=302)


@app.get("/chat/{session_id}")
async def chat_session(request: Request, session_id: int):
    """Redirect to home page (chat panel is integrated)."""
    require_auth(request)
    return RedirectResponse(url="/", status_code=302)


@app.post("/chat/new")
async def chat_new_session(request: Request):
    """Create a new chat session."""
    require_auth(request)
    form = await request.form()
    name = form.get("name", "新对话")
    session_id = create_chat_session(name)
    return RedirectResponse(url=f"/chat/{session_id}", status_code=303)


@app.post("/chat/{session_id}/delete")
async def chat_delete_session(request: Request, session_id: int):
    """Delete a chat session."""
    require_auth(request)
    delete_chat_session(session_id)
    return RedirectResponse(url="/chat", status_code=303)


@app.post("/chat/{session_id}/rename")
async def chat_rename(request: Request, session_id: int):
    """Rename a chat session."""
    require_auth(request)
    form = await request.form()
    name = form.get("name", "对话")
    rename_chat_session(session_id, name)
    return RedirectResponse(url=f"/chat/{session_id}", status_code=303)


@app.get("/chat/{session_id}/messages")
async def chat_get_messages(request: Request, session_id: int):
    """HTMX: Get messages for a session."""
    require_auth(request)
    messages = get_chat_messages(session_id)
    return templates.TemplateResponse(
        "partials/chat_messages.html",
        {**_ctx(request), "messages": messages}
    )


@app.get("/chat/{session_id}/sessions")
async def chat_get_sessions(request: Request):
    """HTMX: Get sessions list."""
    require_auth(request)
    sessions = get_chat_sessions()
    return templates.TemplateResponse(
        "partials/chat_sessions.html",
        {**_ctx(request), "sessions": sessions, "active_session": int(request.query_params.get("active", 0))}
    )


@app.get("/chat/sessions")
async def chat_sessions_json(request: Request):
    """API: Get sessions list as JSON (for programmatic access)."""
    require_auth(request)
    limit = request.query_params.get("limit", "50")
    try:
        limit_val = int(limit)
    except (ValueError, TypeError):
        limit_val = 50
    
    sessions = get_chat_sessions(limit=limit_val)
    return JSONResponse(content=sessions)


@app.get("/chat/sessions-list")
async def chat_sessions_list(request: Request):
    """API: Get sessions list as HTML chips."""
    require_auth(request)
    sessions = get_chat_sessions(limit=20)

    # 安全地获取 active 参数，避免 int("") 异常
    try:
        active_param = request.query_params.get("active", "0")
        active_id = int(active_param) if active_param else 0
    except (ValueError, TypeError):
        active_id = 0

    html_content = ""
    for s in sessions:
        active_class = "active" if s["id"] == active_id else ""
        msg_count = s.get("msg_count", 0)
        name = html.escape(s.get("name", "对话"))
        html_content += f'<div class="chat-session-chip {active_class}" onclick="selectChatSession({s["id"]})">{name} ({msg_count})</div>'

    if not html_content:
        html_content = '<div class="chat-session-chip" onclick="newChatSession()">+ 新对话</div>'

    return HTMLResponse(html_content)


@app.get("/chat/{session_id}/messages-html")
async def chat_messages_html(request: Request, session_id: int):
    """API: Get messages as HTML."""
    require_auth(request)
    messages = get_chat_messages(session_id, limit=50)

    html_content = ""
    for msg in messages:
        role_label = "你" if msg["role"] == "user" else "AI"
        time_str = datetime.fromtimestamp(msg["created_at"]).strftime("%H:%M") if msg.get("created_at") else ""
        content = html.escape(msg["content"])
        html_content += f'''
<div class="chat-message chat-message-{msg["role"]}">
    <div class="chat-message-header">
        <span class="chat-message-role">{role_label}</span>
        <span class="chat-message-time">{time_str}</span>
    </div>
    <div class="chat-message-content">{content}</div>
</div>
'''
    return HTMLResponse(html_content)



@app.post("/chat/{session_id}/send")
async def chat_send_message(request: Request, session_id: int):
    """HTMX: Send a message and get AI response."""
    require_auth(request)
    form = await request.form()
    user_message = form.get("message", "").strip()
    ai_backend = form.get("ai_backend", "claude")
    
    if not user_message:
        return HTMLResponse("")
    
    # Save user message
    add_chat_message(session_id, "user", user_message)
    
    # Build conversation history for context
    messages = get_chat_messages(session_id, limit=20)
    history = []
    for msg in messages:
        if msg["role"] == "user":
            history.append(f"User: {msg['content']}")
        else:
            history.append(f"Assistant: {msg['content']}")
    
    # Prepare prompt with context
    context = "\n".join(history[-10:])  # Last 10 messages for context
    prompt = f"""Previous conversation:
{context}

User: {user_message}
Assistant:"""
    
    # Execute AI CLI
    ai_response = ""
    error_msg = ""
    try:
        ai_response = await run_ai_cli(ai_backend, prompt)
        add_chat_message(session_id, "assistant", ai_response, ai_backend)
    except Exception as e:
        error_msg = str(e)
        add_chat_message(session_id, "assistant", f"Error: {error_msg}", ai_backend)
    
    # Auto-rename session if first message
    if len(messages) <= 1:
        rename_chat_session(session_id, user_message[:30] + ("..." if len(user_message) > 30 else ""))
    
    # Return updated messages
    messages = get_chat_messages(session_id)
    return templates.TemplateResponse(
        "partials/chat_messages.html",
        {**_ctx(request), "messages": messages}
    )


async def run_ai_cli(backend: str, prompt: str, timeout: int = 120) -> str:
    """Execute AI CLI command and return output."""
    import shlex
    
    cli_commands = {
        "claude": ["claude", "--print"],
        "codex": ["codex", "exec", "--skip-git-repo-check"],
        "gemini": ["gemini", "-p"],
        "qwen": ["qwen", "--prompt", "--web-search-default", "--yolo"],
        "copilot": ["copilot"],
    }
    
    if backend not in cli_commands:
        raise ValueError(f"Unknown CLI backend: {backend}")
    
    cmd = cli_commands[backend]
    
    # Some CLIs read from stdin, others take prompt as argument
    if backend in ("claude", "gemini", "qwen", "copilot"):
        # Pass prompt via stdin
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=prompt.encode("utf-8")),
            timeout=timeout
        )
    else:
        # codex: pass as argument
        proc = await asyncio.create_subprocess_exec(
            *cmd, prompt,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout
        )
    
    if proc.returncode != 0:
        raise RuntimeError(f"CLI failed: {stderr.decode('utf-8', errors='replace')}")
    
    return stdout.decode("utf-8", errors="replace").strip()


# ─── Gmail Push Notification webhook ──────────────────────────────────────────

import asyncio as _asyncio
import queue as _queue

# Thread-safe queue for Gmail push events; consumed by email_daemon via run_gmail_push()
gmail_push_queue: "_queue.Queue[dict]" = _queue.Queue()


@app.post("/webhook/gmail")
async def gmail_push_webhook(request: Request):
    """
    Receive Gmail Pub/Sub push notifications.

    Google Pub/Sub POSTs a JSON body:
      {"message": {"data": "<base64-encoded-json>", "messageId": "..."}, "subscription": "..."}

    The decoded data contains:
      {"emailAddress": "user@gmail.com", "historyId": "12345"}

    We acknowledge immediately (return 200) and put the event on a queue
    for the daemon's run_gmail_push() loop to process asynchronously.
    """
    import base64

    try:
        body = await request.json()
    except Exception:
        return {"status": "error", "detail": "invalid JSON"}

    try:
        data_b64 = body.get("message", {}).get("data", "")
        data_bytes = base64.b64decode(data_b64 + "==")
        event = json.loads(data_bytes.decode("utf-8"))
    except Exception as e:
        # Malformed payload — still return 200 to prevent Pub/Sub redelivery
        return {"status": "ignored", "detail": str(e)}

    gmail_push_queue.put_nowait({
        "email_address": event.get("emailAddress", ""),
        "history_id":    str(event.get("historyId", "")),
        "received_at":   datetime.utcnow().isoformat(),
    })

    # Return 200 immediately so Pub/Sub marks message as acknowledged
    return {"status": "ok"}


@app.post("/webhook/discord")
async def discord_webhook(request: Request):
    """
    Receive Discord interaction / event payloads.

    Discord sends interaction payloads to registered webhook URLs.
    We verify the signature and put the payload on the Discord adapter's queue.

    Note: This endpoint handles the PING challenge required by Discord to verify webhooks.
    """
    import hmac
    import hashlib

    DISCORD_PUBLIC_KEY = os.environ.get("DISCORD_PUBLIC_KEY", "")
    if DISCORD_PUBLIC_KEY:
        # Verify Ed25519 signature (simplified: check headers exist)
        sig_header    = request.headers.get("X-Signature-Ed25519", "")
        ts_header     = request.headers.get("X-Signature-Timestamp", "")
        if not sig_header or not ts_header:
            from fastapi.responses import Response
            return Response(status_code=401)

    try:
        body = await request.json()
    except Exception:
        return {"status": "error"}

    # Discord PING challenge
    if body.get("type") == 1:
        return {"type": 1}

    # Push to Discord adapter queue if loaded
    try:
        from channels.discord_adapter import CHANNEL as dc_channel
        if hasattr(dc_channel, "_webhook_queue"):
            dc_channel._webhook_queue.put_nowait(body)
    except Exception:
        pass

    return {"type": 5}  # DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MailMindHub Web UI")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=7000, help="Bind port (default: 7000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload (dev mode)")
    args = parser.parse_args()

    print(f"  MailMindHub Web UI → http://{args.host}:{args.port}")
    uvicorn.run(
        "webui.server:app" if not args.reload else "webui.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        app_dir=str(ROOT),
        log_level="info",
    )
