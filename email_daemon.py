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
        "password":        os.environ.get("MAIL_GMAIL_PASSWORD", ""),   # 应用专用密码（非 OAuth 时使用）
        "imap_server":     "imap.gmail.com",
        "imap_port":       993,
        "smtp_server":     "smtp.gmail.com",
        "smtp_port":       465,
        "smtp_ssl":        True,
        "imap_id":         False,
        "auth":            "oauth_google",   # 改为 "password" 则使用应用专用密码
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
        "oauth_client_id":  os.environ.get("OUTLOOK_CLIENT_ID", ""),    # Azure App 注册的 Client ID
        "allowed_senders": [s.strip() for s in os.environ.get("MAIL_OUTLOOK_ALLOWED", "").split(",") if s.strip()],
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
#  Web Search 配置
# ────────────────────────────────────────────────────────────────

WEB_SEARCH_ENABLED = os.environ.get("WEB_SEARCH", "false").lower() == "true"
WEB_SEARCH_ENGINE = os.environ.get("WEB_SEARCH_ENGINE", "duckduckgo")  # duckduckgo / google / bing
SEARCH_RESULTS_COUNT = int(os.environ.get("SEARCH_RESULTS_COUNT", "5"))

# 搜索提示词模板
WEB_SEARCH_PROMPT = """
【网络搜索结果】（来自 {engine}，共 {count} 条）：
{search_results}

---
以上为网络搜索结果，请结合上述信息回答用户的问题。
"""


def web_search(query: str, num_results: int = 5) -> list:
    """
    执行网络搜索，返回搜索结果列表
    
    支持的搜索引擎：
    - duckduckgo: DuckDuckGo API（无需 API Key）
    - wikipedia: Wikipedia API（免费，适合知识类查询）
    - google: Google Custom Search API（需要 API Key）
    - bing: Bing Search API（需要 API Key）
    """
    results = []

    if WEB_SEARCH_ENGINE == "duckduckgo":
        try:
            # DuckDuckGo Instant Answer API（无需 Key）
            headers = {"User-Agent": "Mozilla/5.0"}
            url = f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}&format=json&no_html=1"
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            
            # 提取摘要
            if data.get("AbstractText"):
                results.append({
                    "title": data.get("Heading", "摘要"),
                    "snippet": data.get("AbstractText", ""),
                    "url": data.get("AbstractURL", "")
                })
            
            # 提取相关结果
            for item in data.get("RelatedTopics", [])[:num_results]:
                if isinstance(item, dict) and "Text" in item:
                    results.append({
                        "title": item.get("Text", "")[:100] + "...",
                        "snippet": item.get("Text", ""),
                        "url": item.get("FirstURL", "")
                    })
                    
        except Exception as e:
            log.warning(f"DuckDuckGo 搜索失败：{e}")
            
    elif WEB_SEARCH_ENGINE == "wikipedia":
        # Wikipedia API（免费，无需 API Key）
        try:
            lang = os.environ.get('WIKIPEDIA_LANG', 'zh')
            url = f"https://{lang}.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "format": "json",
                "srlimit": num_results
            }
            headers = {"User-Agent": "MailMind/1.0"}
            resp = requests.get(url, params=params, headers=headers, timeout=10)
            data = resp.json()
            for item in data.get("query", {}).get("search", [])[:num_results]:
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", "").replace('<span class="searchmatch">', '').replace('</span>', ''),
                    "url": f"https://{lang}.wikipedia.org/wiki/{item.get('title', '')}"
                })
        except Exception as e:
            log.warning(f"Wikipedia 搜索失败：{e}")

    elif WEB_SEARCH_ENGINE == "google":
        # Google 需要 API Key，这里使用自定义搜索 API
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        cse_id = os.environ.get("GOOGLE_CSE_ID", "")
        if api_key and cse_id:
            try:
                url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cse_id}&q={requests.utils.quote(query)}"
                resp = requests.get(url, timeout=10)
                data = resp.json()
                for item in data.get("items", [])[:num_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "url": item.get("link", "")
                    })
            except Exception as e:
                log.warning(f"Google 搜索失败：{e}")
        else:
            log.warning("未配置 GOOGLE_API_KEY 或 GOOGLE_CSE_ID")
            
    elif WEB_SEARCH_ENGINE == "bing":
        # Bing 需要 API Key
        api_key = os.environ.get("BING_API_KEY", "")
        if api_key:
            try:
                url = f"https://api.bing.microsoft.com/v7.0/search?q={requests.utils.quote(query)}"
                headers = {"Ocp-Apim-Subscription-Key": api_key}
                resp = requests.get(url, headers=headers, timeout=10)
                data = resp.json()
                for item in data.get("webPages", {}).get("value", [])[:num_results]:
                    results.append({
                        "title": item.get("name", ""),
                        "snippet": item.get("snippet", ""),
                        "url": item.get("url", "")
                    })
            except Exception as e:
                log.warning(f"Bing 搜索失败：{e}")
        else:
            log.warning("未配置 BING_API_KEY")
    
    return results


