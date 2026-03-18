#!/usr/bin/env python3
"""
MailMindHub — 邮件 → AI 守护进程 (模块化重构版)
"""

import os
import sys
import signal
import time
import re
import json
import argparse
import threading
from datetime import datetime
from typing import Optional

# 核心配置与模块
from core.config import MAILBOXES, AI_BACKENDS, POLL_INTERVAL, DEFAULT_TASK_AI, PROMPT_TEMPLATE, PROMPT_TEMPLATES, AI_CONCURRENCY, AI_MODIFY_SUBJECT, PROMPT_LANG, MAX_EMAIL_CHARS
from core.validator import validate_config
from core.mail_client import fetch_unread_emails, imap_login, get_oauth_token, fetch_thread_context, push_templates_to_mailbox
from core.mail_sender import send_reply, archive_output
from ai.providers import get_ai_provider
from utils.parser import parse_ai_response, auto_detect_tasks, trim_email_body, detect_lang
from utils.logger import log
from tasks.scheduler import scheduler
from tasks.registry import execute_task_logic
from concurrent.futures import ThreadPoolExecutor

# ────────────────────────────────────────────────────────────────
# 帮助 / 模板回复
# ────────────────────────────────────────────────────────────────

_HELP_KEYWORDS = {"help", "帮助", "模板", "template", "templates", "テンプレート", "ヘルプ", "使い方"}

_HELP_BODY = {
    "zh": """\
欢迎使用 MailMindHub！以下是常用指令模板，复制后直接发送即可。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【模板 1】立即提问（AI 直接回答）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
主题：随意
正文：
请帮我分析一下[你的问题或内容]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【模板 2】立即网页搜索
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
主题：随意
正文：
搜索并总结关于[主题]的最新信息

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【模板 3】立即天气查询
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
主题：随意
正文：
查询[城市名]现在的天气

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【模板 4】每日新闻订阅（每天定时发送）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
主题：随意
正文：
每天早上9点发送[主题，如：日本股市、AI行业]的最新新闻摘要，持续到[结束日期，如：2026-12-31]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【模板 5】定时提醒（一次性）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
主题：随意
正文：
在[时间，如：2026-03-20 10:00]提醒我[提醒内容]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【模板 6】每周定时 AI 分析
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
主题：随意
正文：
每周一早上8点帮我分析[主题，如：本周科技热点]并发送邮件

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【模板 7】系统状态报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
主题：随意
正文：
每天下午6点发送一次服务器运行状态报告

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【技能列表】直接用关键词触发
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
发送含有技能关键词的邮件即可触发对应技能。
常用技能：翻译、股票查询、代码审查、摘要、待办管理、数学计算、写诗

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
提示：发送「帮助」可随时重新获取本列表。
""",
    "ja": """\
MailMindHub へようこそ！よく使うテンプレートを以下にまとめました。コピーしてそのままお送りください。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【テンプレート 1】即時AI回答
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
件名：なんでも可
本文：
[質問や内容]を分析・回答してください

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【テンプレート 2】即時ウェブ検索
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
件名：なんでも可
本文：
[トピック]に関する最新情報を検索してまとめてください

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【テンプレート 3】即時天気確認
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
件名：なんでも可
本文：
[都市名]の現在の天気を教えてください

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【テンプレート 4】毎日ニュース配信
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
件名：なんでも可
本文：
毎朝9時に[テーマ、例：日経225・東証]の最新ニュースを送ってください。[終了日、例：2026-12-31]まで

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【テンプレート 5】一回限りのリマインダー
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
件名：なんでも可
本文：
[日時、例：2026-03-20 10:00]に[内容]をリマインドしてください

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【テンプレート 6】毎週定期AI分析
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
件名：なんでも可
本文：
毎週月曜朝8時に[テーマ、例：今週のテクノロジー動向]を分析してメールで送ってください

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【テンプレート 7】サーバー状態レポート
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
件名：なんでも可
本文：
毎日18時にサーバーの稼働状況レポートを送ってください

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【スキル一覧】キーワードで直接起動
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
スキルのキーワードを含むメールを送信するだけで対応スキルが起動します。
主なスキル：翻訳、株価照会、コードレビュー、要約、TODO管理、数式計算、詩作成

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ヒント：「テンプレート」または「ヘルプ」と送るといつでもこの一覧を再取得できます。
""",
    "en": """\
Welcome to MailMindHub! Here are ready-to-use templates — just copy and send.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Template 1] Instant AI Answer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Subject: anything
Body:
Please analyze / answer: [your question]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Template 2] Instant Web Search
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Subject: anything
Body:
Search and summarize the latest info about [topic]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Template 3] Instant Weather
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Subject: anything
Body:
What is the current weather in [city]?

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Template 4] Daily News Digest
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Subject: anything
Body:
Send me a daily news digest about [topic, e.g. AI industry] every morning at 9am until [end date, e.g. 2026-12-31]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Template 5] One-time Reminder
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Subject: anything
Body:
Remind me about [content] at [datetime, e.g. 2026-03-20 10:00]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Template 6] Weekly AI Analysis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Subject: anything
Body:
Every Monday at 8am, analyze [topic, e.g. this week's tech highlights] and email me the results

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Template 7] Server Status Report
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Subject: anything
Body:
Send me a server status report every day at 6pm

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Skills] Trigger directly with keywords
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Send an email containing a skill keyword to trigger the corresponding skill.
Available skills: translate, stock lookup, code review, summarize, todo management, math calculation, poem writing

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tip: Send "help" or "templates" anytime to get this list again.
""",
}

