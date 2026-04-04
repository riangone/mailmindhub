import sqlite3
import json
import time
import threading
import logging
import re
import os
from datetime import datetime, timedelta
from typing import Optional
from core.config import MAILBOXES
from core.mail_sender import send_reply, archive_output
from tasks.registry import execute_task_logic
from utils.logger import log

MAX_TASK_RETRIES = int(os.environ.get("TASK_MAX_RETRIES", 3))

class TaskScheduler:
    def __init__(self, db_path="tasks.db"):
        self.db_path = os.path.join(os.path.dirname(__file__), "..", db_path)
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mailbox_name TEXT,
                    "to" TEXT,
                    subject TEXT,
                    body TEXT,
                    trigger_time REAL,
                    interval_seconds INTEGER,
                    until_time REAL,
                    cron_expr TEXT,
                    type TEXT,
                    payload TEXT,
                    output TEXT,
                    attachments TEXT,
                    in_reply_to TEXT,
                    lang TEXT DEFAULT 'zh',
                    status TEXT DEFAULT 'pending'
                )
            """)
            # Migrations for existing databases
            for col, definition in [
                ("cron_expr", "TEXT"),
                ("paused_at", "REAL"),
                ("retry_count", "INTEGER DEFAULT 0"),
                ("lang", "TEXT DEFAULT 'zh'"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {definition}")
                except Exception:
                    pass
            # Indexes for scheduler performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_trigger_status ON tasks (trigger_time, status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_mailbox_status ON tasks (mailbox_name, status)")
            # mail_stats table for dashboard
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mail_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts REAL NOT NULL,
                    mailbox TEXT,
                    status TEXT,
                    ai_ms INTEGER,
                    subject TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stats_ts ON mail_stats (ts)")

    def _parse_datetime(self, value: str):
        if not value: return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None

    def _cron_next(self, cron_expr: str, after: float = None) -> Optional[float]:
        """Calculate next trigger time for a cron expression using croniter."""
        try:
            from croniter import croniter
            base = datetime.fromtimestamp(after or time.time())
            next_dt = croniter(cron_expr, base).get_next(datetime)
            return time.mktime(next_dt.timetuple())
        except Exception as e:
            log.error(f"cron 表达式解析失败 '{cron_expr}': {e}")
            return None

    def record_stat(self, mailbox: str, status: str, ai_ms: int = None, subject: str = None):
        """Record email processing stat for dashboard."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT INTO mail_stats (ts, mailbox, status, ai_ms, subject) VALUES (?,?,?,?,?)",
                    (time.time(), mailbox, status, ai_ms, (subject or "")[:100])
                )
        except Exception as e:
            log.warning(f"[Stats] Failed to record stat: {e}")

    def _parse_duration(self, value: str):
        if not value: return None
        s = value.strip().lower()
        if s.isdigit(): return int(s)
        m = re.fullmatch(r"(\d+)\s*([smhd])", s)
        if not m: return None
        num = int(m.group(1))
        unit = m.group(2)
        return num * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]

    def add_task(
        self,
        mailbox_name,
        to,
        subject,
        body,
        schedule_at: str = None,
        schedule_every: str = None,
        schedule_until: str = None,
        schedule_cron: str = None,
        task_type: str = "email",
        task_payload: Optional[dict] = None,
        output: Optional[dict] = None,
        attachments: Optional[list] = None,
        in_reply_to: str = "",
        lang: str = "zh",
    ):
        try:
            interval = self._parse_duration(schedule_every)
            until_ts = self._parse_datetime(schedule_until)
            cron_expr = schedule_cron or None

            if cron_expr:
                trigger_time = self._cron_next(cron_expr)
            elif schedule_at:
                if isinstance(schedule_at, str) and schedule_at.isdigit():
                    trigger_time = time.time() + int(schedule_at)
                else:
                    trigger_time = self._parse_datetime(schedule_at)
            else:
                trigger_time = time.time()

            if trigger_time is None:
                raise ValueError("schedule_at/schedule_cron 无法解析")

            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO tasks (mailbox_name, "to", subject, body, trigger_time, interval_seconds, until_time, cron_expr, type, payload, output, attachments, in_reply_to, lang)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    mailbox_name, to, subject, body, trigger_time, interval, until_ts, cron_expr,
                    task_type or "email", json.dumps(task_payload or {}),
                    json.dumps(output or {}), json.dumps(attachments or []), in_reply_to, lang
                ))
            log.info(f"📅 任务已存入数据库：[{subject}] 将在 {datetime.fromtimestamp(trigger_time)} 发送")
            return True
        except Exception as e:
            log.error(f"安排任务失败: {e}")
            return False

    # ── Task management ──────────────────────────────────────────

    def list_tasks(self, status_filter: str = None, type_filter: str = None,
                   subject_filter: str = None, mailbox_filter: str = None) -> list:
        """Return task rows matching optional filters."""
        sql = 'SELECT * FROM tasks WHERE 1=1'
        params = []
        if status_filter:
            sql += ' AND status = ?'
            params.append(status_filter)
        else:
            sql += " AND status NOT IN ('completed', 'failed')"
        if type_filter:
            sql += ' AND type = ?'
            params.append(type_filter)
        if subject_filter:
            sql += ' AND subject LIKE ?'
            params.append(f'%{subject_filter}%')
        if mailbox_filter:
            sql += ' AND mailbox_name = ?'
            params.append(mailbox_filter)
        sql += ' ORDER BY trigger_time ASC'
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def cancel_task(self, task_id: int) -> bool:
        """Set status to 'cancelled'. Returns True if a row was updated."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE tasks SET status='cancelled' WHERE id=? AND status NOT IN ('completed','failed','cancelled')",
                (task_id,))
            return cur.rowcount > 0

    def pause_task(self, task_id: int) -> bool:
        """Set status to 'paused'. Returns True if a row was updated."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE tasks SET status='paused', paused_at=? WHERE id=? AND status='pending'",
                (time.time(), task_id))
            return cur.rowcount > 0

    def resume_task(self, task_id: int) -> bool:
        """Restore a paused task to 'pending'. Returns True if updated."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(
                "UPDATE tasks SET status='pending', paused_at=NULL WHERE id=? AND status='paused'",
                (task_id,))
            return cur.rowcount > 0

    def restart_task(self, task_id: int) -> bool:
        """Re-enable a cancelled, failed or completed task.
        Recalculates trigger_time if it's a recurring task.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                return False
            t = dict(row)
            
            now = time.time()
            cron_expr = t.get("cron_expr")
            interval = t.get("interval_seconds")
            
            new_trigger = now
            if cron_expr:
                new_trigger = self._cron_next(cron_expr, after=now) or now
            elif interval:
                # For interval tasks, we can either run now or wait one interval.
                # Running now seems more intuitive for a manual "restart".
                new_trigger = now

            cur = conn.execute(
                "UPDATE tasks SET status='pending', trigger_time=?, retry_count=0 WHERE id=?",
                (new_trigger, task_id)
            )
            return cur.rowcount > 0

    def delete_task(self, task_id: int) -> bool:
        """Permanently remove a task. Returns True if deleted."""
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            return cur.rowcount > 0

    def cancel_tasks_by_filter(self, type_filter: str = None, subject_filter: str = None,
                                mailbox_filter: str = None) -> int:
        """Cancel all matching active tasks. Returns count of cancelled rows."""
        sql = "UPDATE tasks SET status='cancelled' WHERE status NOT IN ('completed','failed','cancelled')"
        params = []
        if type_filter:
            sql += ' AND type=?'
            params.append(type_filter)
        if subject_filter:
            sql += ' AND subject LIKE ?'
            params.append(f'%{subject_filter}%')
        if mailbox_filter:
            sql += ' AND mailbox_name=?'
            params.append(mailbox_filter)
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(sql, params)
            return cur.rowcount

    def run_forever(self):
        log.info("⏰ 任务调度器已启动 (SQLite)")
        while True:
            now = time.time()
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute("SELECT * FROM tasks WHERE trigger_time <= ? AND status = 'pending'", (now,))
                    due_tasks = cursor.fetchall()
                    
                    for t in due_tasks:
                        task_dict = dict(t)
                        # Mark as processing to avoid double execution
                        conn.execute("UPDATE tasks SET status = 'processing' WHERE id = ?", (task_dict['id'],))
                        conn.commit()

                        try:
                            self._execute_single_task(task_dict)

                            cron_expr = task_dict.get("cron_expr")
                            interval = task_dict.get("interval_seconds")
                            until_time = task_dict.get("until_time")

                            if cron_expr:
                                next_time = self._cron_next(cron_expr, after=time.time())
                                if next_time and (not until_time or next_time <= until_time):
                                    conn.execute("UPDATE tasks SET trigger_time = ?, status = 'pending' WHERE id = ?", (next_time, task_dict['id']))
                                else:
                                    conn.execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_dict['id'],))
                            elif interval:
                                next_time = time.time() + interval
                                if not until_time or next_time <= until_time:
                                    conn.execute("UPDATE tasks SET trigger_time = ?, status = 'pending' WHERE id = ?", (next_time, task_dict['id']))
                                else:
                                    conn.execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_dict['id'],))
                            else:
                                conn.execute("UPDATE tasks SET status = 'completed' WHERE id = ?", (task_dict['id'],))
                        except Exception as e:
                            retry_count = (task_dict.get("retry_count") or 0) + 1
                            if retry_count <= MAX_TASK_RETRIES:
                                backoff = min(60 * (2 ** (retry_count - 1)), 3600)
                                next_retry = time.time() + backoff
                                log.warning(f"任务 {task_dict['id']} 出错，{backoff}秒后重试 ({retry_count}/{MAX_TASK_RETRIES}): {e}")
                                conn.execute(
                                    "UPDATE tasks SET status='pending', trigger_time=?, retry_count=? WHERE id=?",
                                    (next_retry, retry_count, task_dict['id'])
                                )
                            else:
                                log.error(f"任务 {task_dict['id']} 已达最大重试次数 ({MAX_TASK_RETRIES})，标记为失败: {e}")
                                conn.execute("UPDATE tasks SET status = 'failed' WHERE id = ?", (task_dict['id'],))
                        conn.commit()
            except Exception as e:
                log.error(f"调度器主循环出错: {e}")
            time.sleep(10)

    def _execute_single_task(self, t: dict):
        log.info(f"🔔 执行任务：[{t['subject']}] -> {t['to']}")
        lang = t.get("lang", "zh")

        # 進捗コールバック：CLI AI 実行中に AI_PROGRESS_INTERVAL 秒ごとに中間メール送信
        def _progress_cb(elapsed_s: int):
            try:
                from core.config import AI_PROGRESS_INTERVAL
                if not AI_PROGRESS_INTERVAL:
                    return
                mins, secs = divmod(elapsed_s, 60)
                msg = {
                    "zh": f"⏳ 定时任务处理中……已用时 {mins} 分 {secs} 秒\n\n任务：{t['subject']}",
                    "ja": f"⏳ 定期タスク実行中……経過時間 {mins} 分 {secs} 秒\n\nタスク：{t['subject']}",
                    "en": f"⏳ Scheduled task running…… elapsed {mins}m {secs}s\n\nTask: {t['subject']}",
                    "ko": f"⏳ 예약 작업 실행 중…… 경과 시간 {mins}분 {secs}초\n\n작업: {t['subject']}",
                }.get(lang, f"⏳ 定时任务处理中……已用时 {mins} 分 {secs} 秒")
                send_reply(
                    MAILBOXES[t["mailbox_name"]],
                    t["to"],
                    t["subject"],
                    msg,
                    in_reply_to=t.get("in_reply_to", ""),
                    lang=lang,
                )
            except Exception as e:
                log.warning(f"进度邮件发送失败 (task {t['id']}): {e}")

        # Prepare task dict for registry
        task_for_logic = {
            "type": t["type"],
            "payload": json.loads(t["payload"]),
            "subject": t["subject"],
            "body": t["body"],
        }

        subject, body = execute_task_logic(task_for_logic, lang=lang, progress_cb=_progress_cb)

        output = json.loads(t["output"])
        attachments = json.loads(t["attachments"])

        # Build RFC 8058 one-click unsubscribe headers for recurring tasks
        extra_headers: dict = {}
        is_recurring = bool(t.get("interval_seconds") or t.get("cron_expr"))
        if is_recurring:
            try:
                from core.one_click_unsubscribe import list_unsubscribe_headers
                extra_headers = list_unsubscribe_headers(t["id"], t["to"])
            except Exception as e:
                log.warning(f"构建 List-Unsubscribe 头失败 (task {t['id']}): {e}")

        if output.get("email", True):
            send_reply(
                MAILBOXES[t["mailbox_name"]],
                t["to"],
                subject,
                body,
                in_reply_to=t.get("in_reply_to", ""),
                attachments=attachments,
                extra_headers=extra_headers if extra_headers else None,
                lang=lang,
            )

        if output.get("archive", False):
            archive_output(output, subject, body, attachments)

    def run_task_now(self, task_id: int):
        """Immediately execute a task in a background thread.
        Marks it 'processing' right away (prevents double execution by the scheduler),
        then updates status / next trigger_time after the task finishes.
        Works for any status (pending, paused, failed, completed).
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row:
                raise ValueError(f"Task #{task_id} not found")
            task = dict(row)
            conn.execute("UPDATE tasks SET status='processing' WHERE id=?", (task_id,))

        def _run():
            try:
                self._execute_single_task(task)
                with sqlite3.connect(self.db_path) as conn:
                    cron_expr = task.get("cron_expr")
                    interval = task.get("interval_seconds")
                    until_time = task.get("until_time")
                    if cron_expr:
                        next_time = self._cron_next(cron_expr, after=time.time())
                        if next_time and (not until_time or next_time <= until_time):
                            conn.execute("UPDATE tasks SET trigger_time=?, status='pending' WHERE id=?", (next_time, task_id))
                        else:
                            conn.execute("UPDATE tasks SET status='completed' WHERE id=?", (task_id,))
                    elif interval:
                        next_time = time.time() + interval
                        if not until_time or next_time <= until_time:
                            conn.execute("UPDATE tasks SET trigger_time=?, status='pending' WHERE id=?", (next_time, task_id))
                        else:
                            conn.execute("UPDATE tasks SET status='completed' WHERE id=?", (task_id,))
                    else:
                        conn.execute("UPDATE tasks SET status='completed' WHERE id=?", (task_id,))
            except Exception as e:
                log.error(f"手動実行タスク #{task_id} 失敗: {e}")
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("UPDATE tasks SET status='failed' WHERE id=?", (task_id,))

        threading.Thread(target=_run, daemon=True, name=f"webui-task-{task_id}").start()


# Singleton instance
scheduler = TaskScheduler()
