import imaplib
import email
import socket
import ssl
import os
import re
import time
import base64
from email.header import decode_header as _decode_header, Header
from email.utils import parseaddr, formatdate
from email.mime.text import MIMEText
from core.config import MAILBOXES, ATTACHMENT_MAX_SIZE_MB, CONTEXT_MAX_DEPTH
from core.prompts import TEMPLATES, FOLDER_NAMES
from utils.logger import log

# ────────────────────────────────────────────────────────────────
# 核心 IMAP 工具函数
# ────────────────────────────────────────────────────────────────

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
                        log.warning(f"附件 '{filename}' 超出大小限制")
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
    # Increase default timeout to 60s for slow SSL handshakes/connections
    timeout = mailbox.get("timeout", 60)
    try:
        mail = imaplib.IMAP4_SSL(mailbox["imap_server"], mailbox["imap_port"], timeout=timeout)
    except (socket.timeout, ssl.SSLError) as e:
        log.error(f"IMAP SSL 连接/握手超时 ({mailbox['imap_server']}): {e}")
        raise
    except Exception as e:
        log.error(f"IMAP 连接失败 ({mailbox['imap_server']}): {e}")
        raise
    if mailbox.get("imap_id"):
        try:
            mail.xatom("ID", '("name" "mailmind" "version" "1.0")')
        except Exception:
            pass
    auth = mailbox.get("auth", "password")
    if auth in ("password", "app_password"):
        mail.login(mailbox["address"], mailbox["password"])
    else:
        from core.mail_client_oauth import get_oauth_token # 假设拆分了 OAuth
        token = get_oauth_token(mailbox)
        mail.authenticate("XOAUTH2", lambda x: base64.b64encode(f"user={mailbox['address']}\x01auth=Bearer {token}\x01\x01".encode()).decode())
    return mail

def get_archive_folder(mailbox: dict) -> str:
    imap_server = mailbox.get("imap_server", "").lower()
    if "gmail" in imap_server:
        return mailbox.get("archive_folder") or "[Gmail]/All Mail"
    return mailbox.get("archive_folder") or "Archive"

def imap_move_messages(mail, uid_list: list, target_folder: str) -> int:
    if not uid_list: return 0
    success = 0
    try: mail.create(target_folder)
    except Exception: pass
    for uid in uid_list:
        try:
            rv, _ = mail.uid("copy", uid, target_folder)
            if rv == "OK":
                mail.uid("store", uid, "+FLAGS", "\\Deleted")
                success += 1
        except Exception as e:
            log.warning(f"移动 uid={uid} 失败: {e}")
    mail.expunge()
    return success

def imap_archive_messages(mail, uid_list: list, mailbox: dict) -> int:
    return imap_move_messages(mail, uid_list, get_archive_folder(mailbox))

def imap_delete_messages(mail, uid_list: list) -> int:
    """Permanently delete messages by UID."""
    if not uid_list: return 0
    success = 0
    for uid in uid_list:
        try:
            mail.uid("store", uid, "+FLAGS", "\\Deleted")
            success += 1
        except Exception as e:
            log.warning(f"删除 uid={uid} 失败: {e}")
    mail.expunge()
    return success

def imap_set_flag(mail, uid_list: list, flag: str, add: bool = True) -> int:
    r"""Add or remove a flag (e.g. \Seen, \Flagged) on messages by UID."""
    if not uid_list: return 0
    success = 0
    action = "+FLAGS" if add else "-FLAGS"
    flag_str = flag if flag.startswith("\\") else f"\\{flag}"
    for uid in uid_list:
        try:
            mail.uid("store", uid, action, flag_str)
            success += 1
        except Exception as e:
            log.warning(f"设置标志 {flag} uid={uid} 失败: {e}")
    return success

