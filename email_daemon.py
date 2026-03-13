#!/usr/bin/env python3
"""
MailMind — 邮件 → AI 守护进程
支持多邮箱（含 OAuth）、多AI（CLI/API）、白名单、AI自动生成回复标题
用法: python email_daemon.py [--mailbox NAME] [--ai NAME] [--list]
"""

import imaplib
import smtplib
import email
import subprocess
import time
import logging
import os
import sys
import argparse
import json
import re
import requests
import threading
from html import unescape
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import decode_header as _decode_header
from email.utils import parseaddr

# ═══════════════════════════════════════════════════════════════
#  邮箱配置
# ═══════════════════════════════════════════════════════════════

MAILBOXES = {
    "126": {
        "address":         os.environ.get("MAIL_126_ADDRESS", ""),
        "password":        os.environ.get("MAIL_126_PASSWORD", ""),
        "imap_server":     "imap.126.com",
        "imap_port":       993,
        "smtp_server":     "smtp.126.com",
        "smtp_port":       465,
        "smtp_ssl":        True,
        "imap_id":         True,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_126_ALLOWED", "").split(",") if s.strip()],
    },
    "163": {
        "address":         os.environ.get("MAIL_163_ADDRESS", ""),
        "password":        os.environ.get("MAIL_163_PASSWORD", ""),
        "imap_server":     "imap.163.com",
        "imap_port":       993,
        "smtp_server":     "smtp.163.com",
        "smtp_port":       465,
        "smtp_ssl":        True,
        "imap_id":         True,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_163_ALLOWED", "").split(",") if s.strip()],
    },
    "qq": {
        "address":         os.environ.get("MAIL_QQ_ADDRESS", ""),
        "password":        os.environ.get("MAIL_QQ_PASSWORD", ""),
        "imap_server":     "imap.qq.com",
        "imap_port":       993,
        "smtp_server":     "smtp.qq.com",
        "smtp_port":       465,
        "smtp_ssl":        True,
        "imap_id":         False,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_QQ_ALLOWED", "").split(",") if s.strip()],
    },
    "gmail": {
        "address":         os.environ.get("MAIL_GMAIL_ADDRESS", ""),
        "password":        os.environ.get("MAIL_GMAIL_PASSWORD", ""),
        "imap_server":     "imap.gmail.com",
        "imap_port":       993,
        "smtp_server":     "smtp.gmail.com",
        "smtp_port":       465,
        "smtp_ssl":        True,
        "imap_id":         False,
        "auth":            "oauth_google",
        "oauth_token_file": os.path.join(os.path.dirname(__file__), "token_gmail.json"),
        "oauth_creds_file": os.path.join(os.path.dirname(__file__), "credentials_gmail.json"),
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_GMAIL_ALLOWED", "").split(",") if s.strip()],
    },
    "outlook": {
        "address":         os.environ.get("MAIL_OUTLOOK_ADDRESS", ""),
        "imap_server":     "outlook.office365.com",
        "imap_port":       993,
        "smtp_server":     "smtp.office365.com",
        "smtp_port":       587,
        "smtp_ssl":        False,
        "imap_id":         False,
        "auth":            "oauth_microsoft",
        "oauth_token_file": os.path.join(os.path.dirname(__file__), "token_outlook.json"),
        "oauth_client_id":  os.environ.get("OUTLOOK_CLIENT_ID", ""),
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_OUTLOOK_ALLOWED", "").split(",") if s.strip()],
    },
    "icloud": {
        "address":         os.environ.get("MAIL_ICLOUD_ADDRESS", ""),
        "password":        os.environ.get("MAIL_ICLOUD_PASSWORD", ""),  # App-specific password
        "imap_server":     "imap.mail.me.com",
        "imap_port":       993,
        "smtp_server":     "smtp.mail.me.com",
        "smtp_port":       587,
        "smtp_ssl":        False,
        "imap_id":         False,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_ICLOUD_ALLOWED", "").split(",") if s.strip()],
    },
    "proton": {
        "address":         os.environ.get("MAIL_PROTON_ADDRESS", ""),
        "password":        os.environ.get("MAIL_PROTON_PASSWORD", ""),  # Bridge password
        "imap_server":     "127.0.0.1",
        "imap_port":       1143,
        "smtp_server":     "127.0.0.1",
        "smtp_port":       1025,
        "smtp_ssl":        False,
        "imap_id":         False,
        "auth":            "password",
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_PROTON_ALLOWED", "").split(",") if s.strip()],
    },
}

# ═══════════════════════════════════════════════════════════════
#  AI 配置
# ═══════════════════════════════════════════════════════════════

def _copilot_cmd() -> str:
    """查找 GitHub Copilot CLI 可执行文件路径"""
    env_cmd = os.environ.get("COPILOT_CMD", "")
    if env_cmd:
        return env_cmd
    bundled = os.path.expanduser(
        "~/.vscode-server/data/User/globalStorage/github.copilot-chat/copilotCli/copilot"
    )
    if os.path.isfile(bundled):
        return bundled
    return "copilot"


