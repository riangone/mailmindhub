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
import subprocess
from datetime import datetime
from typing import Optional

# 核心配置与模块
from core.config import MAILBOXES, AI_BACKENDS, POLL_INTERVAL, DEFAULT_TASK_AI, PROMPT_TEMPLATE, PROMPT_TEMPLATES, AI_CONCURRENCY, AI_MODIFY_SUBJECT, PROMPT_LANG, MAX_EMAIL_CHARS, WORKSPACE_DIR, SHOW_FILE_CHANGES, AI_CLI_TIMEOUT, AI_PROGRESS_INTERVAL
from core.validator import validate_config
from core.mail_client import fetch_unread_emails, imap_login, get_oauth_token, fetch_thread_context, push_templates_to_mailbox, send_templates_to_address
from core.mail_sender import send_reply, archive_output
from ai.providers import get_ai_provider
from utils.parser import parse_ai_response, trim_email_body, detect_lang
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

def call_ai(ai_name: str, backend: dict, instruction: str, lang: str = None, progress_cb=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M (%Z)")
    tmpl = _get_prompt_template(lang or PROMPT_LANG)
    try:
        # Inject AI skills hint
        from ai.skills import get_ai_skills_prompt
        ai_skill_hint = get_ai_skills_prompt(lang or PROMPT_LANG)
        if ai_skill_hint:
            tmpl = ai_skill_hint + "\n\n" + tmpl
        # Inject Python skills hint (backward compatibility)
        from skills.loader import get_skills_hint
        hint = get_skills_hint(lang or PROMPT_LANG)
        if hint:
            tmpl = tmpl.replace("{instruction}", hint + "\n{instruction}")
    except Exception:
        pass
    # Inject WORKSPACE_DIR constraint for CLI AI backends
    if WORKSPACE_DIR and os.path.isdir(WORKSPACE_DIR):
        workspace_hint = f"[WORKSPACE] All file operations MUST be performed inside: {WORKSPACE_DIR}\nDo NOT read or write files outside this directory.\n\n"
        tmpl = workspace_hint + tmpl
    # 安全格式化：转义非占位符的花括号（如 JSON 示例中的 {skill}）
    prompt = tmpl.replace("{", "{{").replace("}", "}}").replace("{{instruction}}", "{instruction}").replace("{{now}}", "{now}").format(instruction=instruction, now=now)
    ai = get_ai_provider(ai_name, backend)
    is_cli = backend.get("type") == "cli"
    with _ai_semaphore:
        if is_cli:
            raw = ai.call(prompt, progress_cb=progress_cb, timeout=AI_CLI_TIMEOUT, progress_interval=AI_PROGRESS_INTERVAL)
        else:
            raw = ai.call(prompt)
    # AI error prefix indicates a failure — return sentinel rather than parse garbage
    if isinstance(raw, str) and raw.startswith("AI 出错："):
        return None
    return parse_ai_response(raw)

def _get_git_diff_summary(workspace_dir: str) -> str:
    """Return git diff --stat output if workspace_dir is a git repo with changes."""
    try:
        if not os.path.exists(os.path.join(workspace_dir, ".git")):
            return ""
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            capture_output=True, text=True, cwd=workspace_dir, timeout=10
        )
        summary = result.stdout.strip()
        if summary:
            return summary
        result2 = subprocess.run(
            ["git", "status", "--short"],
            capture_output=True, text=True, cwd=workspace_dir, timeout=10
        )
        return result2.stdout.strip()
    except Exception as e:
        log.warning(f"获取 git diff 失败: {e}")
        return ""


def process_email(mailbox_name, ai_name, backend, em):
    try:
        _process_email_impl(mailbox_name, ai_name, backend, em)
    except Exception as e:
        import traceback
        log.error(f"处理邮件失败：{e}")
        log.error(traceback.format_exc())
        # 即使失败也标记为已处理，避免无限重试
        processed_ids.add(em["id"])
        save_processed_ids(PROCESSED_IDS_PATH, processed_ids)

