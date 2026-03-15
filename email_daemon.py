#!/usr/bin/env python3
"""
MailMind — 邮件 → AI 守护进程 (模块化重构版)
"""

import os
import sys
import time
import json
import argparse
import threading
from typing import Optional

# 核心配置与模块
from core.config import MAILBOXES, AI_BACKENDS, POLL_INTERVAL, DEFAULT_TASK_AI, PROMPT_TEMPLATE
from core.validator import validate_config
from core.mail_client import fetch_unread_emails, imap_login, get_oauth_token, fetch_message_content_by_id
from core.mail_sender import send_reply, archive_output
from ai.providers import get_ai_provider
from utils.parser import parse_ai_response, auto_detect_tasks
from utils.logger import log
from tasks.scheduler import scheduler
from tasks.registry import execute_task_logic
from concurrent.futures import ThreadPoolExecutor

# 初始化线程池
executor = ThreadPoolExecutor(max_workers=5)

# 已处理 ID 路径
PROCESSED_IDS_PATH: Optional[str] = None
processed_ids: set = set()

def _default_processed_ids_path(mailbox_name: str) -> str:
    return os.path.join(os.path.dirname(__file__), f"processed_ids_{mailbox_name}.json")

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
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(sorted(ids), f, indent=2)
        os.replace(path + ".tmp", path)
    except Exception as e:
        log.warning(f"保存 processed_ids 失败：{e}")

# ────────────────────────────────────────────────────────────────

def call_ai(ai_name: str, backend: dict, instruction: str):
    prompt = PROMPT_TEMPLATE.format(instruction=instruction)
    ai = get_ai_provider(ai_name, backend)
    raw = ai.call(prompt)
    return parse_ai_response(raw)

def process_email(mailbox_name, ai_name, backend, em):
    log.info(f"📨 收到指令: [{em['subject']}] 来自 {em['from_email']}")
    
    # 尝试获取会话上下文
    context_msg = ""
    if em.get("in_reply_to"):
        log.info(f"🔍 检测到回复，正在获取上下文: {em['in_reply_to']}")
        context_msg = fetch_message_content_by_id(MAILBOXES[mailbox_name], em["in_reply_to"])
    
    instr = f"发件人：{em['from']}\n主题：{em['subject']}\n\n"
    if context_msg:
        instr += f"--- 上下文（上一封邮件内容） ---\n{context_msg}\n\n--- 当前邮件内容 ---\n"
    
    instr += em['body']
    for att in em.get("attachments", []):
        if att["is_text"]: instr += f"\n\n--- 附件：{att['filename']} ---\n{att['content']}"
    
    sub, body, sch_at, sch_every, sch_until, atts, task_type, task_payload, output = call_ai(ai_name, backend, instr)
    
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
            in_reply_to=em.get("message_id", "")
        )
        if sch_every:
            msg = f"您的任务将每 {sch_every} 发送一次，截止至 {sch_until or '未指定'}。\n\n内容预览：\n{body}"
            send_reply(MAILBOXES[mailbox_name], em["from_email"], f"已安排定时任务：{sub}", msg)
        else:
            msg = f"您的任务已安排在 {sch_at} 左右执行。\n\n内容预览：\n{body}"
            send_reply(MAILBOXES[mailbox_name], em["from_email"], f"已安排定时任务：{sub}", msg)
    elif task_type and task_type != "email":
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
            with imapclient.IMAPClient(mailbox["imap_server"], ssl=True) as client:
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
    args = parser.parse_args()

    if args.list:
        for name, mb in MAILBOXES.items():
            print(f"  {name:10s} {mb.get('address', '(未配置)')}")
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
    log.info(f"🚀 MailMind 启动 | 邮箱: {args.mailbox} | AI: {args.ai} | 模式: {'轮询' if use_poll else 'IDLE'}")
    
    backend = AI_BACKENDS[args.ai]
    if use_poll:
        run_poll(args.mailbox, args.ai, backend)
    else:
        run_idle(args.mailbox, args.ai, backend)

if __name__ == "__main__":
    main()