AI_BACKENDS = {
    "claude":      {"type": "cli", "cmd": os.environ.get("CLAUDE_CMD", "claude"), "args": ["--print"]},
    "codex":       {"type": "cli", "cmd": os.environ.get("CODEX_CMD",  "codex"),  "args": ["exec", "--skip-git-repo-check"]},
    "gemini":      {"type": "cli", "cmd": os.environ.get("GEMINI_CMD", "gemini"), "args": ["-p"]},
    "qwen":        {"type": "cli", "cmd": os.environ.get("QWEN_CMD",   "qwen"),   "args": ["--prompt"]},
    "anthropic":   {"type": "api_anthropic", "api_key": os.environ.get("ANTHROPIC_API_KEY", ""),  "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")},
    "openai":      {"type": "api_openai",    "api_key": os.environ.get("OPENAI_API_KEY", ""),     "model": os.environ.get("OPENAI_MODEL",     "gpt-4o"),            "url": "https://api.openai.com/v1/chat/completions"},
    "gemini-api":  {"type": "api_gemini",    "api_key": os.environ.get("GEMINI_API_KEY", ""),     "model": os.environ.get("GEMINI_MODEL",     "gemini-3-flash-preview")},
    "qwen-api":    {"type": "api_qwen",      "api_key": os.environ.get("QWEN_API_KEY", ""),       "model": os.environ.get("QWEN_MODEL",       "qwen-max")},
    "deepseek":    {"type": "api_openai",    "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),   "model": os.environ.get("DEEPSEEK_MODEL",    "deepseek-chat"),     "url": "https://api.deepseek.com/v1/chat/completions"},
    "copilot":     {"type": "cli_copilot",   "cmd": _copilot_cmd()},
}


# ────────────────────────────────────────────────────────────────
#  Web Search / Weather / News 配置
# ────────────────────────────────────────────────────────────────

WEB_SEARCH_ENABLED = os.environ.get("WEB_SEARCH", "false").lower() == "true"
WEB_SEARCH_ENGINE = os.environ.get("WEB_SEARCH_ENGINE", "duckduckgo")  # duckduckgo / google / bing
SEARCH_RESULTS_COUNT = int(os.environ.get("SEARCH_RESULTS_COUNT", "5"))
WEB_SEARCH_TIMEOUT = int(os.environ.get("WEB_SEARCH_TIMEOUT", "10"))

WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")
WEATHER_DEFAULT_LOCATION = os.environ.get("WEATHER_DEFAULT_LOCATION", "Tokyo")

NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
NEWS_DEFAULT_QUERY = os.environ.get("NEWS_DEFAULT_QUERY", "technology OR AI")
NEWS_DEFAULT_LANGUAGE = os.environ.get("NEWS_DEFAULT_LANGUAGE", "zh")
NEWS_DEFAULT_COUNTRY = os.environ.get("NEWS_DEFAULT_COUNTRY", "")
NEWS_DEFAULT_PAGE_SIZE = int(os.environ.get("NEWS_DEFAULT_PAGE_SIZE", "8"))

# 搜索提示词模板
WEB_SEARCH_PROMPT = """
【网络搜索结果】（来自 {engine}，共 {count} 条）：
{search_results}

---
以上为网络搜索结果，请结合上述信息回答用户的问题。
"""


def web_search(query: str, num_results: int = 5, engine: str | None = None) -> list:
    """
    执行网络搜索，返回搜索结果列表
    """
    results = []
    engine = (engine or WEB_SEARCH_ENGINE).lower().strip()

    if engine == "duckduckgo":
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            url = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_html=1"
            resp = requests.get(url, headers=headers, timeout=WEB_SEARCH_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("Heading", "摘要"),
                    "snippet": data.get("AbstractText", ""),
                    "url": data.get("AbstractURL", "")
                })
            for item in data.get("RelatedTopics", [])[:num_results]:
                if isinstance(item, dict) and "Text" in item:
                    results.append({
                        "title": item.get("Text", "")[:100] + "...",
                        "snippet": item.get("Text", ""),
                        "url": item.get("FirstURL", "")
                    })
        except Exception as e:
            log.warning(f"DuckDuckGo 搜索失败：{e}")
            
    elif engine == "wikipedia":
        try:
            lang = os.environ.get('WIKIPEDIA_LANG', 'zh')
            url = f"https://{lang}.wikipedia.org/w/api.php"
            params = {"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": num_results}
            headers = {"User-Agent": "MailMind/1.0"}
            resp = requests.get(url, params=params, headers=headers, timeout=WEB_SEARCH_TIMEOUT)
            data = resp.json()
            for item in data.get("query", {}).get("search", [])[:num_results]:
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", "").replace('<span class="searchmatch">', '').replace('</span>', ''),
                    "url": f"https://{lang}.wikipedia.org/wiki/{item.get('title', '')}"
                })
        except Exception as e:
            log.warning(f"Wikipedia 搜索失败：{e}")

    elif engine == "google":
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        cse_id = os.environ.get("GOOGLE_CSE_ID", "")
        if api_key and cse_id:
            try:
                url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cse_id}&q={requests.utils.quote(query)}"
                resp = requests.get(url, timeout=WEB_SEARCH_TIMEOUT)
                data = resp.json()
                for item in data.get("items", [])[:num_results]:
                    results.append({"title": item.get("title", ""), "snippet": item.get("snippet", ""), "url": item.get("link", "")})
            except Exception as e:
                log.warning(f"Google 搜索失败：{e}")
            
    elif engine == "bing":
        api_key = os.environ.get("BING_API_KEY", "")
        if api_key:
            try:
                url = f"https://api.bing.microsoft.com/v7.0/search?q={requests.utils.quote(query)}"
                headers = {"Ocp-Apim-Subscription-Key": api_key}
                resp = requests.get(url, headers=headers, timeout=WEB_SEARCH_TIMEOUT)
                data = resp.json()
                for item in data.get("webPages", {}).get("value", [])[:num_results]:
                    results.append({"title": item.get("name", ""), "snippet": item.get("snippet", ""), "url": item.get("url", "")})
            except Exception as e:
                log.warning(f"Bing 搜索失败：{e}")
    
    return results