def _process_email_impl(mailbox_name, ai_name, backend, em):
    log.info(f"📨 收到指令: [{em['subject']}] 来自 {em['from_email']}")

    # 优先检测语言，用于后续回复
    email_text = f"{em.get('subject', '')} {em.get('body', '')}"
    em_lang = detect_lang(email_text)
    lang = em_lang if em_lang in ("zh", "ja", "en", "ko") else PROMPT_LANG

    instr = f"发件人：{em['from']}\n主题：{em['subject']}\n\n"
    instr += trim_email_body(em['body'] or "", max_chars=MAX_EMAIL_CHARS)
    for att in em.get("attachments", []):
        if att["is_text"]:
            content = att["content"]
            if len(content) > 5000:
                content = content[:5000] + "...(附件内容过长已截断)"
            instr += f"\n\n--- 附件：{att['filename']} ---\n{content}"

    # 追加会话上下文，帮助 AI 理解“纠正/修改”类指令
    thread_ctx = ""
    if em.get("references") or em.get("in_reply_to"):
        try:
            thread_ctx = fetch_thread_context(
                MAILBOXES[mailbox_name],
                em.get("references", ""),
                em.get("in_reply_to", ""),
            )
        except Exception as e:
            log.warning(f"获取会话上下文失败: {e}")
            thread_ctx = ""
    if thread_ctx:
        max_ctx = min(2000, MAX_EMAIL_CHARS)
        if len(thread_ctx) > max_ctx:
            thread_ctx = thread_ctx[:max_ctx] + "...(上下文已截断)"
        instr += f"\n\n--- 会话上下文（供参考） ---\n{thread_ctx}"

    # CLI AI（Claude/Codex 等）は長時間実行になるため、受信確認メールを即時送信
    is_cli = backend.get("type") == "cli"
    if is_cli:
        ack_body = {
            "zh": "✅ 已收到您的请求，AI 正在处理中，请稍候……",
            "ja": "✅ リクエストを受け付けました。AI が処理中です、しばらくお待ちください……",
            "en": "✅ Request received. AI is working on it, please wait……",
            "ko": "✅ 요청을 받았습니다. AI가 처리 중입니다, 잠시만 기다려 주세요……",
        }.get(lang, "✅ 已收到您的请求，AI 正在处理中，请稍候……")
        send_reply(MAILBOXES[mailbox_name], em["from_email"], em["subject"], ack_body, em.get("message_id"), lang=lang)

    # 进度回调：CLI AI 运行期间每隔 AI_PROGRESS_INTERVAL 秒发送进度邮件
    def _progress_cb(elapsed_s: int):
        mins, secs = divmod(elapsed_s, 60)
        msg = {
            "zh": f"⏳ AI 仍在处理中……已用时 {mins} 分 {secs} 秒",
            "ja": f"⏳ AI はまだ処理中です……経過時間 {mins} 分 {secs} 秒",
            "en": f"⏳ AI is still working…… elapsed {mins}m {secs}s",
            "ko": f"⏳ AI가 아직 처리 중입니다…… 경과 시간 {mins}분 {secs}초",
        }.get(lang, f"⏳ AI 仍在处理中……已用时 {mins} 分 {secs} 秒")
        send_reply(MAILBOXES[mailbox_name], em["from_email"], em["subject"], msg, em.get("message_id"), lang=lang)

    _ai_start = time.time()
    ai_result = call_ai(ai_name, backend, instr, lang=lang, progress_cb=_progress_cb if is_cli else None)
    _ai_ms = int((time.time() - _ai_start) * 1000)
    if ai_result is None:
        # AI call failed — notify user and stop processing
        scheduler.record_stat(mailbox_name, "error", _ai_ms, em.get("subject"))
        err_msg = {
            "zh": "AI 处理失败，请稍后重试。",
            "ja": "AI の処理に失敗しました。しばらく経ってから再送してください。",
            "en": "AI processing failed, please try again later.",
            "ko": "AI 처리 실패, 잠시 후 다시 시도해 주세요.",
        }.get(lang, "AI 处理失败，请稍后重试。")
        send_reply(MAILBOXES[mailbox_name], em["from_email"], em["subject"], err_msg, em.get("message_id"), lang=lang)
        processed_ids.add(em["id"])
        save_processed_ids(PROCESSED_IDS_PATH, processed_ids)
        return
    scheduler.record_stat(mailbox_name, "success", _ai_ms, em.get("subject"))
    sub, body, sch_at, sch_every, sch_until, sch_cron, atts, task_type, task_payload, output = ai_result

    # email_manage 确认回复检测（先经 AI，再执行）
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
                    result = execute_email_manage_op(MAILBOXES[mailbox_name], pending_op, lang)
                    reply_sub = {"zh": "邮件整理：完成", "ja": "メール整理：完了", "en": "Email organization: done", "ko": "이메일 정리: 완료"}.get(lang, "邮件整理：完成")
                else:
                    log.info("❌ email_manage 已取消")
                    result = {"zh": "操作已取消。", "ja": "操作をキャンセルしました。", "en": "Operation cancelled.", "ko": "작업이 취소되었습니다."}.get(lang, "操作已取消。")
                    reply_sub = {"zh": "邮件整理：已取消", "ja": "メール整理：キャンセル済み", "en": "Email organization: cancelled", "ko": "이메일 정리: 취소됨"}.get(lang, "邮件整理：已取消")
                send_reply(MAILBOXES[mailbox_name], em["from_email"], reply_sub, result, em.get("message_id"), lang=lang)
                processed_ids.add(em["id"])
                save_processed_ids(PROCESSED_IDS_PATH, processed_ids)
                return

    # 帮助/模板请求：先经 AI，再按请求回复模板列表
    if _is_help_request(em):
        log.info("📋 检测到帮助请求，回复模板列表")
        help_body = _HELP_BODY.get(lang, _HELP_BODY["zh"])
        send_reply(MAILBOXES[mailbox_name], em["from_email"], "MailMindHub 使用模板", help_body, em.get("message_id"), lang=lang)
        processed_ids.add(em["id"])
        save_processed_ids(PROCESSED_IDS_PATH, processed_ids)
        return

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
            in_reply_to=em.get("message_id", ""),
            lang=lang
        )
        def _tl(zh, ja, en, ko):
            return {"zh": zh, "ja": ja, "en": en, "ko": ko}.get(lang, zh)
        if sch_cron:
            msg = _tl(
                f"您的任务已按 cron 表达式 [{sch_cron}] 调度，截止至 {sch_until or '未指定'}。\n\n内容预览：\n{body}",
                f"タスクは cron 式 [{sch_cron}] でスケジュールされました（終了：{sch_until or '未指定'}）。\n\n内容プレビュー：\n{body}",
                f"Task scheduled with cron [{sch_cron}], until {sch_until or 'not set'}.\n\nPreview:\n{body}",
                f"작업이 cron 표현식 [{sch_cron}]에 따라 예약되었습니다 (종료: {sch_until or '지정되지 않음'}).\n\n내용 미리보기:\n{body}",
            )
            send_reply(MAILBOXES[mailbox_name], em["from_email"], _tl(f"已安排定时任务：{sub}", f"定期タスク設定済み：{sub}", f"Scheduled task: {sub}", f"예약 작업 설정됨: {sub}"), msg, lang=lang)
        elif sch_every:
            msg = _tl(
                f"您的任务将每 {sch_every} 发送一次，截止至 {sch_until or '未指定'}。\n\n内容预览：\n{body}",
                f"タスクは {sch_every} ごとに実行されます（終了：{sch_until or '未指定'}）。\n\n内容プレビュー：\n{body}",
                f"Task will run every {sch_every}, until {sch_until or 'not set'}.\n\nPreview:\n{body}",
                f"작업이 매 {sch_every}마다 실행됩니다 (종료: {sch_until or '지정되지 않음'}).\n\n내용 미리보기:\n{body}",
            )
            send_reply(MAILBOXES[mailbox_name], em["from_email"], _tl(f"已安排定时任务：{sub}", f"定期タスク設定済み：{sub}", f"Scheduled task: {sub}", f"예약 작업 설정됨: {sub}"), msg, lang=lang)
        else:
            msg = _tl(
                f"您的任务已安排在 {sch_at} 左右执行。\n\n内容预览：\n{body}",
                f"タスクは {sch_at} 頃に実行されます。\n\n内容プレビュー：\n{body}",
                f"Task scheduled for {sch_at}.\n\nPreview:\n{body}",
                f"작업이 {sch_at} 경에 실행되도록 예약되었습니다.\n\n내용 미리보기:\n{body}",
            )
            send_reply(MAILBOXES[mailbox_name], em["from_email"], _tl(f"已安排定时任务：{sub}", f"タスク設定済み：{sub}", f"Scheduled task: {sub}", f"예약 작업 설정됨: {sub}"), msg, lang=lang)
    elif task_type == "email_manage":
        log.info("📂 email_manage：执行邮件整理（干运行+确认）")
        from core.email_manager import search_matching_emails, build_confirmation_body, add_pending_op
        filter_spec   = (task_payload or {}).get("filter", {})
        action        = (task_payload or {}).get("action", "move")
        target_folder = (task_payload or {}).get("target_folder", "")
        uid_list, sample_subjects = search_matching_emails(MAILBOXES[mailbox_name], filter_spec)
        if not uid_list:
            no_match = {"zh": "未找到符合条件的邮件，请检查筛选条件是否正确。", "ja": "条件に一致するメールが見つかりませんでした。", "en": "No emails matched the filter criteria.", "ko": "조건에 일치하는 이메일을 찾을 수 없습니다."}.get(lang, "未找到符合条件的邮件。")
            send_reply(MAILBOXES[mailbox_name], em["from_email"], sub or em["subject"], no_match, em.get("message_id"), lang=lang)
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
            confirm_body = build_confirmation_body(op_data, lang)
            confirm_sub  = {"zh": f"请确认：{sub or em['subject']}", "ja": f"確認：{sub or em['subject']}", "en": f"Please confirm: {sub or em['subject']}", "ko": f"확인 부탁드립니다: {sub or em['subject']}"}.get(lang, f"请确认：{sub or em['subject']}")
            sent_msg_id  = send_reply(MAILBOXES[mailbox_name], em["from_email"], confirm_sub, confirm_body, em.get("message_id"), lang=lang)
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
        }, lang=lang, progress_cb=_progress_cb if is_cli else None)
        out_conf = output or {"email": True}
        if out_conf.get("email", True):
            send_reply(MAILBOXES[mailbox_name], em["from_email"], t_sub, t_body, em.get("message_id"), atts, lang=lang)
        if out_conf.get("archive", False):
            archive_output(out_conf, t_sub, t_body, atts)
    else:
        # CLI AI が WORKSPACE_DIR でファイルを変更した場合、git diff サマリを添付
        reply_body = body
        if is_cli and WORKSPACE_DIR and SHOW_FILE_CHANGES:
            diff_summary = _get_git_diff_summary(WORKSPACE_DIR)
            if diff_summary:
                diff_label = {
                    "zh": "📁 文件变更摘要",
                    "ja": "📁 ファイル変更サマリ",
                    "en": "📁 File changes",
                    "ko": "📁 파일 변경 사항",
                }.get(lang, "📁 文件变更摘要")
                reply_body = (reply_body or "") + f"\n\n---\n{diff_label}：\n```\n{diff_summary}\n```"
        send_reply(MAILBOXES[mailbox_name], em["from_email"], sub, reply_body, em.get("message_id"), atts, lang=lang)

    processed_ids.add(em["id"])
    save_processed_ids(PROCESSED_IDS_PATH, processed_ids)