def format_search_results(results: list) -> str:
    """格式化搜索结果为用户可读的文本"""
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. 【{r.get('title', '无标题')}】")
        lines.append(f"   {r.get('snippet', '')}")
        lines.append(f"   链接：{r.get('url', '')}")
        lines.append("")
    return "\n".join(lines)


def search_web_if_needed(instruction: str) -> str:
    """
    判断是否需要搜索，如果需要则执行搜索并返回格式化的结果
    如果不需要搜索或搜索失败，返回空字符串
    """
    if not WEB_SEARCH_ENABLED:
        return ""
    
    # 检测指令中是否包含搜索关键词
    search_keywords = ["搜索", "查找", "查询", "最新", "最近", "news", "search", "look up", "find"]
    needs_search = any(kw in instruction.lower() for kw in search_keywords)
    
    if not needs_search:
        return ""
    
    log.info("🔍 检测到搜索意图，执行网络搜索...")
    
    # 提取搜索关键词（简化：使用整个指令的前 50 个字）
    search_query = instruction[:50].replace("\n", " ").strip()
    
    results = web_search(search_query, SEARCH_RESULTS_COUNT)
    
    if results:
        log.info(f"✅ 搜索完成，找到 {len(results)} 条结果")
        return WEB_SEARCH_PROMPT.format(
            engine=WEB_SEARCH_ENGINE,
            count=len(results),
            search_results=format_search_results(results)
        )
    else:
        log.warning("⚠️  搜索未返回结果")
        return ""

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))

# ═══════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("mailmind")
processed_ids: set = set()
PROCESSED_IDS_PATH: str | None = None


def _default_processed_ids_path(mailbox_name: str) -> str:
    base_dir = os.path.dirname(__file__)
    return os.path.join(base_dir, f"processed_ids_{mailbox_name}.json")