def fetch_weather(location: str) -> str:
    if not WEATHER_API_KEY:
        return "⚠️ 未配置 WEATHER_API_KEY，无法获取天气。"
    loc = location or WEATHER_DEFAULT_LOCATION
    try:
        url = "https://api.weatherapi.com/v1/current.json"
        params = {"key": WEATHER_API_KEY, "q": loc, "lang": "zh"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        cur = data.get("current", {})
        loc_info = data.get("location", {})
        return (
            f"{loc_info.get('name', loc)} 天气：{cur.get('condition', {}).get('text', '')}，"
            f"气温 {cur.get('temp_c', 'N/A')}℃，体感 {cur.get('feelslike_c', 'N/A')}℃，"
            f"湿度 {cur.get('humidity', 'N/A')}%，风速 {cur.get('wind_kph', 'N/A')}km/h。"
        )
    except Exception as e:
        return f"⚠️ 天气获取失败：{e}"


def fetch_news(query: str | None = None, page_size: int | None = None, language: str | None = None, country: str | None = None, sources: str | None = None) -> str:
    if not NEWS_API_KEY:
        return "⚠️ 未配置 NEWS_API_KEY，无法获取新闻。"
    q = query or NEWS_DEFAULT_QUERY
    page_size = page_size or NEWS_DEFAULT_PAGE_SIZE
    language = (language or NEWS_DEFAULT_LANGUAGE).strip()
    country = (country or NEWS_DEFAULT_COUNTRY).strip()
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": q,
            "language": language if language else None,
            "pageSize": page_size,
            "sortBy": "publishedAt",
        }
        if sources:
            params["sources"] = sources
        if country:
            url = "https://newsapi.org/v2/top-headlines"
            params = {"q": q, "country": country, "pageSize": page_size}
        headers = {"X-Api-Key": NEWS_API_KEY}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("articles", [])[:page_size]
        if not items:
            return "没有找到相关新闻。"
        lines = []
        for i, it in enumerate(items, 1):
            title = it.get("title", "无标题")
            source = it.get("source", {}).get("name", "")
            url = it.get("url", "")
            lines.append(f"{i}. {title} ({source})\n   {url}")
        return "\n".join(lines)
    except Exception as e:
        return f"⚠️ 新闻获取失败：{e}"


def format_search_results(results: list) -> str:
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. 【{r.get('title', '无标题')}】\n   {r.get('snippet', '')}\n   链接：{r.get('url', '')}\n")
    return "\n".join(lines)


def search_web_if_needed(instruction: str) -> str:
    if not WEB_SEARCH_ENABLED:
        return ""
    search_keywords = ["搜索", "查找", "查询", "最新", "最近", "news", "search", "look up", "find"]
    if not any(kw in instruction.lower() for kw in search_keywords):
        return ""
    
    log.info("🔍 检测到搜索意图，执行网络搜索...")
    search_query = instruction[:50].replace("\n", " ").strip()
    results = web_search(search_query, SEARCH_RESULTS_COUNT)
    if results:
        return WEB_SEARCH_PROMPT.format(engine=WEB_SEARCH_ENGINE, count=len(results), search_results=format_search_results(results))
    return ""


def _parse_time_hhmm(text: str):
    m = re.search(r"(\d{1,2})[:：](\d{2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})\s*点(?:半)?", text)
    if m:
        h = int(m.group(1))
        if "半" in m.group(0):
            return h, 30
        return h, 0
    return None, None


def _next_weekday(base: datetime, weekday: int):
    days_ahead = (weekday - base.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return base + timedelta(days=days_ahead)


def _parse_schedule_from_text(text: str):
    low = text.lower()
    schedule_at = None
    schedule_every = None
    schedule_until = None

    rel_min = re.search(r"(?:每|every|毎|매)\s*(\d+)\s*(分钟|min|minutes|分|분)", low)
    rel_hour = re.search(r"(?:每|every|毎|매)\s*(\d+)\s*(小时|hour|hours|h|時間|시간)", low)
    rel_day = re.search(r"(?:每|every|毎|매)\s*(\d+)\s*(天|day|days|d|日|일)", low)
    if rel_min:
        schedule_every = f"{rel_min.group(1)}m"
    elif rel_hour:
        schedule_every = f"{rel_hour.group(1)}h"
    elif rel_day:
        schedule_every = f"{rel_day.group(1)}d"

    if any(k in text for k in ["每天", "毎日", "매일"]) and not schedule_every:
        schedule_every = "1d"

    if any(k in text for k in ["每周", "毎週", "매주"]) and not schedule_every:
        schedule_every = "7d"

    date_time = re.search(r"(\d{4}-\d{2}-\d{2})(?:\s*[tT ]\s*(\d{1,2}:\d{2}))?", low)
    if date_time:
        d = date_time.group(1)
        t = date_time.group(2) or "09:00"
        schedule_at = f"{d}T{t}:00"

    until_match = re.search(r"(?:截止|直到|until)\s*(\d{4}-\d{2}-\d{2}(?:[tT ]\d{1,2}:\d{2})?)", low)
    if until_match:
        schedule_until = until_match.group(1).replace(" ", "T")

    now = datetime.now()
    if not schedule_at:
        if any(k in text for k in ["今天", "今日", "今日", "오늘"]):
            h, m = _parse_time_hhmm(text)
            if h is not None:
                dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if dt <= now:
                    dt = dt + timedelta(days=1)
                schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["明天", "明日", "明日", "내일"]):
            h, m = _parse_time_hhmm(text)
            h = 9 if h is None else h
            m = 0 if m is None else m
            dt = (now + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
            schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["今晚", "今夜", "晚上", "今晚", "오늘 밤", "저녁"]):
            h, m = _parse_time_hhmm(text)
            h = 20 if h is None else h
            m = 0 if m is None else m
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if dt <= now:
                dt = dt + timedelta(days=1)
            schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["早上", "上午", "朝", "午前", "아침", "오전"]):
            h, m = _parse_time_hhmm(text)
            h = 9 if h is None else h
            m = 0 if m is None else m
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if dt <= now:
                dt = dt + timedelta(days=1)
            schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["下午", "午後", "오후"]):
            h, m = _parse_time_hhmm(text)
            h = 15 if h is None else h
            m = 0 if m is None else m
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if dt <= now:
                dt = dt + timedelta(days=1)
            schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["每周", "毎週", "매주"]):
            weekday_map = {
                "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
                "月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日曜": 6, "日": 6,
                "월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6,
            }
            m = re.search(r"(?:每周|毎週|매주)([一二三四五六日天月火水木金土日曜월화수목금토일])", text)
            if m:
                target = weekday_map[m.group(1)]
                h, m2 = _parse_time_hhmm(text)
                h = 9 if h is None else h
                m2 = 0 if m2 is None else m2
                dt = _next_weekday(now, target).replace(hour=h, minute=m2, second=0, microsecond=0)
                schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["每天", "毎日", "매일"]):
            h, m = _parse_time_hhmm(text)
            if h is not None:
                dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if dt <= now:
                    dt = dt + timedelta(days=1)
                schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")

    return schedule_at, schedule_every, schedule_until


