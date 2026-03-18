import smtplib
import os
import re
import uuid
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.utils import make_msgid
from typing import Optional

try:
    import markdown
except ImportError:
    markdown = None

from core.mail_client import get_oauth_token, make_oauth_string
from utils.logger import log

def smtp_login(mailbox: dict):
    server = smtplib.SMTP_SSL(mailbox["smtp_server"], mailbox["smtp_port"]) if mailbox.get("smtp_ssl") else smtplib.SMTP(mailbox["smtp_server"], mailbox["smtp_port"])
    if not mailbox.get("smtp_ssl"):
        server.ehlo()
        server.starttls()
    auth = mailbox.get("auth", "password")
    if auth == "password":
        server.login(mailbox["address"], mailbox["password"])
    else:
        token = get_oauth_token(mailbox)
        server.docmd("AUTH", f"XOAUTH2 {make_oauth_string(mailbox['address'], token)}")
    return server

def send_reply(mailbox: dict, to: str, subject: str, body: str, in_reply_to: str = "", attachments: list = None, extra_headers: dict = None) -> str:
    """Send a reply email. Returns the Message-ID of the sent message.

    Args:
        extra_headers: Optional dict of additional MIME headers to set on the
                       message (e.g. List-Unsubscribe / List-Unsubscribe-Post
                       for RFC 8058 one-click unsubscribe support).
    """
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    footer_plain = f"\n\n---\n✉️  由 MailMindHub AI 自动回复 | {ts}"
    footer_html = f'<br><hr><p style="color: #666; font-size: 12px;">✉️  由 MailMindHub AI 自动回复 | {ts}</p>'

    full_body_plain = body + footer_plain

    msg = MIMEMultipart("mixed")
    msg_id = make_msgid(domain=mailbox["smtp_server"])
    msg["Message-ID"] = msg_id
    msg["From"], msg["To"], msg["Subject"] = mailbox["address"], to, subject
    if in_reply_to:
        msg["In-Reply-To"] = msg["References"] = in_reply_to
    for header_name, header_value in (extra_headers or {}).items():
        msg[header_name] = header_value
    
    alt_part = MIMEMultipart("alternative")
    alt_part.attach(MIMEText(full_body_plain, "plain", "utf-8"))
    
    if markdown:
        try:
            html_content = markdown.markdown(body, extensions=['extra', 'codehilite', 'nl2br'])
            full_body_html = f"""<html><head><style>
                body {{ font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; }}
                pre {{ background-color: #f6f8fa; padding: 10px; border-radius: 5px; overflow-x: auto; }}
                code {{ font-family: SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace; background-color: rgba(27,31,35,0.05); padding: 0.2em 0.4em; border-radius: 3px; }}
                blockquote {{ border-left: 4px solid #dfe2e5; color: #6a737d; padding-left: 1em; margin-left: 0; }}
                table {{ border-collapse: collapse; width: 100%; }}
                table, th, td {{ border: 1px solid #dfe2e5; }}
                th, td {{ padding: 6px 13px; }}
                tr:nth-child(even) {{ background-color: #f6f8fa; }}
            </style></head><body>
            {html_content}
            {footer_html}
            </body></html>"""
            alt_part.attach(MIMEText(full_body_html, "html", "utf-8"))
        except Exception as e:
            log.warning(f"Markdown 转换失败: {e}")
            
    msg.attach(alt_part)
    
    for att in (attachments or []):
        part = MIMEBase("application", "octet-stream")
        content = att["content"]
        if isinstance(content, str):
            content = content.encode("utf-8")
        part.set_payload(content)
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", "attachment", filename=att.get("filename", "file.txt"))
        msg.attach(part)
        
    with smtp_login(mailbox) as s:
        s.sendmail(mailbox["address"], to, msg.as_string())
    log.info(f"✅ 已回复 -> {to} | {subject}")
    return msg_id

def archive_output(output: dict, subject: str, body: str, attachments: Optional[list] = None):
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