def _is_help_request(em: dict) -> bool:
    subject = (em.get("subject") or "").strip().lower()
    body = (em.get("body") or "").strip().lower()
    return subject in _HELP_KEYWORDS or body in _HELP_KEYWORDS

# 初始化线程池与 AI 并发限速器
executor = ThreadPoolExecutor(max_workers=5)
_ai_semaphore = threading.Semaphore(AI_CONCURRENCY)
_shutdown_event = threading.Event()

def _handle_signal(signum, frame):
    log.info(f"收到信号 {signum}，正在优雅退出...")
    _shutdown_event.set()
    executor.shutdown(wait=False)
    sys.exit(0)

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

# 已处理 ID 路径
PROCESSED_IDS_PATH: Optional[str] = None
processed_ids: set = set()

def _default_processed_ids_path(mailbox_name: str) -> str:
    return os.path.join(os.path.dirname(__file__), f"processed_ids_{mailbox_name}.json")

# Keep only the most recent N processed IDs to prevent unbounded growth
_MAX_PROCESSED_IDS = int(os.environ.get("MAX_PROCESSED_IDS", 5000))

def load_processed_ids(path: str) -> set:
    if not path or not os.path.isfile(path): return set()
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
        # Trim to most recent _MAX_PROCESSED_IDS entries (by sort order as proxy)
        trimmed = sorted(ids)[-_MAX_PROCESSED_IDS:]
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(trimmed, f, indent=2)
        os.replace(path + ".tmp", path)
    except Exception as e:
        log.warning(f"保存 processed_ids 失败：{e}")

# ────────────────────────────────────────────────────────────────

def _get_prompt_template(lang: str) -> str:
    """Return the prompt template for the given language, falling back to PROMPT_LANG."""
    if lang == PROMPT_LANG:
        return PROMPT_TEMPLATE
    tmpl_raw = PROMPT_TEMPLATES.get(lang) or PROMPT_TEMPLATES.get(PROMPT_LANG) or PROMPT_TEMPLATES.get("zh", "")
    return tmpl_raw.replace("{{instruction}}", "{instruction}").replace("{{now}}", "{now}")

