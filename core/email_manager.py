"""
email_manager.py — Email organization: pending-op store, IMAP search, confirmation, execution.
"""
import os
import json
import re
import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

from core.mail_client import (
    imap_login, imap_move_messages, imap_delete_messages, imap_set_flag,
    imap_add_label, imap_remove_label, imap_archive_messages, imap_search_body,
)
from utils.logger import log

PENDING_OPS_FILE = os.path.join(os.path.dirname(__file__), "..", "pending_email_ops.json")
PENDING_OP_EXPIRY_HOURS = 24

# ────────────────────────────────────────────────────────────────
# Pending-op store
# ────────────────────────────────────────────────────────────────

def _load_pending() -> dict:
    if not os.path.isfile(PENDING_OPS_FILE):
        return {}
    try:
        with open(PENDING_OPS_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    cutoff = (datetime.now() - timedelta(hours=PENDING_OP_EXPIRY_HOURS)).isoformat()
    return {k: v for k, v in raw.items() if v.get("created_at", "") >= cutoff}


def _save_pending(ops: dict):
    tmp = PENDING_OPS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(ops, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PENDING_OPS_FILE)


def add_pending_op(confirmation_msg_id: str, op_data: dict):
    ops = _load_pending()
    ops[confirmation_msg_id] = op_data
    _save_pending(ops)


def get_pending_op(in_reply_to: str) -> Optional[dict]:
    if not in_reply_to:
        return None
    return _load_pending().get(in_reply_to.strip())


def pop_pending_op(in_reply_to: str) -> Optional[dict]:
    ops = _load_pending()
    op = ops.pop(in_reply_to.strip(), None)
    if op is not None:
        _save_pending(ops)
    return op


# ────────────────────────────────────────────────────────────────
# IMAP search
# ────────────────────────────────────────────────────────────────

def _is_ascii_only(s: str) -> bool:
    """Check if string contains only ASCII characters."""
    try:
        s.encode('ascii')
        return True
    except UnicodeEncodeError:
        return False


def search_matching_emails(mailbox: dict, filter_spec: dict) -> tuple:
    """Search emails matching filter_spec. Returns (uid_list, sample_subjects).
    Capped at 200 UIDs to prevent accidental mass operations.
    
    Note: IMAP SEARCH only supports ASCII characters for FROM/SUBJECT.
    Non-ASCII search terms are skipped with a warning log.
    """
    folder = filter_spec.get("folder", "INBOX")

    # Build IMAP SEARCH criteria
    criteria = ["ALL"]
    
    from_val = filter_spec.get("from_contains")
    if from_val:
        if _is_ascii_only(from_val):
            criteria = [f'FROM "{from_val}"']
        else:
            log.warning(f"email_manage: 跳过非 ASCII 的发件人搜索条件 '{from_val}'（IMAP 不支持）")
    
    subject_val = filter_spec.get("subject_contains")
    if subject_val:
        if _is_ascii_only(subject_val):
            criteria.append(f'SUBJECT "{subject_val}"')
        else:
            log.warning(f"email_manage: 跳过非 ASCII 的主题搜索条件 '{subject_val}'（IMAP 不支持）")
    
    if filter_spec.get("since_days"):
        since_date = (datetime.now() - timedelta(days=int(filter_spec["since_days"]))).strftime("%d-%b-%Y")
        criteria.append(f'SINCE {since_date}')
    if filter_spec.get("before_days"):
        before_date = (datetime.now() - timedelta(days=int(filter_spec["before_days"]))).strftime("%d-%b-%Y")
        criteria.append(f'BEFORE {before_date}')
    if filter_spec.get("unread") is True:
        criteria.append("UNSEEN")
    elif filter_spec.get("unread") is False:
        criteria.append("SEEN")

    if filter_spec.get("flagged") is True:
        criteria.append("FLAGGED")
    elif filter_spec.get("flagged") is False:
        criteria.append("UNFLAGGED")

    body_text = filter_spec.get("body_contains")

    search_str = " ".join(criteria)

    mail = imap_login(mailbox)
    uid_list = []
    sample_subjects = []
    try:
        status, _ = mail.select(folder, readonly=True)
        if status != "OK":
            log.warning(f"email_manage: 无法打开文件夹 '{folder}'")
            return [], []

        _, data = mail.uid("search", None, search_str)
        uids = data[0].split() if data[0] else []
        uids = uids[:200]  # safety cap
        uid_list = [u.decode() for u in uids]

        # Optionally narrow by body content (ASCII only)
        if body_text and uid_list:
            if _is_ascii_only(body_text):
                _, bdata = mail.uid("search", None, f'BODY "{body_text}"')
                body_uids = set((bdata[0] or b"").split())
                uid_list = [u for u in uid_list if u.encode() in body_uids]
            else:
                log.warning(f"email_manage: 跳过非 ASCII 的正文搜索条件 '{body_text}'（IMAP 不支持）")

        # Fetch subjects for sample (first 5)
        if uids:
            sample_uids = b",".join(uids[:5])
            _, fetch_data = mail.uid("fetch", sample_uids, "(RFC822.HEADER)")
            from email.header import decode_header as _dh
            def _decode(s):
                if not s:
                    return ""
                parts = _dh(s)
                out = []
                for part, charset in parts:
                    if isinstance(part, bytes):
                        out.append(part.decode(charset or "utf-8", errors="replace"))
                    else:
                        out.append(str(part))
                return "".join(out)

            import email as _email
            for item in fetch_data:
                if isinstance(item, tuple):
                    msg = _email.message_from_bytes(item[1])
                    sample_subjects.append(_decode(msg.get("Subject", "(无主题)")))
    except Exception as e:
        log.error(f"email_manage 搜索失败：{e}")
    finally:
        mail.logout()

    return uid_list, sample_subjects


# ────────────────────────────────────────────────────────────────
# Confirmation email body builder
# ────────────────────────────────────────────────────────────────

_ACTION_LABELS = {
    "zh": {
        "move":          lambda dest: f"移动到文件夹「{dest}」",
        "delete":        lambda _: "删除",
        "mark_read":     lambda _: "标为已读",
        "mark_unread":   lambda _: "标为未读",
        "star":          lambda _: "加星标",
        "unstar":        lambda _: "取消星标",
        "archive":       lambda _: "归档",
        "label":         lambda dest: f"添加标签「{dest}」",
        "unlabel":       lambda dest: f"移除标签「{dest}」",
    },
    "ja": {
        "move":          lambda dest: f"「{dest}」フォルダへ移動",
        "delete":        lambda _: "削除",
        "mark_read":     lambda _: "既読にする",
        "mark_unread":   lambda _: "未読にする",
        "star":          lambda _: "スターを付ける",
        "unstar":        lambda _: "スターを外す",
        "archive":       lambda _: "アーカイブ",
        "label":         lambda dest: f"ラベル「{dest}」を追加",
        "unlabel":       lambda dest: f"ラベル「{dest}」を削除",
    },
    "en": {
        "move":          lambda dest: f"Move to '{dest}'",
        "delete":        lambda _: "Delete",
        "mark_read":     lambda _: "Mark as read",
        "mark_unread":   lambda _: "Mark as unread",
        "star":          lambda _: "Star",
        "unstar":        lambda _: "Unstar",
        "archive":       lambda _: "Archive",
        "label":         lambda dest: f"Add label '{dest}'",
        "unlabel":       lambda dest: f"Remove label '{dest}'",
    },
}

_FILTER_DESC = {
    "zh": {
        "from_contains":    lambda v: f"发件人含「{v}」",
        "subject_contains": lambda v: f"主题含「{v}」",
        "body_contains":    lambda v: f"正文含「{v}」",
        "since_days":       lambda v: f"{v} 天内",
        "before_days":      lambda v: f"{v} 天前",
        "unread":           lambda v: "未读" if v else "已读",
        "flagged":          lambda v: "已加星标" if v else "未加星标",
        "folder":           lambda v: f"文件夹「{v}」",
    },
    "ja": {
        "from_contains":    lambda v: f"差出人に「{v}」を含む",
        "subject_contains": lambda v: f"件名に「{v}」を含む",
        "body_contains":    lambda v: f"本文に「{v}」を含む",
        "since_days":       lambda v: f"{v} 日以内",
        "before_days":      lambda v: f"{v} 日以上前",
        "unread":           lambda v: "未読" if v else "既読",
        "flagged":          lambda v: "スター付き" if v else "スターなし",
        "folder":           lambda v: f"フォルダ「{v}」",
    },
    "en": {
        "from_contains":    lambda v: f"from contains '{v}'",
        "subject_contains": lambda v: f"subject contains '{v}'",
        "body_contains":    lambda v: f"body contains '{v}'",
        "since_days":       lambda v: f"within last {v} days",
        "before_days":      lambda v: f"older than {v} days",
        "unread":           lambda v: "unread" if v else "read",
        "flagged":          lambda v: "starred" if v else "unstarred",
        "folder":           lambda v: f"folder '{v}'",
    },
}

_CONFIRM_INSTRS = {
    "zh": ("✅ 回复「确认执行」开始整理", "❌ 回复「取消」放弃操作", "（确认邮件将在 24 小时后失效）"),
    "ja": ("✅「確認実行」と返信して整理を開始", "❌「キャンセル」と返信して中止", "（確認メールは 24 時間後に失効します）"),
    "en": ("✅ Reply '确认执行' to proceed", "❌ Reply '取消' to cancel", "(This confirmation expires in 24 hours)"),
}


def build_confirmation_body(op_data: dict, lang: str = "zh") -> str:
    count = op_data.get("matched_count", 0)
    action = op_data.get("action", "move")
    dest = op_data.get("target_folder", "")
    filter_spec = op_data.get("filter", {})
    samples = op_data.get("sample_subjects", [])

    labels = _ACTION_LABELS.get(lang, _ACTION_LABELS["zh"])
    action_label = labels.get(action, lambda d: action)(dest)

    fdesc_map = _FILTER_DESC.get(lang, _FILTER_DESC["zh"])
    filter_parts = []
    for key, fn in fdesc_map.items():
        if key in filter_spec and filter_spec[key] is not None:
            filter_parts.append(fn(filter_spec[key]))
    filter_summary = "、".join(filter_parts) if filter_parts else (
        {"zh": "所有邮件", "ja": "すべてのメール", "en": "all emails"}.get(lang, "all emails")
    )

    lines = []
    if lang == "zh":
        lines.append(f"MailMindHub 将对邮箱执行以下整理操作：\n")
        lines.append(f"  操作：{action_label}")
        lines.append(f"  筛选：{filter_summary}")
        lines.append(f"  匹配：{count} 封邮件\n")
        if samples:
            lines.append("邮件样本（最多显示5封）：")
            for i, s in enumerate(samples[:5], 1):
                lines.append(f"  {i}. {s[:60]}")
            lines.append("")
    elif lang == "ja":
        lines.append(f"MailMindHub は以下のメール整理を実行します：\n")
        lines.append(f"  操作：{action_label}")
        lines.append(f"  条件：{filter_summary}")
        lines.append(f"  対象：{count} 件のメール\n")
        if samples:
            lines.append("メールのサンプル（最大5件）：")
            for i, s in enumerate(samples[:5], 1):
                lines.append(f"  {i}. {s[:60]}")
            lines.append("")
    else:
        lines.append(f"MailMindHub will perform the following email organization:\n")
        lines.append(f"  Action: {action_label}")
        lines.append(f"  Filter: {filter_summary}")
        lines.append(f"  Matched: {count} emails\n")
        if samples:
            lines.append("Email samples (up to 5):")
            for i, s in enumerate(samples[:5], 1):
                lines.append(f"  {i}. {s[:60]}")
            lines.append("")

    sep = "━" * 36
    lines.append(sep)
    confirm_line, cancel_line, expiry_line = _CONFIRM_INSTRS.get(lang, _CONFIRM_INSTRS["zh"])
    lines.append(confirm_line)
    lines.append(cancel_line)
    lines.append(expiry_line)

    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────
# Execution
# ────────────────────────────────────────────────────────────────

def execute_email_manage_op(mailbox: dict, op_data: dict, lang: str = "zh") -> str:
    """Execute the pending email operation. Returns a human-readable result string."""
    action = op_data.get("action", "move")
    uid_list = op_data.get("matched_ids", [])
    folder = op_data.get("filter", {}).get("folder", "INBOX")
    dest = op_data.get("target_folder", "")

    if not uid_list:
        return {"zh": "没有找到需要操作的邮件。", "ja": "対象メールが見つかりません。", "en": "No emails to process."}.get(lang, "No emails.")

    mail = imap_login(mailbox)
    count = 0
    try:
        status, _ = mail.select(folder)
        if status != "OK":
            return {"zh": f"无法打开文件夹「{folder}」。", "ja": f"フォルダ「{folder}」を開けませんでした。", "en": f"Cannot open folder '{folder}'."}.get(lang, f"Cannot open '{folder}'.")

        if action == "move":
            count = imap_move_messages(mail, uid_list, dest)
        elif action == "delete":
            trash_folder = mailbox.get("trash_folder", "")
            if trash_folder:
                count = imap_move_messages(mail, uid_list, trash_folder)
            else:
                count = imap_delete_messages(mail, uid_list)
        elif action == "mark_read":
            count = imap_set_flag(mail, uid_list, "\\Seen", add=True)
        elif action == "mark_unread":
            count = imap_set_flag(mail, uid_list, "\\Seen", add=False)
        elif action == "star":
            count = imap_set_flag(mail, uid_list, "\\Flagged", add=True)
        elif action == "unstar":
            count = imap_set_flag(mail, uid_list, "\\Flagged", add=False)
        elif action == "archive":
            count = imap_archive_messages(mail, uid_list, mailbox)
        elif action == "label":
            count = imap_add_label(mail, uid_list, dest)
        elif action == "unlabel":
            count = imap_remove_label(mail, uid_list, dest)
        else:
            return f"未知操作类型：{action}"
    except Exception as e:
        log.error(f"execute_email_manage_op 失败：{e}")
        return {"zh": f"执行出错：{e}", "ja": f"実行エラー：{e}", "en": f"Execution error: {e}"}.get(lang, str(e))
    finally:
        mail.logout()

    total = len(uid_list)
    failed = total - count
    if lang == "zh":
        action_past = {
            "move": f"移动到「{dest}」", "delete": "删除", "mark_read": "标为已读",
            "mark_unread": "标为未读", "star": "加星标", "unstar": "取消星标",
            "archive": "归档", "label": f"添加标签「{dest}」", "unlabel": f"移除标签「{dest}」",
        }.get(action, action)
        return f"✅ 邮件整理完成！\n\n已{action_past} {count} 封\n失败 {failed} 封\n合计 {total} 封"
    elif lang == "ja":
        action_past = {
            "move": f"「{dest}」へ移動", "delete": "削除", "mark_read": "既読化",
            "mark_unread": "未読化", "star": "スター付与", "unstar": "スター削除",
            "archive": "アーカイブ", "label": f"ラベル「{dest}」追加", "unlabel": f"ラベル「{dest}」削除",
        }.get(action, action)
        return f"✅ メール整理が完了しました！\n\n{action_past}：{count} 件\n失敗：{failed} 件\n合計：{total} 件"
    else:
        action_past = {
            "move": f"moved to '{dest}'", "delete": "deleted", "mark_read": "marked as read",
            "mark_unread": "marked as unread", "star": "starred", "unstar": "unstarred",
            "archive": "archived", "label": f"labeled '{dest}'", "unlabel": f"unlabeled '{dest}'",
        }.get(action, action)
        return f"✅ Email organization complete!\n\nSuccessfully {action_past}: {count}\nFailed: {failed}\nTotal: {total}"
