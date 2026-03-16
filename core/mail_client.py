import imaplib
import email
import os
import json
import logging
import base64
import time
from email.header import decode_header as _decode_header
from email.utils import parseaddr, formatdate
from email.mime.text import MIMEText
from core.config import MAILBOXES, ATTACHMENT_MAX_SIZE_MB, CONTEXT_MAX_DEPTH
from utils.logger import log

# ────────────────────────────────────────────────────────────────
# 模板定义（每条：subject, body）
# ────────────────────────────────────────────────────────────────
_TEMPLATES = {
    "zh": [
        (
            "【模板1】立即提问",
            "请帮我分析以下内容：\n\n[在此填写你的问题或内容]",
        ),
        (
            "【模板2】立即网页搜索",
            "搜索并总结关于[主题]的最新信息",
        ),
        (
            "【模板3】立即天气查询",
            "查询[城市名，如：东京]现在的天气",
        ),
        (
            "【模板4】每日新闻订阅",
            "每天早上9点发送[主题，如：日本股市]的最新新闻摘要，持续到[结束日期，如：2026-12-31]",
        ),
        (
            "【模板5】定时提醒（一次性）",
            "在[时间，如：2026-03-20 10:00]提醒我[提醒内容]",
        ),
        (
            "【模板6】每周AI分析",
            "每周一早上8点帮我分析[主题，如：本周科技热点]并发送邮件",
        ),
        (
            "【模板7】系统状态报告",
            "每天下午6点发送一次服务器运行状态报告",
        ),
    ],
    "ja": [
        (
            "【テンプレート1】即時AI回答",
            "以下の内容を分析・回答してください：\n\n[ここに質問や内容を入力]",
        ),
        (
            "【テンプレート2】即時ウェブ検索",
            "[トピック]に関する最新情報を検索してまとめてください",
        ),
        (
            "【テンプレート3】即時天気確認",
            "[都市名、例：東京]の現在の天気を教えてください",
        ),
        (
            "【テンプレート4】毎日ニュース配信",
            "毎朝9時に[テーマ、例：日経225・東証]の最新ニュースを送ってください。[終了日、例：2026-12-31]まで",
        ),
        (
            "【テンプレート5】一回限りのリマインダー",
            "[日時、例：2026-03-20 10:00]に[内容]をリマインドしてください",
        ),
        (
            "【テンプレート6】毎週定期AI分析",
            "毎週月曜朝8時に[テーマ、例：今週のテクノロジー動向]を分析してメールで送ってください",
        ),
        (
            "【テンプレート7】サーバー状態レポート",
            "毎日18時にサーバーの稼働状況レポートを送ってください",
        ),
    ],
    "en": [
        (
            "[Template 1] Instant AI Answer",
            "Please analyze and answer the following:\n\n[Enter your question or content here]",
        ),
        (
            "[Template 2] Instant Web Search",
            "Search and summarize the latest information about [topic]",
        ),
        (
            "[Template 3] Instant Weather",
            "What is the current weather in [city, e.g. Tokyo]?",
        ),
        (
            "[Template 4] Daily News Digest",
            "Send me a daily news digest about [topic, e.g. AI industry] every morning at 9am until [end date, e.g. 2026-12-31]",
        ),
        (
            "[Template 5] One-time Reminder",
            "Remind me about [content] at [datetime, e.g. 2026-03-20 10:00]",
        ),
        (
            "[Template 6] Weekly AI Analysis",
            "Every Monday at 8am, analyze [topic, e.g. this week's tech highlights] and email me the results",
        ),
        (
            "[Template 7] Server Status Report",
            "Send me a server status report every day at 6pm",
        ),
    ],
}

_FOLDER_NAMES = {
    "zh": "MailMind模板",
    "ja": "MailMindテンプレート",
    "en": "MailMind Templates",
}