def call_ai(ai_name: str, backend: dict, instruction: str, lang: str = None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M (%Z)")
    tmpl = _get_prompt_template(lang or PROMPT_LANG)
    try:
        from skills.loader import get_skills_hint
        hint = get_skills_hint(lang or PROMPT_LANG)
        if hint:
            tmpl = tmpl.replace("{instruction}", hint + "\n{instruction}")
    except Exception:
        pass
    prompt = tmpl.format(instruction=instruction, now=now)
    ai = get_ai_provider(ai_name, backend)
    with _ai_semaphore:
        raw = ai.call(prompt)
    # AI error prefix indicates a failure — return sentinel rather than parse garbage
    if isinstance(raw, str) and raw.startswith("AI 出错："):
        return None
    return parse_ai_response(raw)

def process_email(mailbox_name, ai_name, backend, em):
    log.info(f"📨 收到指令: [{em['subject']}] 来自 {em['from_email']}")

    # 帮助/模板请求：直接回复模板列表，不调用 AI
    if _is_help_request(em):
        log.info("📋 检测到帮助请求，回复模板列表")
        help_body = _HELP_BODY.get(PROMPT_LANG, _HELP_BODY["zh"])
        send_reply(MAILBOXES[mailbox_name], em["from_email"], "MailMindHub 使用模板", help_body, em.get("message_id"))
        processed_ids.add(em["id"])
        save_processed_ids(PROCESSED_IDS_PATH, processed_ids)
        return

    # email_manage 确认回复检测
    if em.get("in_reply_to"):
        from core.email_manager import get_pending_op, pop_pending_op, execute_email_manage_op
        pending_op = get_pending_op(em["in_reply_to"])
        if pending_op:
            body_lower = (em.get("body") or "").strip().lower()
            _CONFIRM = {"确认执行", "确认", "执行", "confirm", "yes", "ok", "確認実行", "確認", "실행"}
            _CANCEL  = {"取消", "cancel", "no", "キャンセル", "取り消し", "취소"}
            is_confirm = any(k in body_lower for k in _CONFIRM)
            is_cancel  = any(k in body_lower for k in _CANCEL)
            if is_confirm or is_cancel:
                pop_pending_op(em["in_reply_to"])
                if is_confirm:
                    log.info(f"✅ email_manage 已确认，开始执行 {len(pending_op.get('matched_ids', []))} 个操作")
                    result = execute_email_manage_op(MAILBOXES[mailbox_name], pending_op, PROMPT_LANG)
                    reply_sub = {"zh": "邮件整理：完成", "ja": "メール整理：完了", "en": "Email organization: done"}.get(PROMPT_LANG, "邮件整理：完成")
                else:
                    log.info("❌ email_manage 已取消")
                    result = {"zh": "操作已取消。", "ja": "操作をキャンセルしました。", "en": "Operation cancelled."}.get(PROMPT_LANG, "操作已取消。")
                    reply_sub = {"zh": "邮件整理：已取消", "ja": "メール整理：キャンセル済み", "en": "Email organization: cancelled"}.get(PROMPT_LANG, "邮件整理：已取消")
                send_reply(MAILBOXES[mailbox_name], em["from_email"], reply_sub, result, em.get("message_id"))
                processed_ids.add(em["id"])
                save_processed_ids(PROCESSED_IDS_PATH, processed_ids)
                return


    # 検出言語を優先、グローバル設定を fallback
    email_text = f"{em.get('subject', '')} {em.get('body', '')}"
    em_lang = detect_lang(email_text)
    lang = em_lang if em_lang in ("zh", "ja", "en") else PROMPT_LANG

    instr = f"发件人：{em['from']}\n主题：{em['subject']}\n\n"
    instr += trim_email_body(em['body'] or "", max_chars=MAX_EMAIL_CHARS)
    for att in em.get("attachments", []):
        if att["is_text"]:
            content = att["content"]
            if len(content) > 5000:
                content = content[:5000] + "...(附件内容过长已截断)"
            instr += f"\n\n--- 附件：{att['filename']} ---\n{content}"

    ai_result = call_ai(ai_name, backend, instr, lang=lang)
    if ai_result is None:
        # AI call failed — notify user and stop processing
        err_msg = {
            "zh": "AI 处理失败，请稍后重试。",
            "ja": "AI の処理に失敗しました。しばらく経ってから再送してください。",
            "en": "AI processing failed, please try again later.",
        }.get(lang, "AI 处理失败，请稍后重试。")
        send_reply(MAILBOXES[mailbox_name], em["from_email"], em["subject"], err_msg, em.get("message_id"))
        processed_ids.add(em["id"])
        save_processed_ids(PROCESSED_IDS_PATH, processed_ids)
        return
    sub, body, sch_at, sch_every, sch_until, sch_cron, atts, task_type, task_payload, output = ai_result

    if not task_type:
        detected_tasks = auto_detect_tasks(trim_email_body(em["body"] or ""))
        if detected_tasks:
            det = detected_tasks[0]
            task_type = det.get("task_type") or task_type
            if not task_payload and det.get("task_payload"): task_payload = det.get("task_payload")
            if not output and det.get("output"): output = det.get("output")
            if not sch_at and det.get("schedule_at"): sch_at = det.get("schedule_at")
            if not sch_every and det.get("schedule_every"): sch_every = det.get("schedule_every")
            if not sch_cron and det.get("schedule_cron"): sch_cron = det.get("schedule_cron")
            if not sch_until and det.get("schedule_until"): sch_until = det.get("schedule_until")

    if AI_MODIFY_SUBJECT and sub:
        # 移除可能的前缀以确保标题干净
        sub = re.sub(r"^(?:Re|RE|回复|回信|答复)[:：]\s*", "", sub, flags=re.I)
    else:
        # 默认不修改标题，也不添加任何前缀
        sub = em["subject"]

    if sch_cron or sch_at or sch_every:
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
            sch_cron,
            task_type or "email",
            task_payload or {},
            output or {},
            atts,
            in_reply_to=em.get("message_id", "")
        )
        def _tl(zh, ja, en):
            return {"zh": zh, "ja": ja, "en": en}.get(lang, zh)
        if sch_cron:
            msg = _tl(
                f"您的任务已按 cron 表达式 [{sch_cron}] 调度，截止至 {sch_until or '未指定'}。\n\n内容预览：\n{body}",
                f"タスクは cron 式 [{sch_cron}] でスケジュールされました（終了：{sch_until or '未指定'}）。\n\n内容プレビュー：\n{body}",
                f"Task scheduled with cron [{sch_cron}], until {sch_until or 'not set'}.\n\nPreview:\n{body}",
            )
            send_reply(MAILBOXES[mailbox_name], em["from_email"], _tl(f"已安排定时任务：{sub}", f"定期タスク設定済み：{sub}", f"Scheduled task: {sub}"), msg)
        elif sch_every:
            msg = _tl(
                f"您的任务将每 {sch_every} 发送一次，截止至 {sch_until or '未指定'}。\n\n内容预览：\n{body}",
                f"タスクは {sch_every} ごとに実行されます（終了：{sch_until or '未指定'}）。\n\n内容プレビュー：\n{body}",
                f"Task will run every {sch_every}, until {sch_until or 'not set'}.\n\nPreview:\n{body}",
            )
            send_reply(MAILBOXES[mailbox_name], em["from_email"], _tl(f"已安排定时任务：{sub}", f"定期タスク設定済み：{sub}", f"Scheduled task: {sub}"), msg)
        else:
            msg = _tl(
                f"您的任务已安排在 {sch_at} 左右执行。\n\n内容预览：\n{body}",
                f"タスクは {sch_at} 頃に実行されます。\n\n内容プレビュー：\n{body}",
                f"Task scheduled for {sch_at}.\n\nPreview:\n{body}",
            )
            send_reply(MAILBOXES[mailbox_name], em["from_email"], _tl(f"已安排定时任务：{sub}", f"タスク設定済み：{sub}", f"Scheduled task: {sub}"), msg)
    elif task_type == "email_manage":
        log.info("📂 email_manage：执行邮件整理（干运行+确认）")
        from core.email_manager import search_matching_emails, build_confirmation_body, add_pending_op
        filter_spec   = (task_payload or {}).get("filter", {})
        action        = (task_payload or {}).get("action", "move")
        target_folder = (task_payload or {}).get("target_folder", "")
        uid_list, sample_subjects = search_matching_emails(MAILBOXES[mailbox_name], filter_spec)
        if not uid_list:
            no_match = {"zh": "未找到符合条件的邮件，请检查筛选条件是否正确。", "ja": "条件に一致するメールが見つかりませんでした。", "en": "No emails matched the filter criteria."}.get(PROMPT_LANG, "未找到符合条件的邮件。")
            send_reply(MAILBOXES[mailbox_name], em["from_email"], sub or em["subject"], no_match, em.get("message_id"))
        else:
            op_data = {
                "mailbox_name": mailbox_name,
                "from_email": em["from_email"],
                "original_msg_id": em.get("message_id", ""),
                "action": action,
                "filter": filter_spec,
                "target_folder": target_folder,
                "matched_ids": uid_list,
                "matched_count": len(uid_list),
                "sample_subjects": sample_subjects[:5],
                "created_at": datetime.now().isoformat(),
            }
            confirm_body = build_confirmation_body(op_data, PROMPT_LANG)
            confirm_sub  = {"zh": f"请确认：{sub or em['subject']}", "ja": f"確認：{sub or em['subject']}", "en": f"Please confirm: {sub or em['subject']}"}.get(PROMPT_LANG, f"请确认：{sub or em['subject']}")
            sent_msg_id  = send_reply(MAILBOXES[mailbox_name], em["from_email"], confirm_sub, confirm_body, em.get("message_id"))
            if sent_msg_id:
                add_pending_op(sent_msg_id, op_data)
                log.info(f"📋 已发送确认邮件，等待用户授权（{len(uid_list)} 封邮件）")
            else:
                log.warning("email_manage: send_reply 未返回 Message-ID，无法存储待确认操作")
    elif task_type and task_type not in ("email", "ai_job"):
        log.info(f"⚡ 立即执行工具任务: {task_type}")
        t_sub, t_body = execute_task_logic({
            "type": task_type,
            "payload": task_payload or {},
            "subject": sub,
            "body": body
        })
        out_conf = output or {"email": True}
        if out_conf.get("email", True):
            send_reply(MAILBOXES[mailbox_name], em["from_email"], t_sub, t_body, em.get("message_id"), atts)
        if out_conf.get("archive", False):
            archive_output(out_conf, t_sub, t_body, atts)
    else:
        send_reply(MAILBOXES[mailbox_name], em["from_email"], sub, body, em.get("message_id"), atts)
    
    processed_ids.add(em["id"])
    save_processed_ids(PROCESSED_IDS_PATH, processed_ids)