def auto_detect_task(instruction: str):
    low = instruction.lower()
    task_type = None
    payload = {}
    output = {}

    if any(k in low for k in ["天气", "weather", "天気", "날씨"]):
        task_type = "weather"
        m = re.search(r"(?:天气|weather|天気|날씨)[：: ]?([^\n，,;；]+)", instruction, re.I)
        if m:
            payload["location"] = m.group(1).strip()
    if any(k in low for k in ["新闻", "news", "ニュース", "뉴스"]):
        task_type = "news"
        m = re.search(r"(?:新闻|news|ニュース|뉴스)[：: ]?([^\n，,;；]+)", instruction, re.I)
        if m:
            payload["query"] = m.group(1).strip()
    if any(k in low for k in ["检索", "搜索", "网页", "search", "look up", "find", "検索", "검색"]):
        task_type = "web_search"
        m = re.search(r"(?:检索|搜索|网页检索|search|look up|find|検索|검색)[：: ]?([^\n]+)", instruction, re.I)
        if m:
            payload["query"] = m.group(1).strip()
    if any(k in low for k in ["日报", "周报", "月报", "report", "summary", "レポート", "보고서", "리포트"]):
        task_type = "report"
        if any(k in low for k in ["天气", "weather", "天気", "날씨"]):
            payload["weather_locations"] = [WEATHER_DEFAULT_LOCATION]
        if any(k in low for k in ["新闻", "news", "ニュース", "뉴스"]):
            payload["news_query"] = NEWS_DEFAULT_QUERY
        m = re.search(r"(?:检索|搜索|网页检索|search|検索|검색)[：: ]?([^\n，,;；]+)", instruction, re.I)
        if m:
            payload["web_query"] = m.group(1).strip()
    if any(k in low for k in ["ai", "分析", "总结", "润色", "翻译", "生成", "分析", "要約", "翻訳", "生成", "분석", "요약", "번역", "생성"]):
        if not task_type:
            task_type = "ai_job"
        payload.setdefault("prompt", instruction.strip())

    if any(k in low for k in ["归档", "archive", "保存", "save", "保存", "アーカイブ", "저장", "아카이브"]):
        output["archive"] = True
        output["archive_dir"] = "reports"
    if any(k in low for k in ["仅归档", "no email", "不要发邮件", "メール不要", "메일 보내지", "이메일 필요없음"]):
        output["email"] = False

    schedule_at, schedule_every, schedule_until = _parse_schedule_from_text(instruction)
    return task_type, payload, output, schedule_at, schedule_every, schedule_until


def auto_detect_tasks(instruction: str):
    parts = [p.strip() for p in re.split(r"[；;\n]+", instruction) if p.strip()]
    tasks = []
    for part in parts:
        task_type, payload, output, sch_at, sch_every, sch_until = auto_detect_task(part)
        if task_type or sch_at or sch_every:
            tasks.append({
                "task_type": task_type or "email",
                "task_payload": payload or {},
                "output": output or {},
                "schedule_at": sch_at,
                "schedule_every": sch_every,
                "schedule_until": sch_until,
                "raw": part,
            })
    return tasks

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))

# ═══════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("mailmind")
processed_ids: set = set()
PROCESSED_IDS_PATH: str | None = None


def _default_processed_ids_path(mailbox_name: str) -> str:
    return os.path.join(os.path.dirname(__file__), f"processed_ids_{mailbox_name}.json")