def push_templates_to_mailbox(mailbox: dict, lang: str = "zh") -> int:
    """通过 IMAP APPEND 将模板邮件写入邮箱专属文件夹，返回成功写入数量。"""
    templates = _TEMPLATES.get(lang, _TEMPLATES["zh"])
    folder = _FOLDER_NAMES.get(lang, "MailMind Templates")
    address = mailbox["address"]

    mail = imap_login(mailbox)
    try:
        # 创建文件夹（已存在则忽略错误）
        mail.create(folder)
    except Exception:
        pass

    # 清空旧模板（删除已有内容后重写）
    try:
        status, _ = mail.select(folder)
        if status == "OK":
            _, ids = mail.search(None, "ALL")
            for mid in ids[0].split():
                mail.store(mid, "+FLAGS", "\\Deleted")
            mail.expunge()
    except Exception:
        pass

    count = 0
    for subject, body in templates:
        msg = MIMEText(body, "plain", "utf-8")
        msg["From"] = address
        msg["To"] = address
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=True)
        raw = msg.as_bytes()
        try:
            result = mail.append(folder, "", imaplib.Time2Internaldate(time.time()), raw)
            if result[0] == "OK":
                count += 1
            else:
                log.warning(f"模板写入失败：{subject} → {result}")
        except Exception as e:
            log.warning(f"模板写入异常：{subject} → {e}")

    mail.logout()
    log.info(f"📋 已写入 {count}/{len(templates)} 个模板到文件夹「{folder}」")
    return count

def _oauth_google(mailbox: dict) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    SCOPES = ["https://www.googleapis.com/auth/gmail.imap", "https://mail.google.com/"]
    token_file, creds_file = mailbox["oauth_token_file"], mailbox["oauth_creds_file"]
    creds = Credentials.from_authorized_user_file(token_file, SCOPES) if os.path.exists(token_file) else None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
            print(f"\nGmail OAuth 授权链接：\n{auth_url}\n请输入 code:")
            flow.fetch_token(code=input(">>> ").strip())
            creds = flow.credentials
        with open(token_file, "w") as f:
            f.write(creds.to_json())
    return creds.token

def _oauth_microsoft(mailbox: dict) -> str:
    import msal
    client_id, token_file = mailbox.get("oauth_client_id"), mailbox["oauth_token_file"]
    SCOPES = ["https://outlook.office.com/IMAP.AccessAsUser.All", "https://outlook.office.com/SMTP.Send", "offline_access"]
    cache = msal.SerializableTokenCache()
    if os.path.exists(token_file):
        cache.deserialize(open(token_file).read())
    app = msal.PublicClientApplication(client_id, authority="https://login.microsoftonline.com/common", token_cache=cache)
    accounts = app.get_accounts()
    result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        print(f"\nOutlook OAuth 授权：{flow['verification_uri']} 代码：{flow['user_code']}")
        result = app.acquire_token_by_device_flow(flow)
    if cache.has_state_changed:
        with open(token_file, "w") as f:
            f.write(cache.serialize())
    return result["access_token"]

def get_oauth_token(mailbox: dict) -> str:
    auth = mailbox.get("auth", "password")
    if auth == "oauth_google":
        return _oauth_google(mailbox)
    if auth == "oauth_microsoft":
        return _oauth_microsoft(mailbox)
    return ""

def make_oauth_string(address: str, token: str) -> str:
    return base64.b64encode(f"user={address}\x01auth=Bearer {token}\x01\x01".encode()).decode()

def decode_str(s: str) -> str:
    if not s: return ""
    result = []
    for part, charset in _decode_header(s):
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(str(part))
    return "".join(result)

def get_body_and_attachments(msg) -> tuple:
    max_bytes = ATTACHMENT_MAX_SIZE_MB * 1024 * 1024
    body, attachments = "", []
    if msg.is_multipart():
        for part in msg.walk():
            disposition = str(part.get_content_disposition() or "")
            if "attachment" in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    if len(payload) > max_bytes:
                        filename = decode_str(part.get_filename() or "untitled")
                        log.warning(f"附件 '{filename}' 超出大小限制 ({len(payload)//1024}KB > {ATTACHMENT_MAX_SIZE_MB}MB)，已跳过")
                        continue
                    is_text = part.get_content_type().startswith("text/")
                    content = payload.decode(part.get_content_charset() or "utf-8", errors="replace") if is_text else payload
                    attachments.append({"filename": decode_str(part.get_filename() or "untitled"), "content": content, "is_text": is_text})
            elif part.get_content_type() == "text/plain" and not body and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload:
                    body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace").strip()
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            body = payload.decode(msg.get_content_charset() or "utf-8", errors="replace").strip()
    return body, attachments

def imap_login(mailbox: dict):
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
        mail.authenticate("XOAUTH2", lambda x: make_oauth_string(mailbox["address"], token))
    return mail

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