def _channel_reply(em: dict, subject: str, body: str):
    """Send reply via channel's _reply_fn."""
    reply_fn = em.get("_reply_fn")
    if callable(reply_fn):
        try:
            reply_fn(em["from_email"], subject, body)
        except Exception as e:
            log.warning(f"[Channel:{em.get('channel')}] 回复失败: {e}")


def process_channel_message(channel_name: str, ai_name: str, backend: dict, em: dict):
    """Process a single message from a non-email channel (Telegram/Discord)."""
    try:
        from skills.loader import get_skills_hint
        email_text = f"{em.get('subject', '')} {em.get('body', '')}"
        lang = detect_lang(email_text)
        if lang not in ("zh", "ja", "en", "ko"):
            lang = PROMPT_LANG

        # Help request
        if _is_help_request(em):
            help_body = _HELP_BODY.get(lang, _HELP_BODY["zh"])
            _channel_reply(em, "MailMindHub 使用模板", help_body)
            return

        instr = f"发件人：{em['from']}\n主题：{em['subject']}\n\n"
        instr += trim_email_body(em.get("body", ""), max_chars=MAX_EMAIL_CHARS)

        template = PROMPT_TEMPLATES.get(lang, PROMPT_TEMPLATE)
        skills_hint = get_skills_hint(lang)
        prompt = f"{template}\n\n{skills_hint}\n\n{instr}" if skills_hint else f"{template}\n\n{instr}"

        ai_result = call_ai(ai_name, backend, prompt, lang=lang)
        if ai_result is None:
            err_msg = {"zh": "AI 处理失败，请稍后重试。", "ja": "AI の処理に失敗しました。",
                       "en": "AI processing failed.", "ko": "AI 처리 실패."}.get(lang, "AI 处理失败。")
            _channel_reply(em, em["subject"], err_msg)
            return

        sub, body, sch_at, sch_every, sch_until, sch_cron, atts, task_type, task_payload, output = ai_result

        if sch_cron or sch_at or sch_every:
            # For scheduled tasks from channels, use a virtual mailbox "channel:<name>"
            # The scheduler will attempt email delivery; reply with confirmation only
            def _tl(zh, ja, en, ko):
                return {"zh": zh, "ja": ja, "en": en, "ko": ko}.get(lang, zh)
            msg = _tl(
                f"您的任务已安排，内容预览：\n{body}",
                f"タスクが設定されました。\n{body}",
                f"Task scheduled.\n{body}",
                f"작업이 예약되었습니다.\n{body}",
            )
            _channel_reply(em, _tl(f"已安排任务：{sub}", f"タスク設定済み：{sub}", f"Scheduled: {sub}", f"예약됨: {sub}"), msg)
        elif task_type and task_type not in ("email", "ai_job"):
            log.info(f"[Channel:{channel_name}] 执行工具任务: {task_type}")
            t_sub, t_body = execute_task_logic({"type": task_type, "payload": task_payload or {},
                                                 "subject": sub, "body": body}, lang=lang)
            _channel_reply(em, t_sub, t_body)
        else:
            _channel_reply(em, sub or em["subject"], body)

    except Exception as e:
        import traceback
        log.error(f"[Channel:{channel_name}] 处理消息失败: {e}\n{traceback.format_exc()}")