def load_processed_ids(path: str) -> set:
    if not path or not os.path.isfile(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(str(x) for x in data) if isinstance(data, list) else set()
    except Exception as e:
        log.warning(f"读取 processed_ids 失败：{e}")
        return set()


def save_processed_ids(path: str, ids: set):
    if not path: return
    try:
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(sorted(ids), f, indent=2)
        os.replace(path + ".tmp", path)
    except Exception as e:
        log.warning(f"保存 processed_ids 失败：{e}")


def is_sender_allowed(sender_email: str, allowed: list) -> bool:
    if not allowed: return True
    sender_email = (sender_email or "").strip().lower()
    if "@" not in sender_email: return False
    _, _, sender_domain = sender_email.rpartition("@")
    for entry in allowed:
        rule = (entry or "").strip().lower()
        if not rule: continue
        if "@" in rule and not rule.startswith("@"):
            if sender_email == rule: return True
        else:
            if rule.startswith("@"): rule = rule[1:]
            if sender_domain == rule: return True
    return False


# ═══════════════════════════════════════════════════════════════
#  任务调度器 (定时任务)
# ═══════════════════════════════════════════════════════════════

class TaskScheduler:
    def __init__(self, filename="tasks.json"):
        self.filename = os.path.join(os.path.dirname(__file__), filename)
        self.tasks = []
        self.lock = threading.Lock()
        self.load_tasks()

    def load_tasks(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r", encoding="utf-8") as f:
                    self.tasks = json.load(f)
            except Exception as e:
                log.error(f"加载任务失败: {e}")

    def save_tasks(self):
        try:
            with open(self.filename, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"保存任务失败: {e}")

    def _parse_datetime(self, value: str):
        if not value: return None
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()

    def _parse_duration(self, value: str):
        if not value: return None
        s = value.strip().lower()
        if s.isdigit(): return int(s)
        m = re.fullmatch(r"(\d+)\s*([smhd])", s)
        if not m: return None
        num = int(m.group(1))
        unit = m.group(2)
        return num * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]

    def add_task(
        self,
        mailbox_name,
        to,
        subject,
        body,
        schedule_at: str = None,
        schedule_every: str = None,
        schedule_until: str = None,
        task_type: str = "email",
        task_payload: dict | None = None,
        output: dict | None = None,
        attachments: list | None = None,
    ):
        try:
            interval = self._parse_duration(schedule_every)
            until_ts = self._parse_datetime(schedule_until)

            if schedule_at:
                if schedule_at.isdigit():
                    trigger_time = time.time() + int(schedule_at)
                else:
                    trigger_time = self._parse_datetime(schedule_at)
            else:
                trigger_time = time.time()

            if trigger_time is None:
                raise ValueError("schedule_at 无法解析")
            if schedule_every and interval is None:
                raise ValueError("schedule_every 无法解析")

            with self.lock:
                self.tasks.append({
                    "mailbox_name": mailbox_name,
                    "to": to,
                    "subject": subject,
                    "body": body,
                    "trigger_time": trigger_time,
                    "interval_seconds": interval,
                    "until_time": until_ts,
                    "type": task_type or "email",
                    "payload": task_payload or {},
                    "output": output or {},
                    "attachments": attachments or [],
                })
                self.save_tasks()
            log.info(f"📅 任务已安排：[{subject}] 将在 {datetime.fromtimestamp(trigger_time)} 发送")
            return True
        except Exception as e:
            log.error(f"安排任务失败: {e}")
            return False

    def run_forever(self):
        log.info("⏰ 任务调度器已启动")
        while True:
            now = time.time()
            due_tasks = []
            with self.lock:
                new_tasks = []
                for t in self.tasks:
                    if now >= t["trigger_time"]: due_tasks.append(t)
                    else: new_tasks.append(t)
                if due_tasks:
                    self.tasks = new_tasks
                    self.save_tasks()
            for t in due_tasks:
                try:
                    log.info(f"🔔 执行定时任务：[{t['subject']}] -> {t['to']}")
                    execute_task(t)
                    interval = t.get("interval_seconds")
                    if interval:
                        next_time = time.time() + interval
                        until_time = t.get("until_time")
                        if not until_time or next_time <= until_time:
                            with self.lock:
                                t["trigger_time"] = next_time
                                self.tasks.append(t)
                                self.save_tasks()
                except Exception as e:
                    log.error(f"执行任务出错: {e}")
            time.sleep(10)

scheduler = TaskScheduler()

PROMPT_TEMPLATE = """\
你正在通过邮件接收用户指令。以下是用户发来的邮件，请执行其中的任务。

{instruction}

请严格按以下 JSON 格式回复，不要输出任何其他内容：
{{"subject": "根据回复内容拟定的简短邮件标题",
  "body": "回复正文内容",
  "schedule_at": "可选：触发时间(ISO格式或相对秒数)",
  "schedule_every": "可选：重复间隔(秒或5m/2h)",
  "schedule_until": "可选：截止时间(ISO格式)",
  "attachments": [{{"filename": "文件名.txt", "content": "文件内容"}}],
  "task_type": "可选：email|ai_job|weather|news|web_search|report",
  "task_payload": {{"可选": "任务参数，如 location/query/prompt 等"}},
  "output": {{"email": true, "archive": true, "archive_dir": "reports"}}
}}

说明：
- schedule_at: 仅当用户要求定时提醒/发送时使用（例如 "2026-03-13T10:00:00" 或 "3600" 表示1小时后）。若即时回复则省略。
- schedule_every: 当用户要求“每 X 分钟/小时”等重复提醒时填写（例如 "5m"、"300"）。
- schedule_until: 重复提醒的截止时间（例如 "2026-03-13T18:00:00"），与 schedule_every 配合使用。
- attachments 为可选字段，附件内容为纯文本。"""


# ═══════════════════════════════════════════════════════════════
#  OAuth & 邮件核心逻辑
# ═══════════════════════════════════════════════════════════════

def _oauth_google(mailbox: dict) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    SCOPES = ["https://www.googleapis.com/auth/gmail.imap", "https://mail.google.com/"]
    token_file, creds_file = mailbox["oauth_token_file"], mailbox["oauth_creds_file"]
    creds = Credentials.from_authorized_user_file(token_file, SCOPES) if os.path.exists(token_file) else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token: creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            print(f"\nGmail OAuth 授权链接：\n{auth_url}\n请输入 code:")
            flow.fetch_token(code=input(">>> ").strip())
            creds = flow.credentials
        with open(token_file, "w") as f: f.write(creds.to_json())
    return creds.token

def _oauth_microsoft(mailbox: dict) -> str:
    import msal
    client_id, token_file = mailbox.get("oauth_client_id"), mailbox["oauth_token_file"]
    SCOPES = ["https://outlook.office.com/IMAP.AccessAsUser.All", "https://outlook.office.com/SMTP.Send", "offline_access"]
    cache = msal.SerializableTokenCache()
    if os.path.exists(token_file): cache.deserialize(open(token_file).read())
    app = msal.PublicClientApplication(client_id, authority="https://login.microsoftonline.com/common", token_cache=cache)
    accounts = app.get_accounts()
    result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        print(f"\nOutlook OAuth 授权：{flow['verification_uri']} 代码：{flow['user_code']}")
        result = app.acquire_token_by_device_flow(flow)
    if cache.has_state_changed:
        with open(token_file, "w") as f: f.write(cache.serialize())
    return result["access_token"]

def get_oauth_token(mailbox: dict) -> str:
    auth = mailbox.get("auth", "password")
    if auth == "oauth_google": return _oauth_google(mailbox)
    if auth == "oauth_microsoft": return _oauth_microsoft(mailbox)
    return ""

def make_oauth_string(address: str, token: str) -> str:
    import base64
    return base64.b64encode(f"user={address}\x01auth=Bearer {token}\x01\x01".encode()).decode()

def decode_str(s: str) -> str:
    if not s: return ""
    result = []
    for part, charset in _decode_header(s):
        if isinstance(part, bytes): result.append(part.decode(charset or "utf-8", errors="replace"))
        else: result.append(str(part))
    return "".join(result)

def get_body_and_attachments(msg) -> tuple:
    body, attachments = "", []
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get_content_disposition() or "")
            if "attachment" in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    is_text = part.get_content_type().startswith("text/")
                    content = payload.decode(part.get_content_charset() or "utf-8", errors="replace") if is_text else payload
                    attachments.append({"filename": decode_str(part.get_filename() or "untitled"), "content": content, "is_text": is_text})
            elif part.get_content_type() == "text/plain" and not body and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload: body = payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
    else:
        payload = msg.get_payload(decode=True)
        if payload: body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace").strip()
    return body, attachments