def load_processed_ids(path: str) -> set:
    if not path:
        return set()
    if not os.path.isfile(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return set(str(x) for x in data)
        log.warning(f"processed_ids 文件格式不正确，忽略：{path}")
        return set()
    except Exception as e:
        log.warning(f"读取 processed_ids 失败：{e}")
        return set()


def save_processed_ids(path: str, ids: set):
    if not path:
        return
    tmp_path = f"{path}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(sorted(ids), f, ensure_ascii=True, indent=2)
        os.replace(tmp_path, path)
    except Exception as e:
        log.warning(f"保存 processed_ids 失败：{e}")
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def is_sender_allowed(sender_email: str, allowed: list) -> bool:
    if not allowed:
        return True
    sender_email = (sender_email or "").strip().lower()
    if "@" not in sender_email:
        return False
    _, _, sender_domain = sender_email.rpartition("@")
    for entry in allowed:
        rule = (entry or "").strip().lower()
        if not rule:
            continue
        if "@" in rule:
            if sender_email == rule:
                return True
        else:
            if rule.startswith("@"):
                rule = rule[1:]
            if sender_domain == rule:
                return True
    return False

PROMPT_TEMPLATE = """\
你正在通过邮件接收用户指令。以下是用户发来的邮件，请执行其中的任务。

{instruction}

请严格按以下 JSON 格式回复，不要输出任何其他内容：
{{"subject": "根据回复内容拟定的简短邮件标题", "body": "回复正文内容", "attachments": [{{"filename": "文件名.txt", "content": "文件内容"}}]}}

说明：
- attachments 为可选字段，仅在需要以文件形式返回内容时填写（如整理后的文档、报告等）
- 若无附件，可省略 attachments 字段或设为空数组
- 附件内容为纯文本，文件名应包含正确后缀（如 .txt / .md / .csv 等）"""


# ═══════════════════════════════════════════════════════════════
#  OAuth 认证
# ═══════════════════════════════════════════════════════════════

def _oauth_google(mailbox: dict) -> str:
    """获取 Gmail OAuth access_token，首次运行打印 URL 让用户授权"""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        raise ImportError("请安装 Google OAuth 库：pip install google-auth google-auth-oauthlib google-auth-httplib2")

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.imap",
        "https://mail.google.com/",
    ]
    token_file = mailbox["oauth_token_file"]
    creds_file = mailbox["oauth_creds_file"]
    creds = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            log.info("🔄 Gmail token 已自动刷新")
        else:
            if not os.path.exists(creds_file):
                raise FileNotFoundError(
                    f"找不到 {creds_file}\n"
                    "请先从 Google Cloud Console 下载 OAuth 凭据（桌面应用类型）\n"
                    "教程：https://developers.google.com/gmail/api/quickstart/python"
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            print("\n" + "="*60)
            print("📧 Gmail OAuth 授权")
            print("="*60)
            print("请在本地浏览器打开以下链接完成授权：\n")
            print(auth_url)
            print("\n授权完成后，将页面显示的 code 粘贴到这里：")
            code = input(">>> ").strip()
            flow.fetch_token(code=code)
            creds = flow.credentials
            log.info("✅ Gmail OAuth 授权成功")

        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return creds.token


def _oauth_microsoft(mailbox: dict) -> str:
    """获取 Outlook OAuth access_token，首次运行打印 URL 让用户授权"""
    try:
        import msal
    except ImportError:
        raise ImportError("请安装 MSAL 库：pip install msal")

    client_id  = mailbox.get("oauth_client_id", "")
    token_file = mailbox["oauth_token_file"]

    if not client_id:
        raise ValueError(
            "未设置 OUTLOOK_CLIENT_ID 环境变量\n"
            "请先在 Azure Portal 注册应用并获取 Client ID\n"
            "教程：https://learn.microsoft.com/zh-cn/azure/active-directory/develop/quickstart-register-app"
        )

    SCOPES = ["https://outlook.office.com/IMAP.AccessAsUser.All",
              "https://outlook.office.com/SMTP.Send", "offline_access"]

    # 尝试从缓存加载 token
    cache = msal.SerializableTokenCache()
    if os.path.exists(token_file):
        cache.deserialize(open(token_file).read())

    app = msal.PublicClientApplication(client_id, authority="https://login.microsoftonline.com/common", token_cache=cache)

    # 先尝试静默获取
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    if not result:
        # 需要交互授权
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"无法启动设备流: {flow.get('error_description')}")

        print("\n" + "="*60)
        print("📧 Outlook OAuth 授权")
        print("="*60)
        print(f"请在本地浏览器打开：{flow['verification_uri']}")
        print(f"输入代码：{flow['user_code']}")
        print("\n等待授权完成...")
        result = app.acquire_token_by_device_flow(flow)

    if "access_token" not in result:
        raise RuntimeError(f"OAuth 失败: {result.get('error_description', result)}")

    # 保存缓存
    if cache.has_state_changed:
        with open(token_file, "w") as f:
            f.write(cache.serialize())

    log.info("✅ Outlook OAuth token 获取成功")
    return result["access_token"]