def fetch_unread_emails(mailbox: dict, processed_ids: set):
    mail = imap_login(mailbox)
    allowed = mailbox.get("allowed_senders", [])
    emails = []

    def _fetch_folder(folder: str, id_prefix: str = ""):
        try:
            status, _ = mail.select(folder)
            if status != "OK":
                return
        except Exception:
            return
        _, ids = mail.search(None, "UNSEEN")
        for mid in ids[0].split():
            eid = id_prefix + mid.decode()
            if eid in processed_ids:
                continue
            _, data = mail.fetch(mid, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            sender = decode_str(msg.get("From", ""))
            sender_email = parseaddr(sender)[1].strip()
            if not is_sender_allowed(sender_email, allowed):
                continue
            if id_prefix:
                try:
                    mail.copy(mid, "INBOX")
                    mail.store(mid, "+FLAGS", "\\Deleted")
                    mail.expunge()
                    log.info(f"📥 垃圾邮件移入收件箱: {sender_email}")
                except Exception as e:
                    log.warning(f"移动垃圾邮件失败: {e}")
            body, atts = get_body_and_attachments(msg)
            
            # Extract headers for conversation context
            message_id = msg.get("Message-ID", "")
            in_reply_to = msg.get("In-Reply-To", "")
            references = msg.get("References", "")
            
            emails.append({
                "id": eid, 
                "from": sender, 
                "from_email": sender_email,
                "subject": decode_str(msg.get("Subject", "(无主题)")),
                "message_id": message_id, 
                "in_reply_to": in_reply_to,
                "references": references,
                "body": body, 
                "attachments": atts
            })

    _fetch_folder("INBOX")
    spam_folder = mailbox.get("spam_folder", "")
    if spam_folder:
        _fetch_folder(spam_folder, id_prefix="spam:")

    mail.logout()
    return emails

def fetch_message_content_by_id(mailbox: dict, message_id: str) -> str:
    """根据 Message-ID 获取邮件正文"""
    if not message_id: return ""
    mail = imap_login(mailbox)
    content = ""
    try:
        for folder in ["INBOX", '"[Gmail]/Sent Mail"', "Sent"]:
            try:
                status, _ = mail.select(folder, readonly=True)
                if status != "OK": continue
                _, data = mail.search(None, f'HEADER Message-ID "{message_id}"')
                ids = data[0].split()
                if ids:
                    _, msg_data = mail.fetch(ids[0], "(RFC822)")
                    msg = email.message_from_bytes(msg_data[0][1])
                    body, _ = get_body_and_attachments(msg)
                    content = body
                    break
            except Exception:
                continue
    finally:
        mail.logout()
    return content

def fetch_thread_context(mailbox: dict, references: str, in_reply_to: str = "", max_depth: int = None) -> str:
    """获取完整会话线索（多层上下文），复用单次 IMAP 连接"""
    if max_depth is None:
        max_depth = CONTEXT_MAX_DEPTH

    # Collect all referenced message IDs (References header is space-separated)
    ref_ids: list[str] = []
    if references:
        ref_ids = [mid.strip() for mid in references.split() if mid.strip()]
    if in_reply_to and in_reply_to.strip() and in_reply_to.strip() not in ref_ids:
        ref_ids.append(in_reply_to.strip())
    if not ref_ids:
        return ""

    # Take the most recent max_depth IDs; preserve original order for output
    ref_ids = ref_ids[-max_depth:]
    needed = set(ref_ids)
    results: dict[str, str] = {}

    try:
        mail = imap_login(mailbox)
        for folder in ["INBOX", '"[Gmail]/Sent Mail"', "Sent", '"Sent Messages"']:
            remaining = needed - set(results.keys())
            if not remaining:
                break
            try:
                status, _ = mail.select(folder, readonly=True)
                if status != "OK":
                    continue
                for mid in list(remaining):
                    try:
                        _, data = mail.search(None, f'HEADER Message-ID "{mid}"')
                        ids = data[0].split()
                        if ids:
                            _, msg_data = mail.fetch(ids[0], "(RFC822)")
                            msg = email.message_from_bytes(msg_data[0][1])
                            body, _ = get_body_and_attachments(msg)
                            if body:
                                results[mid] = body
                    except Exception:
                        continue
            except Exception:
                continue
        mail.logout()
    except Exception as e:
        log.warning(f"获取会话上下文失败: {e}")

    if not results:
        return ""

    parts = [results[mid] for mid in ref_ids if mid in results]
    return "\n\n---\n\n".join(parts)