def imap_login(mailbox: dict):
    mail = imaplib.IMAP4_SSL(mailbox["imap_server"], mailbox["imap_port"], timeout=15)
    if mailbox.get("imap_id"):
        try: mail.xatom("ID", '("name" "mailmind" "version" "1.0")')
        except Exception: pass
    auth = mailbox.get("auth", "password")
    if auth == "password": mail.login(mailbox["address"], mailbox["password"])
    else:
        token = get_oauth_token(mailbox)
        mail.authenticate("XOAUTH2", lambda x: make_oauth_string(mailbox["address"], token))
    return mail

def smtp_login(mailbox: dict):
    server = smtplib.SMTP_SSL(mailbox["smtp_server"], mailbox["smtp_port"]) if mailbox.get("smtp_ssl") else smtplib.SMTP(mailbox["smtp_server"], mailbox["smtp_port"])
    if not mailbox.get("smtp_ssl"):
        server.ehlo()
        server.starttls()
    auth = mailbox.get("auth", "password")
    if auth == "password": server.login(mailbox["address"], mailbox["password"])
    else:
        token = get_oauth_token(mailbox)
        server.docmd("AUTH", f"XOAUTH2 {make_oauth_string(mailbox['address'], token)}")
    return server

def send_reply(mailbox: dict, to: str, subject: str, body: str, in_reply_to: str = "", attachments: list = None):
    full_body = f"{body}\n\n---\n✉️  由 MailMind AI 自动回复 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    msg = MIMEMultipart()
    msg["From"], msg["To"], msg["Subject"] = mailbox["address"], to, subject
    if in_reply_to: msg["In-Reply-To"] = msg["References"] = in_reply_to
    msg.attach(MIMEText(full_body, "plain", "utf-8"))
    for att in (attachments or []):
        part = MIMEBase("application", "octet-stream")
        part.set_payload(att["content"].encode("utf-8") if isinstance(att["content"], str) else att["content"])
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=att.get("filename", "file.txt"))
        msg.attach(part)
    with smtp_login(mailbox) as s: s.sendmail(mailbox["address"], to, msg.as_string())
    log.info(f"✅ 已回复 -> {to} | {subject}")