def imap_add_label(mail, uid_list: list, label: str) -> int:
    """Add a Gmail label (via X-GM-LABELS) to messages by UID."""
    if not uid_list: return 0
    success = 0
    for uid in uid_list:
        try:
            mail.uid("STORE", uid, "+X-GM-LABELS", f'({label})')
            success += 1
        except Exception as e:
            log.warning(f"添加标签 '{label}' uid={uid} 失败: {e}")
    return success

def imap_remove_label(mail, uid_list: list, label: str) -> int:
    """Remove a Gmail label (via X-GM-LABELS) from messages by UID."""
    if not uid_list: return 0
    success = 0
    for uid in uid_list:
        try:
            mail.uid("STORE", uid, "-X-GM-LABELS", f'({label})')
            success += 1
        except Exception as e:
            log.warning(f"移除标签 '{label}' uid={uid} 失败: {e}")
    return success

def imap_search_body(mail, folder: str, body_text: str) -> list:
    """Search for messages containing body_text in their body (ASCII only)."""
    try:
        mail.select(folder, readonly=True)
        _, data = mail.uid("search", None, f'BODY "{body_text}"')
        return [u.decode() for u in (data[0] or b"").split()]
    except Exception as e:
        log.warning(f"IMAP BODY 搜索失败: {e}")
        return []

def push_templates_to_mailbox(mailbox: dict, lang: str = "zh") -> int:
    templates = TEMPLATES.get(lang, TEMPLATES["zh"])
    folder = FOLDER_NAMES.get(lang, "MailMindHub_Templates")
    mail = imap_login(mailbox)
    try:
        mail.create(folder)
        status, _ = mail.select(folder)
        if status == "OK":
            _, ids = mail.search(None, "ALL")
            for mid in ids[0].split():
                mail.store(mid, "+FLAGS", "\\Deleted")
            mail.expunge()
        count = 0
        for subject, body in templates:
            msg = MIMEText(body, "plain", "utf-8")
            msg["From"] = mailbox["address"]
            msg["To"] = mailbox["address"]
            msg["Subject"] = Header(subject, "utf-8")
            msg["Date"] = formatdate(localtime=True)
            if mail.append(folder, "(\\Seen)", imaplib.Time2Internaldate(time.time()), msg.as_bytes())[0] == "OK":
                count += 1
        return count
    finally:
        mail.logout()

