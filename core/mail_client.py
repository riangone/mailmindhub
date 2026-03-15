import imaplib
import email
import os
import json
import logging
import base64
from email.header import decode_header as _decode_header
from email.utils import parseaddr
from core.config import MAILBOXES
from utils.logger import log

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
        # 尝试在收件箱和已发送中查找
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