def run_channel_loop(channel, ai_name: str, backend: dict):
    """Poll a channel adapter for new messages and process them."""
    channel_ids_file = os.path.join(
        os.path.dirname(__file__),
        f"processed_ids_{channel.name}.json"
    )
    ch_processed: set = set()
    if os.path.isfile(channel_ids_file):
        try:
            ch_processed = set(json.load(open(channel_ids_file)))
        except Exception:
            ch_processed = set()

    log.info(f"✅ Channel [{channel.name}] 已就绪")
    interval = int(os.environ.get("CHANNEL_POLL_INTERVAL", "5"))

    while True:
        try:
            messages = channel.poll_messages(ch_processed)
            for em in messages:
                ch_processed.add(em["id"])
                executor.submit(process_channel_message, channel.name, ai_name, backend, em)
            # Persist processed IDs (keep last 2000)
            if len(ch_processed) > 2000:
                ch_processed = set(list(ch_processed)[-2000:])
            with open(channel_ids_file, "w") as f:
                json.dump(list(ch_processed), f)
        except Exception as e:
            log.warning(f"[Channel:{channel.name}] 轮询异常: {e}")
        time.sleep(interval)


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

def run_gmail_push(mailbox_name: str, ai_name: str, backend: dict):
    """
    Gmail Push mode: receive Pub/Sub webhooks via webui/server.py,
    fetch new messages via Gmail API, and process them.

    Requires:
      - GMAIL_PUBSUB_TOPIC env var set
      - webui/server.py running (provides /webhook/gmail endpoint)
      - google-api-python-client installed
    """
    try:
        from core.gmail_pubsub import (
            gmail_watch, gmail_fetch_history, gmail_get_message,
            store_history_id, load_history_id,
        )
        from webui.server import gmail_push_queue
    except ImportError as e:
        log.error(f"[GmailPush] 依赖缺失，切换到 IDLE 模式: {e}")
        run_idle(mailbox_name, ai_name, backend)
        return

    mailbox = MAILBOXES[mailbox_name]

    # Register watch and get initial historyId
    try:
        watch_result = gmail_watch(mailbox)
        history_id   = str(watch_result.get("historyId", ""))
        if history_id:
            store_history_id(mailbox_name, history_id)
    except Exception as e:
        log.error(f"[GmailPush] 注册 watch 失败: {e}")
        log.info("[GmailPush] 回退到 IMAP IDLE 模式")
        run_idle(mailbox_name, ai_name, backend)
        return

    # Track when to renew the watch (expires after 7 days)
    import queue as _q
    watch_renewed_at = time.time()
    WATCH_RENEW_INTERVAL = 6 * 24 * 3600  # 6 days

    log.info(f"✅ [GmailPush] {mailbox_name} Gmail Push 就绪，等待 Pub/Sub 通知...")

    while True:
        # Renew watch before it expires
        if time.time() - watch_renewed_at > WATCH_RENEW_INTERVAL:
            try:
                watch_result = gmail_watch(mailbox)
                history_id   = str(watch_result.get("historyId", history_id))
                store_history_id(mailbox_name, history_id)
                watch_renewed_at = time.time()
                log.info("[GmailPush] Watch 已续期")
            except Exception as e:
                log.warning(f"[GmailPush] Watch 续期失败: {e}")

        # Wait for push event (block up to 10 seconds)
        try:
            event = gmail_push_queue.get(timeout=10)
        except _q.Empty:
            continue

        new_history_id = event.get("history_id", "")
        if not new_history_id:
            continue

        log.info(f"[GmailPush] 收到推送通知 historyId={new_history_id}")

        # Fetch new message IDs since last known historyId
        try:
            start_id = load_history_id(mailbox_name) or history_id
            new_msg_ids = gmail_fetch_history(mailbox, start_id)
            store_history_id(mailbox_name, new_history_id)
            history_id = new_history_id
        except Exception as e:
            log.error(f"[GmailPush] history.list 失败: {e}")
            continue

        for msg_id in new_msg_ids:
            uid = f"gmail_api:{msg_id}"
            if uid in processed_ids:
                continue
            em = gmail_get_message(mailbox, msg_id)
            if em is None:
                continue
            # Check allowed senders
            allowed = mailbox.get("allowed_senders", [])
            if allowed and em["from_email"] not in allowed:
                log.debug(f"[GmailPush] 忽略非白名单发件人: {em['from_email']}")
                processed_ids.add(uid)
                continue
            executor.submit(process_email, mailbox_name, ai_name, backend, em)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mailbox", default="126")
    parser.add_argument("--ai", default="claude")
    parser.add_argument("--poll", action="store_true", help="轮询模式")
    parser.add_argument("--gmail-push", dest="gmail_push", action="store_true",
                        help="Gmail Push 模式（通过 Google Pub/Sub 推送通知，需配置 GMAIL_PUBSUB_TOPIC）")
    parser.add_argument("--list", action="store_true", help="显示配置状态")
    parser.add_argument("--push-templates", action="store_true", help="将指令模板写入守护进程邮箱文件夹后退出")
    parser.add_argument("--push-templates-to", metavar="EMAIL", help="通过 SMTP 将模板发送到指定邮箱后退出")
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

    if args.push_templates_to:
        mailbox = MAILBOXES.get(args.mailbox)
        if not mailbox:
            print(f"错误：未找到邮箱配置 '{args.mailbox}'")
            sys.exit(1)
        count = send_templates_to_address(mailbox, args.push_templates_to, PROMPT_LANG)
        print(f"✅ 已发送 {count} 个模板到 {args.push_templates_to}")
        return

    # 验证配置
    if not validate_config(MAILBOXES, AI_BACKENDS):
        log.error("配置校验失败，请检查 .env 文件")
        # sys.exit(1)

    global PROCESSED_IDS_PATH, processed_ids
    PROCESSED_IDS_PATH = _default_processed_ids_path(args.mailbox)
    processed_ids = load_processed_ids(PROCESSED_IDS_PATH)

    threading.Thread(target=scheduler.run_forever, daemon=True).start()

    # Start enabled messaging channel adapters
    try:
        from channels.loader import get_enabled_channels
        backend_cfg = AI_BACKENDS[args.ai]
        for ch in get_enabled_channels():
            threading.Thread(target=run_channel_loop, args=(ch, args.ai, backend_cfg), daemon=True).start()
    except Exception as e:
        log.warning(f"Channel 加载失败（不影响邮件功能）: {e}")

    backend = AI_BACKENDS[args.ai]
    use_poll = args.poll or os.environ.get("MODE", "idle").lower() == "poll"
    use_gmail_push = getattr(args, "gmail_push", False) or os.environ.get("MODE", "").lower() == "gmail_push"

    if use_gmail_push:
        log.info(f"🚀 MailMindHub 启动 | 邮箱: {args.mailbox} | AI: {args.ai} | 模式: Gmail Push")
        run_gmail_push(args.mailbox, args.ai, backend)
    elif use_poll:
        log.info(f"🚀 MailMindHub 启动 | 邮箱: {args.mailbox} | AI: {args.ai} | 模式: 轮询")
        run_poll(args.mailbox, args.ai, backend)
    else:
        log.info(f"🚀 MailMindHub 启动 | 邮箱: {args.mailbox} | AI: {args.ai} | 模式: IDLE")
        run_idle(args.mailbox, args.ai, backend)

if __name__ == "__main__":
    main()