def get_oauth_token(mailbox: dict) -> str:
    """根据邮箱类型获取 OAuth token"""
    auth = mailbox.get("auth", "password")
    if auth == "oauth_google":
        return _oauth_google(mailbox)
    elif auth == "oauth_microsoft":
        return _oauth_microsoft(mailbox)
    return ""


def make_oauth_string(address: str, token: str) -> str:
    """生成 XOAUTH2 认证字符串"""
    import base64
    auth_str = f"user={address}\x01auth=Bearer {token}\x01\x01"
    return base64.b64encode(auth_str.encode()).decode()


# ═══════════════════════════════════════════════════════════════
#  邮件收发
# ═══════════════════════════════════════════════════════════════

def decode_str(s: str) -> str:
    if not s:
        return ""
    parts = _decode_header(s)
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)


def get_body_and_attachments(msg) -> tuple:
    """返回 (正文文本, 附件列表)
    附件格式: [{"filename": str, "content": str|bytes, "is_text": bool}]
    文本类附件直接解码为字符串，二进制附件保留 bytes。
    """
    body = ""
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition = str(part.get_content_disposition() or "")

            if "attachment" in disposition:
                filename = decode_str(part.get_filename() or "untitled")
                payload = part.get_payload(decode=True)
                if payload:
                    is_text = content_type.startswith("text/")
                    if is_text:
                        charset = part.get_content_charset() or "utf-8"
                        attachments.append({"filename": filename, "content": payload.decode(charset, errors="replace"), "is_text": True})
                    else:
                        attachments.append({"filename": filename, "content": payload, "is_text": False})
            elif content_type == "text/plain" and not body and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace").strip()

    return body, attachments


def imap_login(mailbox: dict) -> imaplib.IMAP4_SSL:
    """建立 IMAP 连接（自动处理密码/OAuth两种方式）"""
    mail = imaplib.IMAP4_SSL(mailbox["imap_server"], mailbox["imap_port"], timeout=15)

    if mailbox.get("imap_id"):
        try:
            mail.xatom("ID", '("name" "mailmind" "version" "1.0")')
        except Exception:
            pass

    auth = mailbox.get("auth", "password")
    if auth == "password":
        mail.login(mailbox["address"], mailbox["password"])
    else:
        token = get_oauth_token(mailbox)
        oauth_str = make_oauth_string(mailbox["address"], token)
        mail.authenticate("XOAUTH2", lambda x: oauth_str)

    return mail


def smtp_login(mailbox: dict):
    """建立 SMTP 连接（自动处理密码/OAuth两种方式）"""
    auth = mailbox.get("auth", "password")

    if mailbox.get("smtp_ssl"):
        server = smtplib.SMTP_SSL(mailbox["smtp_server"], mailbox["smtp_port"])
    else:
        server = smtplib.SMTP(mailbox["smtp_server"], mailbox["smtp_port"])
        server.ehlo()
        server.starttls()

    if auth == "password":
        server.login(mailbox["address"], mailbox["password"])
    else:
        token = get_oauth_token(mailbox)
        oauth_str = make_oauth_string(mailbox["address"], token)
        server.docmd("AUTH", f"XOAUTH2 {oauth_str}")

    return server