def fetch_unread_emails(mailbox: dict, processed_ids: set, ids_lock=None, existing_conn=None):
    """Fetch unread emails, checking processed_ids under the given lock for thread safety.
    
    Args:
        existing_conn: Optional existing imapclient.IMAPClient connection (IDLE mode).
                       When provided, uses its API directly without re-login.
    """
    # Detect if existing_conn is an imapclient.IMAPClient (has 'select_folder' method)
    is_imapclient = existing_conn is not None and hasattr(existing_conn, 'select_folder')
    
    if is_imapclient:
        mail = existing_conn
        should_logout = False
        use_imapclient_api = True
    elif existing_conn is not None:
        # Standard imaplib connection
        mail = existing_conn
        should_logout = False
        use_imapclient_api = False
    else:
        mail = imap_login(mailbox)
        should_logout = True
        use_imapclient_api = False
    
    emails = []
    try:
        if use_imapclient_api:
            mail.select_folder("INBOX", readonly=False)
        else:
            status, _ = mail.select("INBOX")
            if status != "OK": return []
        
        try:
            if use_imapclient_api:
                ids = mail.search("UNSEEN")
                ids_bytes = [str(i).encode() for i in ids]
            else:
                _, ids = mail.uid("search", None, "UNSEEN")
                ids_bytes = ids[0].split() if ids and ids[0] else []
        except (imaplib.IMAP4.abort, OSError) as e:
            log.warning(f"IMAP search 超时: {e}")
            return []
        
        if not ids_bytes: return []
        
        for uid in ids_bytes:
            eid = uid.decode() if isinstance(uid, bytes) else str(uid)
            # Thread-safe check-and-add
            if ids_lock is not None:
                with ids_lock:
                    if eid in processed_ids:
                        continue
                    processed_ids.add(eid)
            else:
                if eid in processed_ids:
                    continue
            try:
                if use_imapclient_api:
                    msg_bytes = mail.fetch([int(eid)], ["RFC822"])[int(eid)][b"RFC822"]
                else:
                    _, data = mail.uid("fetch", uid, "(RFC822)")
                    msg_bytes = data[0][1] if data and data[0] else None
                
                if not msg_bytes: continue
                msg = email.message_from_bytes(msg_bytes)
                body, atts = get_body_and_attachments(msg)
                from_raw = decode_str(msg.get("From", ""))
                _, from_addr = parseaddr(from_raw)
                # 自動返信ヘッダを抽出（RFC 3834 / Outlook / 一般的なメーラー）
                auto_submitted = (msg.get("Auto-Submitted") or "").strip().lower()
                x_autoreply   = (msg.get("X-Autoreply") or "").strip().lower()
                precedence     = (msg.get("Precedence") or "").strip().lower()
                x_auto_suppress = (msg.get("X-Auto-Response-Suppress") or "").strip().lower()
                emails.append({
                    "id": eid,
                    "from": from_raw,
                    "from_email": from_addr or from_raw,
                    "subject": decode_str(msg.get("Subject", "(无主题)")),
                    "message_id": msg.get("Message-ID", ""),
                    "in_reply_to": msg.get("In-Reply-To", ""),
                    "references":  msg.get("References", ""),
                    "auto_submitted": auto_submitted,
                    "x_autoreply":    x_autoreply,
                    "precedence":     precedence,
                    "x_auto_response_suppress": x_auto_suppress,
                    "body": body,
                    "attachments": atts
                })
            except (imaplib.IMAP4.abort, OSError, KeyError) as e:
                log.warning(f"IMAP fetch 超时 (uid={eid}): {e}")
                # Revert the mark if fetch timed out (email not fully retrieved)
                if ids_lock is not None:
                    with ids_lock:
                        processed_ids.discard(eid)
                continue
    finally:
        if should_logout:
            try:
                mail.logout()
            except Exception:
                pass
    return emails

def fetch_thread_context(mailbox: dict, references: str, in_reply_to: str = "", max_depth: int = 5) -> str:
    ref_ids = [mid.strip() for mid in (references or "").split() if mid.strip()]
    if in_reply_to: ref_ids.append(in_reply_to.strip())
    if not ref_ids: return ""

    mail = imap_login(mailbox)
    results = []
    try:
        for folder in ["INBOX", "Sent", '"[Gmail]/Sent Mail"']:
            try:
                mail.select(folder, readonly=True)
            except Exception:
                continue
            for mid in ref_ids[-max_depth:]:
                # 转义 IMAP 特殊字符
                safe_mid = mid.replace("\\", "\\\\").replace('"', '\\"')
                try:
                    _, data = mail.search(None, f'HEADER Message-ID "{safe_mid}"')
                    for msg_id in data[0].split():
                        try:
                            _, msg_data = mail.fetch(msg_id, "(RFC822)")
                            body, _ = get_body_and_attachments(email.message_from_bytes(msg_data[0][1]))
                            if body: results.append(body)
                        except Exception:
                            continue
                except Exception:
                    continue
    finally:
        try:
            mail.logout()
        except Exception:
            pass
    return "\n\n---\n\n".join(results)

# ────────────────────────────────────────────────────────────────
# OAuth 兼容接口（供发送端复用）
# ────────────────────────────────────────────────────────────────

def get_oauth_token(mailbox: dict) -> str:
    from core.mail_client_oauth import get_oauth_token as _get_oauth_token
    return _get_oauth_token(mailbox)

def make_oauth_string(email_address: str, token: str) -> str:
    return base64.b64encode(
        f"user={email_address}\x01auth=Bearer {token}\x01\x01".encode()
    ).decode()