def _archive_output(output: dict, subject: str, body: str, attachments: list | None = None):
    if not output or not output.get("archive"):
        return
    archive_dir = output.get("archive_dir", "reports")
    os.makedirs(archive_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_subject = re.sub(r"[^\w\-_. ]+", "_", subject)[:80]
    path = os.path.join(archive_dir, f"{ts}_{safe_subject}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(subject + "\n\n" + body + "\n")
        if attachments:
            f.write("\n--- 附件列表 ---\n")
            for att in attachments:
                f.write(f"- {att.get('filename', 'file')}\n")
    log.info(f"🗂️ 已归档 -> {path}")

def fetch_unread_emails(mailbox: dict):
    mail = imap_login(mailbox)
    mail.select("INBOX")
    _, ids = mail.search(None, "UNSEEN")
    emails = []
    for mid in ids[0].split():
        if mid.decode() in processed_ids: continue
        _, data = mail.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(data[0][1])
        sender = decode_str(msg.get("From", ""))
        sender_email = parseaddr(sender)[1].strip()
        if not is_sender_allowed(sender_email, mailbox.get("allowed_senders", [])): continue
        body, atts = get_body_and_attachments(msg)
        emails.append({"id": mid.decode(), "from": sender, "from_email": sender_email, "subject": decode_str(msg.get("Subject", "(无主题)")), "message_id": msg.get("Message-ID", ""), "body": body, "attachments": atts})
    mail.logout()
    return emails

def parse_ai_response(raw: str):
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return (
                data.get("subject", ""),
                data.get("body", raw),
                data.get("schedule_at"),
                data.get("schedule_every"),
                data.get("schedule_until"),
                data.get("attachments", []),
                data.get("task_type"),
                data.get("task_payload"),
                data.get("output"),
            )
        except: pass
    return "", raw, None, None, None, [], None, None, None

def call_ai_text(ai_name: str, backend: dict, prompt: str) -> str:
    try:
        if backend["type"] == "cli":
            return subprocess.run([backend["cmd"]] + backend["args"] + [prompt], capture_output=True, text=True, timeout=180).stdout.strip()
        elif backend["type"].startswith("api_"):
            # 简化版：这里假设原有的 API 调用逻辑已在 email_daemon.py 中（实际开发时应保留原有各 API 函数）
            # 为了简洁，此处仅示意逻辑结构
            return "AI API 调用结果待集成"
        return ""
    except Exception as e:
        log.error(f"AI 调用失败: {e}")
        return f"AI 出错: {e}"


def call_ai(ai_name: str, backend: dict, instruction: str):
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    raw = call_ai_text(ai_name, backend, prompt)
    return parse_ai_response(raw)


DEFAULT_TASK_AI = os.environ.get("TASK_DEFAULT_AI", "")


def _pick_task_ai(task_payload: dict):
    ai_name = (task_payload or {}).get("ai_name") or DEFAULT_TASK_AI or "claude"
    backend = AI_BACKENDS.get(ai_name, AI_BACKENDS.get("claude"))
    return ai_name, backend


def _compose_report_sections(payload: dict) -> str:
    sections = []
    locations = payload.get("weather_locations") or []
    if isinstance(locations, str): locations = [locations]
    if locations:
        weather_lines = [fetch_weather(loc) for loc in locations]
        sections.append("【天气】\n" + "\n".join(weather_lines))
    if payload.get("news_query", True):
        news_text = fetch_news(
            query=payload.get("news_query"),
            page_size=payload.get("news_page_size"),
            language=payload.get("news_language"),
            country=payload.get("news_country"),
            sources=payload.get("news_sources"),
        )
        sections.append("【新闻】\n" + news_text)
    if payload.get("web_query"):
        results = web_search(payload.get("web_query"), payload.get("web_count", 5), payload.get("web_engine"))
        sections.append("【网页检索】\n" + (format_search_results(results) if results else "没有找到结果。"))
    return "\n\n".join(sections).strip()


def execute_task(task: dict):
    task_type = (task.get("type") or "email").lower()
    payload = task.get("payload") or {}
    output = task.get("output") or {}
    should_email = output.get("email", True)
    should_archive = output.get("archive", False)
    attachments = task.get("attachments") or []

    subject = task.get("subject") or "定时任务结果"
    body = task.get("body") or ""

    if task_type == "email":
        pass
    elif task_type == "weather":
        location = payload.get("location") or WEATHER_DEFAULT_LOCATION
        body = fetch_weather(location)
        subject = subject or f"天气更新：{location}"
    elif task_type == "news":
        body = fetch_news(
            query=payload.get("query"),
            page_size=payload.get("page_size"),
            language=payload.get("language"),
            country=payload.get("country"),
            sources=payload.get("sources"),
        )
        subject = subject or "新闻汇总"
    elif task_type == "web_search":
        query = payload.get("query") or ""
        results = web_search(query, payload.get("count", 5), payload.get("engine"))
        body = format_search_results(results) if results else "没有找到结果。"
        subject = subject or f"网页检索：{query}"
    elif task_type == "ai_job":
        ai_name, backend = _pick_task_ai(payload)
        prompt = payload.get("prompt") or body
        body = call_ai_text(ai_name, backend, prompt) or "AI 没有返回内容。"
        subject = subject or f"AI 任务结果 ({ai_name})"
    elif task_type == "report":
        report_text = _compose_report_sections(payload)
        if payload.get("use_ai_summary", True):
            ai_name, backend = _pick_task_ai(payload)
            prompt = f"请将以下内容汇总成简洁日报，分点输出，重点突出：\n\n{report_text}"
            summary = call_ai_text(ai_name, backend, prompt).strip()
            body = summary or report_text
            subject = subject or f"日报 ({ai_name})"
        else:
            body = report_text
            subject = subject or "日报"
    else:
        body = f"⚠️ 未知任务类型：{task_type}"

    if should_email:
        send_reply(MAILBOXES[task["mailbox_name"]], task["to"], subject, body, attachments=attachments)
    if should_archive:
        _archive_output(output, subject, body, attachments)

# ═══════════════════════════════════════════════════════════════
#  主流程重构 (已集成定时任务)
# ═══════════════════════════════════════════════════════════════

def process_email(mailbox_name, ai_name, backend, em):
    log.info(f"📨 收到指令: [{em['subject']}] 来自 {em['from_email']}")
    instr = f"发件人：{em['from']}\n主题：{em['subject']}\n\n{em['body']}"
    for att in em.get("attachments", []):
        if att["is_text"]: instr += f"\n\n--- 附件：{att['filename']} ---\n{att['content']}"
    
    search_res = search_web_if_needed(instr)
    if search_res: instr = search_res + "\n\n" + instr
    
    sub, body, sch_at, sch_every, sch_until, atts, task_type, task_payload, output = call_ai(ai_name, backend, instr)
    detected_tasks = []
    if not task_type:
        detected_tasks = auto_detect_tasks(em["body"] or "")
        if detected_tasks:
            det = detected_tasks[0]
            task_type = det.get("task_type") or task_type
            if not task_payload and det.get("task_payload"): task_payload = det.get("task_payload")
            if not output and det.get("output"): output = det.get("output")
            if not sch_at and det.get("schedule_at"): sch_at = det.get("schedule_at")
            if not sch_every and det.get("schedule_every"): sch_every = det.get("schedule_every")
            if not sch_until and det.get("schedule_until"): sch_until = det.get("schedule_until")
    sub = sub or (em["subject"] if em["subject"].startswith("Re:") else f"Re: {em['subject']}")
    
    if sch_at or sch_every:
        if task_type and not output:
            output = {"email": True, "archive": True, "archive_dir": "reports"}
        scheduler.add_task(
            mailbox_name,
            em["from_email"],
            sub,
            body,
            sch_at,
            sch_every,
            sch_until,
            task_type or "email",
            task_payload or {},
            output or {},
            atts,
        )
        if sch_every:
            send_reply(
                MAILBOXES[mailbox_name],
                em["from_email"],
                f"已安排定时任务：{sub}",
                f"您的任务将每 {sch_every} 发送一次，截止至 {sch_until or '未指定'}。\n\n内容预览：\n{body}",
            )
        else:
            send_reply(MAILBOXES[mailbox_name], em["from_email"], f"已安排定时任务：{sub}", f"您的任务已安排在 {sch_at} 左右执行。\n\n内容预览：\n{body}")
    elif detected_tasks:
        summaries = []
        for idx, det in enumerate(detected_tasks, 1):
            d_sub = f"{sub} - {det.get('task_type', 'email')}"
            d_body = body if det.get("task_type") == "email" else ""
            scheduler.add_task(
                mailbox_name,
                em["from_email"],
                d_sub,
                d_body,
                det.get("schedule_at"),
                det.get("schedule_every"),
                det.get("schedule_until"),
                det.get("task_type") or "email",
                det.get("task_payload") or {},
                det.get("output") or {},
                [],
            )
            summaries.append(
                f"{idx}. {det.get('task_type')} | at={det.get('schedule_at') or '-'} | every={det.get('schedule_every') or '-'} | until={det.get('schedule_until') or '-'}"
            )
        send_reply(
            MAILBOXES[mailbox_name],
            em["from_email"],
            f"已安排 {len(detected_tasks)} 个定时任务：{sub}",
            "任务列表：\n" + "\n".join(summaries),
        )
    else:
        send_reply(MAILBOXES[mailbox_name], em["from_email"], sub, body, em.get("message_id"), atts)
    
    processed_ids.add(em["id"])
    save_processed_ids(PROCESSED_IDS_PATH, processed_ids)

def run_idle(mailbox_name, ai_name, backend):
    import imapclient
    mailbox = MAILBOXES[mailbox_name]
    while True:
        try:
            with imapclient.IMAPClient(mailbox["imap_server"], ssl=True) as client:
                if mailbox.get("auth") == "password": client.login(mailbox["address"], mailbox["password"])
                else: client.oauth2_login(mailbox["address"], get_oauth_token(mailbox))
                if mailbox.get("imap_id"): client.id_({"name": "mailmind"})
                client.select_folder("INBOX")
                log.info(f"✅ {mailbox_name} IDLE 就绪")
                while True:
                    for em in fetch_unread_emails(mailbox): process_email(mailbox_name, ai_name, backend, em)
                    client.idle()
                    client.idle_check(timeout=300)
                    client.idle_done()
        except Exception as e:
            log.error(f"IDLE 异常: {e}")
            time.sleep(10)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mailbox", default="126")
    parser.add_argument("--ai", default="claude")
    args = parser.parse_args()
    
    global DEFAULT_TASK_AI
    if not DEFAULT_TASK_AI:
        DEFAULT_TASK_AI = args.ai
    
    global processed_ids, PROCESSED_IDS_PATH
    PROCESSED_IDS_PATH = _default_processed_ids_path(args.mailbox)
    processed_ids = load_processed_ids(PROCESSED_IDS_PATH)
    
    # 启动任务调度器线程
    threading.Thread(target=scheduler.run_forever, daemon=True).start()
    
    log.info(f"🚀 MailMind 启动 | 邮箱: {args.mailbox} | AI: {args.ai}")
    run_idle(args.mailbox, args.ai, AI_BACKENDS[args.ai])

if __name__ == "__main__":
    main()
