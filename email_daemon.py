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
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header as _decode_header

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

AI_BACKENDS = {
    "claude":      {"type": "cli", "cmd": os.environ.get("CLAUDE_CMD", "claude"), "args": ["--print"]},
    "codex":       {"type": "cli", "cmd": os.environ.get("CODEX_CMD",  "codex"),  "args": ["exec", "--skip-git-repo-check"]},
    "gemini":      {"type": "cli", "cmd": os.environ.get("GEMINI_CMD", "gemini"), "args": ["--print"]},
    "qwen":        {"type": "cli", "cmd": os.environ.get("QWEN_CMD",   "qwen"),   "args": ["--prompt"]},
    "anthropic":   {"type": "api_anthropic", "api_key": os.environ.get("ANTHROPIC_API_KEY", ""), "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")},
    "openai":      {"type": "api_openai",    "api_key": os.environ.get("OPENAI_API_KEY", ""),    "model": os.environ.get("OPENAI_MODEL",     "gpt-4o"),            "url": "https://api.openai.com/v1/chat/completions"},
    "gemini-api":  {"type": "api_gemini",    "api_key": os.environ.get("GEMINI_API_KEY", ""),    "model": os.environ.get("GEMINI_MODEL",     "gemini-2.0-flash")},
    "qwen-api":    {"type": "api_qwen",      "api_key": os.environ.get("QWEN_API_KEY", ""),      "model": os.environ.get("QWEN_MODEL",       "qwen-max")},
}

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL", "60"))

# ═══════════════════════════════════════════════════════════════

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("mailmind")
processed_ids: set = set()

PROMPT_TEMPLATE = """\
你正在通过邮件接收用户指令。以下是用户发来的邮件，请执行其中的任务。

{instruction}

请严格按以下 JSON 格式回复，不要输出任何其他内容：
{{"subject": "根据回复内容拟定的简短邮件标题", "body": "回复正文内容"}}"""


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


def get_body(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace").strip()
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace").strip()
    return ""


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
        sender_email = sender.split("<")[-1].rstrip(">").strip() if "<" in sender else sender

        allowed = mailbox.get("allowed_senders", [])
        if allowed and not any(s.lower() in sender_email.lower() for s in allowed):
            log.info(f"跳过非白名单: {sender_email}")
            continue

        emails.append({
            "id":         mid_str,
            "from":       sender,
            "from_email": sender_email,
            "subject":    decode_str(msg.get("Subject", "(无主题)")),
            "message_id": msg.get("Message-ID", ""),
            "body":       get_body(msg),
        })

    mail.logout()
    return emails


def send_reply(mailbox: dict, to: str, subject: str, body: str, in_reply_to: str = ""):
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

    with smtp_login(mailbox) as server:
        server.sendmail(mailbox["address"], to, msg.as_string())

    log.info(f"✅ 已回复 → {to} | {subject}")


# ═══════════════════════════════════════════════════════════════
#  AI 调用
# ═══════════════════════════════════════════════════════════════

def parse_ai_response(raw: str) -> tuple:
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return data.get("subject", ""), data.get("body", raw)
        except json.JSONDecodeError:
            pass
    return "", raw


def call_ai_cli(backend: dict, instruction: str) -> str:
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    cmd = [backend["cmd"]] + backend["args"] + [prompt]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode == 0:
        return result.stdout.strip()
    raise RuntimeError(result.stderr[:300])


def call_ai_api_anthropic(backend: dict, instruction: str) -> str:
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={"x-api-key": backend["api_key"], "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
        json={"model": backend["model"], "max_tokens": 4096, "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"].strip()


def call_ai_api_openai(backend: dict, instruction: str) -> str:
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    resp = requests.post(
        backend["url"],
        headers={"Authorization": f"Bearer {backend['api_key']}", "Content-Type": "application/json"},
        json={"model": backend["model"], "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def call_ai_api_gemini(backend: dict, instruction: str) -> str:
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{backend['model']}:generateContent?key={backend['api_key']}"
    resp = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=120)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()


def call_ai_api_qwen(backend: dict, instruction: str) -> str:
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    resp = requests.post(
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
        headers={"Authorization": f"Bearer {backend['api_key']}", "Content-Type": "application/json"},
        json={"model": backend["model"], "input": {"messages": [{"role": "user", "content": prompt}]}},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["output"]["text"].strip()


def call_ai(ai_name: str, backend: dict, instruction: str) -> tuple:
    try:
        t = backend["type"]
        if   t == "cli":           raw = call_ai_cli(backend, instruction)
        elif t == "api_anthropic": raw = call_ai_api_anthropic(backend, instruction)
        elif t == "api_openai":    raw = call_ai_api_openai(backend, instruction)
        elif t == "api_gemini":    raw = call_ai_api_gemini(backend, instruction)
        elif t == "api_qwen":      raw = call_ai_api_qwen(backend, instruction)
        else: raise ValueError(f"未知 AI 类型: {t}")
        return parse_ai_response(raw)
    except subprocess.TimeoutExpired:
        return "", "任务超时（超过3分钟），请拆分为更小的任务。"
    except FileNotFoundError:
        return "", f"未找到命令 {backend.get('cmd', '')}，请确认已安装。"
    except Exception as e:
        log.error(f"AI 调用失败: {e}")
        return "", f"AI 处理出错：{e}"


# ═══════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════

def process_email(mailbox: dict, ai_name: str, backend: dict, em: dict):
    log.info(f"📨 收到指令: [{em['subject']}] 来自 {em['from_email']}")
    instruction = f"发件人：{em['from']}\n主题：{em['subject']}\n\n{em['body']}"

    log.info(f"🤖 [{ai_name}] 处理中...")
    new_subject, reply_body = call_ai(ai_name, backend, instruction)

    if new_subject:
        reply_subject = new_subject
        log.info(f"📝 AI 生成新标题: {new_subject}")
    else:
        reply_subject = em["subject"] if em["subject"].startswith("Re:") else f"Re: {em['subject']}"

    send_reply(mailbox, to=em["from_email"], subject=reply_subject,
               body=reply_body, in_reply_to=em.get("message_id", ""))
    processed_ids.add(em["id"])


def main():
    parser = argparse.ArgumentParser(description="MailMind — 邮件 AI 守护进程")
    parser.add_argument("--mailbox", default=None, help=f"邮箱: {list(MAILBOXES.keys())}")
    parser.add_argument("--ai",      default=None, help=f"AI:  {list(AI_BACKENDS.keys())}")
    parser.add_argument("--list",    action="store_true", help="列出所有配置状态")
    parser.add_argument("--auth",    action="store_true", help="仅执行 OAuth 授权（不启动轮询）")
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
    log.info(f"   轮询间隔 : {POLL_INTERVAL} 秒")

    while True:
        try:
            emails = fetch_unread_emails(mailbox)
            if emails:
                log.info(f"📬 发现 {len(emails)} 封新指令")
                for em in emails:
                    process_email(mailbox, ai_name, backend, em)
            else:
                log.info("📭 暂无新邮件，等待下次轮询...")
        except KeyboardInterrupt:
            log.info("🛑 已停止")
            break
        except Exception as e:
            log.error(f"出错: {e}", exc_info=True)

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()