def fetch_unread_emails(mailbox: dict) -> list:
    mail = imap_login(mailbox)

    status, _ = mail.select("INBOX")
    if status != "OK":
        log.error("无法选中 INBOX")
        mail.logout()
        return []

    _, ids = mail.search(None, "UNSEEN")
    emails = []

    for mid in ids[0].split():
        mid_str = mid.decode()
        if mid_str in processed_ids:
            continue

        _, data = mail.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(data[0][1])

        sender = decode_str(msg.get("From", ""))
        sender_email = parseaddr(sender)[1].strip() if sender else ""

        allowed = mailbox.get("allowed_senders", [])
        if not is_sender_allowed(sender_email, allowed):
            log.info(f"跳过非白名单: {sender_email}")
            continue

        body, attachments = get_body_and_attachments(msg)
        emails.append({
            "id":          mid_str,
            "from":        sender,
            "from_email":  sender_email,
            "subject":     decode_str(msg.get("Subject", "(无主题)")),
            "message_id":  msg.get("Message-ID", ""),
            "body":        body,
            "attachments": attachments,
        })

    mail.logout()
    return emails


def send_reply(mailbox: dict, to: str, subject: str, body: str, in_reply_to: str = "", attachments: list = None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_body = f"{body}\n\n---\n✉️  由 MailMind AI 自动回复 | {timestamp}"

    msg = MIMEMultipart()
    msg["From"]    = mailbox["address"]
    msg["To"]      = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"]  = in_reply_to
    msg.attach(MIMEText(full_body, "plain", "utf-8"))

    for att in (attachments or []):
        filename = att.get("filename", "attachment.txt")
        content  = att.get("content", "")
        if isinstance(content, str):
            content = content.encode("utf-8")
        part = MIMEBase("application", "octet-stream")
        part.set_payload(content)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)

    with smtp_login(mailbox) as server:
        server.sendmail(mailbox["address"], to, msg.as_string())

    att_info = f" | {len(attachments)} 个附件" if attachments else ""
    log.info(f"✅ 已回复 → {to} | {subject}{att_info}")


# ═══════════════════════════════════════════════════════════════
#  AI 调用
# ═══════════════════════════════════════════════════════════════

def parse_ai_response(raw: str) -> tuple:
    """返回 (subject, body, attachments)"""
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            subject = data.get("subject", "") or ""
            body = data.get("body", "") or raw
            attachments = data.get("attachments", [])
            return subject, body, attachments
        except json.JSONDecodeError:
            log.warning(f"AI 返回的 JSON 解析失败：{raw[:200]}")
    log.warning(f"AI 返回内容未包含有效 JSON: {raw[:200]}")
    return "", raw, []


def call_ai_cli(backend: dict, instruction: str) -> str:
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    cmd = [backend["cmd"]] + backend["args"] + [prompt]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode == 0:
        return result.stdout.strip()
    raise RuntimeError(result.stderr[:300])


def log_token_usage(provider: str, data: dict) -> None:
    """Log token usage if the provider returns it."""
    if not isinstance(data, dict):
        return

    try:
        if provider == "anthropic":
            usage = data.get("usage", {})
            if usage:
                log.info(
                    f"🔢 {provider} tokens: input={usage.get('input_tokens')} "
                    f"output={usage.get('output_tokens')}"
                )
            return

        if provider == "openai":
            usage = data.get("usage", {})
            if usage:
                log.info(
                    f"🔢 {provider} tokens: prompt={usage.get('prompt_tokens')} "
                    f"completion={usage.get('completion_tokens')} total={usage.get('total_tokens')}"
                )
            return

        if provider == "gemini":
            usage = data.get("usageMetadata", {})
            if usage:
                log.info(
                    f"🔢 {provider} tokens: prompt={usage.get('promptTokenCount')} "
                    f"candidates={usage.get('candidatesTokenCount')} total={usage.get('totalTokenCount')}"
                )
            return

        if provider == "qwen":
            usage = data.get("usage") or data.get("token_usage") or data.get("output", {}).get("token_usage")
            if isinstance(usage, dict) and usage:
                log.info(
                    f"🔢 {provider} tokens: input={usage.get('input_tokens')} "
                    f"output={usage.get('output_tokens')} total={usage.get('total_tokens')}"
                )
            return
    except Exception:
        # Never fail the request due to usage logging.
        return