def run_poll(mailbox_name, ai_name, backend):
    mailbox = MAILBOXES[mailbox_name]
    interval = POLL_INTERVAL
    log.info(f"✅ {mailbox_name} 轮询模式就绪（每 {interval} 秒）")
    retries = 0
    while True:
        try:
            for em in fetch_unread_emails(mailbox, processed_ids):
                executor.submit(process_email, mailbox_name, ai_name, backend, em)
            retries = 0 # 成功后重置
        except Exception as e:
            retries += 1
            wait_time = min(2 ** retries, 300)
            log.error(f"轮询异常: {e}。{wait_time} 秒后重试 ({retries})...")
            time.sleep(wait_time)
            continue
        time.sleep(interval)

def run_idle(mailbox_name, ai_name, backend):
    try:
        import imapclient
    except ImportError:
        log.warning("imapclient 未安装，自动切换为轮询模式")
        run_poll(mailbox_name, ai_name, backend)
        return
    
    mailbox = MAILBOXES[mailbox_name]
    retries = 0
    while True:
        try:
            with imapclient.IMAPClient(mailbox["imap_server"], ssl=True, timeout=60) as client:
                if mailbox.get("auth") == "password":
                    client.login(mailbox["address"], mailbox["password"])
                else:
                    client.oauth2_login(mailbox["address"], get_oauth_token(mailbox))
                
                if mailbox.get("imap_id"): client.id_({"name": "mailmind"})
                client.select_folder("INBOX")
                
                if b"IDLE" not in client.capabilities():
                    log.warning(f"{mailbox_name} 服务器不支持 IDLE，自动切换为轮询模式")
                    run_poll(mailbox_name, ai_name, backend)
                    return
                
                log.info(f"✅ {mailbox_name} IDLE 就绪")
                retries = 0 # 重置重试计数
                while True:
                    for em in fetch_unread_emails(mailbox, processed_ids):
                        executor.submit(process_email, mailbox_name, ai_name, backend, em)
                    client.idle()
                    client.idle_check(timeout=300)
                    client.idle_done()
        except Exception as e:
            retries += 1
            wait_time = min(2 ** retries, 300) # 指数退避，最高 5 分钟
            log.error(f"IDLE 异常: {e}。{wait_time} 秒后重试 ({retries})...")
            time.sleep(wait_time)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mailbox", default="126")
    parser.add_argument("--ai", default="claude")
    parser.add_argument("--poll", action="store_true", help="轮询模式")
    parser.add_argument("--list", action="store_true", help="显示配置状态")
    parser.add_argument("--push-templates", action="store_true", help="将指令模板写入邮箱文件夹后退出")
    args = parser.parse_args()

    if args.list:
        for name, mb in MAILBOXES.items():
            print(f"  {name:10s} {mb.get('address', '(未配置)')}")
        return

    if args.push_templates:
        mailbox = MAILBOXES.get(args.mailbox)
        if not mailbox:
            print(f"错误：未找到邮箱配置 '{args.mailbox}'")
            sys.exit(1)
        count = push_templates_to_mailbox(mailbox, PROMPT_LANG)
        print(f"✅ 已写入 {count} 个模板到邮箱「{args.mailbox}」")
        return

    # 验证配置
    if not validate_config(MAILBOXES, AI_BACKENDS):
        log.error("配置校验失败，请检查 .env 文件")
        # sys.exit(1)

    global PROCESSED_IDS_PATH, processed_ids
    PROCESSED_IDS_PATH = _default_processed_ids_path(args.mailbox)
    processed_ids = load_processed_ids(PROCESSED_IDS_PATH)

    threading.Thread(target=scheduler.run_forever, daemon=True).start()

    use_poll = args.poll or os.environ.get("MODE", "idle").lower() == "poll"
    log.info(f"🚀 MailMindHub 启动 | 邮箱: {args.mailbox} | AI: {args.ai} | 模式: {'轮询' if use_poll else 'IDLE'}")
    
    backend = AI_BACKENDS[args.ai]
    if use_poll:
        run_poll(args.mailbox, args.ai, backend)
    else:
        run_idle(args.mailbox, args.ai, backend)

if __name__ == "__main__":
    main()