def call_ai_api_anthropic(backend: dict, instruction: str) -> str:
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": backend["api_key"], "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        json={"model": backend["model"], "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    log_token_usage("anthropic", data)
    return data["content"][0]["text"].strip()


def call_ai_api_openai(backend: dict, instruction: str) -> str:
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    resp = requests.post(
        backend["url"],
        headers={"Authorization": f"Bearer {backend['api_key']}", "Content-Type": "application/json"},
        json={"model": backend["model"], "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    log_token_usage("openai", data)
    return data["choices"][0]["message"]["content"].strip()


def call_ai_api_gemini(backend: dict, instruction: str) -> str:
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{backend['model']}:generateContent?key={backend['api_key']}"
    wait = 5
    for attempt in range(5):
        resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=120)
        if resp.status_code == 429:
            logging.warning(f"Gemini API 429 レート制限、{wait}秒後にリトライ ({attempt+1}/5)")
            time.sleep(wait)
            wait *= 2
            continue
        resp.raise_for_status()
        data = resp.json()
        log_token_usage("gemini", data)
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    resp.raise_for_status()
    return ""


def call_ai_api_qwen(backend: dict, instruction: str) -> str:
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    resp = requests.post(
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
        headers={"Authorization": f"Bearer {backend['api_key']}", "Content-Type": "application/json"},
        json={"model": backend["model"], "input": {"messages": [{"role": "user", "content": prompt}]}},
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    log_token_usage("qwen", data)
    return data["output"]["text"].strip()


def call_ai_cli_copilot(backend: dict, instruction: str) -> str:
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    result = subprocess.run(
        [backend["cmd"], "--prompt", prompt],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:300])
    # Strip trailing usage stats block ("Total usage est: ..." and below)
    output = result.stdout
    cutoff = output.find("\nTotal usage est:")
    if cutoff != -1:
        output = output[:cutoff]
    return output.strip()


def call_ai(ai_name: str, backend: dict, instruction: str) -> tuple:
    """返回 (subject, body, attachments)"""
    try:
        t = backend["type"]
        if   t == "cli":           raw = call_ai_cli(backend, instruction)
        elif t == "api_anthropic": raw = call_ai_api_anthropic(backend, instruction)
        elif t == "api_openai":    raw = call_ai_api_openai(backend, instruction)
        elif t == "api_gemini":    raw = call_ai_api_gemini(backend, instruction)
        elif t == "api_qwen":      raw = call_ai_api_qwen(backend, instruction)
        elif t == "cli_copilot":   raw = call_ai_cli_copilot(backend, instruction)
        else: raise ValueError(f"未知 AI 类型: {t}")
        return parse_ai_response(raw)
    except subprocess.TimeoutExpired:
        return "", "任务超时（超过3分钟），请拆分为更小的任务。", []
    except FileNotFoundError:
        return "", f"未找到命令 {backend.get('cmd', '')}，请确认已安装。", []
    except Exception as e:
        log.error(f"AI 调用失败: {e}")
        return "", f"AI 处理出错：{e}", []


# ═══════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════

def _process_new_emails(mailbox: dict, ai_name: str, backend: dict):
    """拉取并处理所有未读邮件（供 IDLE 和轮询共用）"""
    emails = fetch_unread_emails(mailbox)
    if emails:
        log.info(f"📬 发现 {len(emails)} 封新指令")
        for em in emails:
            process_email(mailbox, ai_name, backend, em)
    return emails


def process_email(mailbox: dict, ai_name: str, backend: dict, em: dict):
    log.info(f"📨 收到指令: [{em['subject']}] 来自 {em['from_email']}")

    # 构建指令：正文 + 收到的附件内容
    instruction = f"发件人：{em['from']}\n主题：{em['subject']}\n\n{em['body']}"
    incoming_attachments = em.get("attachments", [])
    if incoming_attachments:
        log.info(f"📎 邮件附带 {len(incoming_attachments)} 个附件")
        for att in incoming_attachments:
            if att["is_text"]:
                instruction += f"\n\n--- 附件：{att['filename']} ---\n{att['content']}"
            else:
                instruction += f"\n\n--- 附件（二进制，无法读取内容）：{att['filename']} ---"

    # 如果需要，先执行网络搜索
    search_results = search_web_if_needed(instruction)
    if search_results:
        instruction = search_results + "\n\n" + instruction
    
    log.info(f"🤖 [{ai_name}] 处理中...")
    new_subject, reply_body, reply_attachments = call_ai(ai_name, backend, instruction)

    if new_subject and new_subject.strip():
        reply_subject = new_subject.strip()
        log.info(f"📝 AI 生成新标题：{new_subject}")
    else:
        reply_subject = em["subject"] if em["subject"].startswith("Re:") else f"Re: {em['subject']}"
        log.warning("⚠️  AI 未生成标题，使用默认格式")

    if not reply_body or not reply_body.strip():
        reply_body = "AI 处理完成，但未生成具体回复内容。请检查 AI 是否正确理解指令。"
        log.warning("⚠️  AI 返回空 body，使用默认提示")

    if reply_attachments:
        log.info(f"📎 AI 生成 {len(reply_attachments)} 个附件")


    send_reply(mailbox, to=em["from_email"], subject=reply_subject,
               body=reply_body, in_reply_to=em.get("message_id", ""),
               attachments=reply_attachments)
    processed_ids.add(em["id"])
    save_processed_ids(PROCESSED_IDS_PATH, processed_ids)


def run_poll(mailbox: dict, ai_name: str, backend: dict):
    """定时轮询模式"""
    while True:
        try:
            emails = _process_new_emails(mailbox, ai_name, backend)
            if not emails:
                log.info("📭 暂无新邮件，等待下次轮询...")
        except KeyboardInterrupt:
            log.info("🛑 已停止")
            break
        except Exception as e:
            log.error(f"出错: {e}", exc_info=True)
        time.sleep(POLL_INTERVAL)


def run_idle(mailbox: dict, ai_name: str, backend: dict):
    """IMAP IDLE 实时推送模式（断线自动重连）"""
    try:
        import imapclient
    except ImportError:
        raise ImportError("IMAP IDLE 需要 imapclient 库：pip install imapclient")

    IDLE_REFRESH = 25 * 60   # 25 分钟重发 IDLE（服务器通常 29 分钟超时）
    RECONNECT_DELAY = 5

    log.info("📡 IDLE 模式就绪，等待新邮件推送...")

    while True:
        client = None
        try:
            client = imapclient.IMAPClient(
                mailbox["imap_server"], port=mailbox["imap_port"], ssl=True, timeout=30
            )

            # 登录
            auth = mailbox.get("auth", "password")
            if auth == "password":
                client.login(mailbox["address"], mailbox["password"])
            else:
                token = get_oauth_token(mailbox)
                client.oauth2_login(mailbox["address"], token)

            # IMAP ID（126/163 需要）
            if mailbox.get("imap_id"):
                try:
                    client.id_({"name": "mailmind", "version": "1.0"})
                except Exception:
                    pass

            client.select_folder("INBOX")
            log.info("✅ IDLE 连接建立")

            # 启动时先处理一次积压的未读邮件
            _process_new_emails(mailbox, ai_name, backend)

            while True:
                client.idle()
                responses = client.idle_check(timeout=IDLE_REFRESH)
                client.idle_done()

                if responses:
                    log.info("📬 检测到邮箱变化，拉取新邮件...")
                    try:
                        _process_new_emails(mailbox, ai_name, backend)
                    except Exception as e:
                        log.error(f"处理邮件出错: {e}", exc_info=True)
                # else: IDLE 超时刷新，重新进入 IDLE

        except KeyboardInterrupt:
            log.info("🛑 已停止")
            break
        except Exception as e:
            log.error(f"IDLE 连接断开: {e}，{RECONNECT_DELAY} 秒后重连...")
            time.sleep(RECONNECT_DELAY)
        finally:
            if client:
                try:
                    client.logout()
                except Exception:
                    pass


def main():
    parser = argparse.ArgumentParser(description="MailMind — 邮件 AI 守护进程")
    parser.add_argument("--mailbox", default=None, help=f"邮箱: {list(MAILBOXES.keys())}")
    parser.add_argument("--ai",      default=None, help=f"AI:  {list(AI_BACKENDS.keys())}")
    parser.add_argument("--list",    action="store_true", help="列出所有配置状态")
    parser.add_argument("--auth",    action="store_true", help="仅执行 OAuth 授权（不启动守护进程）")
    parser.add_argument("--poll",    action="store_true", help="使用轮询模式（默认: IMAP IDLE）")
    args = parser.parse_args()

    if args.list:
        print("\n可用邮箱:")
        for name, mb in MAILBOXES.items():
            addr   = mb["address"]
            status = "✅" if addr else "❌ 未配置"
            auth   = mb.get("auth", "password")
            print(f"  {name:10} {status}  {addr or ''}  [{auth}]")
        print("\n可用 AI:")
        for name, ai in AI_BACKENDS.items():
            if ai["type"] == "cli":
                print(f"  {name:15} [CLI] cmd={ai['cmd']}")
            else:
                key_ok = "✅" if ai.get("api_key") else "❌ 未配置"
                print(f"  {name:15} [API] {key_ok}  model={ai.get('model', '')}")
        print()
        return

    # 选择邮箱
    mailbox_name = args.mailbox
    if not mailbox_name:
        for name, mb in MAILBOXES.items():
            if mb["address"] and (mb.get("password") or mb.get("auth", "").startswith("oauth")):
                mailbox_name = name
                break
    if not mailbox_name or not MAILBOXES.get(mailbox_name, {}).get("address"):
        print(f"❌ 请指定邮箱: --mailbox {list(MAILBOXES.keys())}")
        print("   并设置对应环境变量，运行 --list 查看详情")
        sys.exit(1)
    mailbox = MAILBOXES[mailbox_name]

    # 加载已处理邮件 ID
    global processed_ids, PROCESSED_IDS_PATH
    env_ids_path = os.environ.get("PROCESSED_IDS_FILE", "").strip()
    PROCESSED_IDS_PATH = env_ids_path or _default_processed_ids_path(mailbox_name)
    processed_ids = load_processed_ids(PROCESSED_IDS_PATH)

    # 选择 AI
    ai_name = args.ai or "claude"
    if ai_name not in AI_BACKENDS:
        print(f"❌ 未知 AI: {ai_name}，可选: {list(AI_BACKENDS.keys())}")
        sys.exit(1)
    backend = AI_BACKENDS[ai_name]

    # 仅授权模式
    if args.auth:
        log.info(f"🔐 执行 {mailbox_name} OAuth 授权...")
        get_oauth_token(mailbox)
        log.info("✅ 授权完成，token 已保存，可以正常启动服务了")
        return

    log.info("🚀 MailMind 启动")
    log.info(f"   邮箱     : {mailbox_name} ({mailbox['address']}) [{mailbox.get('auth', 'password')}]")
    log.info(f"   AI       : {ai_name} [{backend['type']}]")
    log.info(f"   白名单   : {mailbox['allowed_senders'] or '（全部接受）'}")
    log.info(f"   已处理ID : {len(processed_ids)}（{PROCESSED_IDS_PATH}）")

    use_poll = args.poll or os.environ.get("MODE", "").lower() == "poll"
    if use_poll:
        log.info(f"   模式     : 轮询（每 {POLL_INTERVAL} 秒）")
        run_poll(mailbox, ai_name, backend)
    else:
        log.info(f"   模式     : IMAP IDLE（实时推送）")
        run_idle(mailbox, ai_name, backend)


if __name__ == "__main__":
    main()
