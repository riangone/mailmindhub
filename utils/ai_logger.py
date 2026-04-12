"""
utils/ai_logger.py - AI 消息日志数据库

将 AI 的原始响应、解析结果、任务执行详情记录到独立的 SQLite 数据库，
供 Web UI 查询和展示。
"""
import os
import sqlite3
import json
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from utils.logger import log

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "ai_messages.db")
DB_PATH = os.path.abspath(DB_PATH)


def init_db():
    """初始化数据库表结构"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                datetime TEXT NOT NULL,

                -- 邮件上下文
                mailbox_name TEXT,
                from_email TEXT,
                email_subject TEXT,
                email_id TEXT,

                -- AI 调用信息
                ai_name TEXT NOT NULL,
                ai_type TEXT,                          -- cli / api_openai / api_anthropic / ...
                model TEXT,                            -- 使用的模型名称

                -- Prompt 信息
                prompt_preview TEXT,                   -- prompt 前 200 字
                prompt_length INTEGER,

                -- 原始响应
                raw_response TEXT,                     -- 完整原始响应
                raw_response_length INTEGER,

                -- 解析结果
                parse_success INTEGER NOT NULL DEFAULT 0,
                parse_error TEXT,                      -- 解析失败时的错误信息

                -- 提取的字段
                task_type TEXT,
                subject TEXT,
                body_preview TEXT,                     -- body 前 500 字
                body_length INTEGER,
                schedule_at TEXT,
                schedule_every TEXT,
                schedule_cron TEXT,
                schedule_until TEXT,
                task_payload_json TEXT,                -- JSON 序列化
                output_json TEXT,                      -- JSON 序列化
                attachments_count INTEGER DEFAULT 0,

                -- 任务执行结果（如果是即时任务）
                task_executed INTEGER NOT NULL DEFAULT 0,
                task_result_subject TEXT,
                task_result_body_preview TEXT,         -- 结果 body 前 500 字
                task_result_length INTEGER,
                task_error TEXT,

                -- 耗时
                ai_call_ms INTEGER,
                task_exec_ms INTEGER,

                -- 语言
                lang TEXT DEFAULT 'zh'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_messages_timestamp ON ai_messages(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_messages_from_email ON ai_messages(from_email)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_messages_task_type ON ai_messages(task_type)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_messages_ai_name ON ai_messages(ai_name)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_messages_parse_success ON ai_messages(parse_success)")
        log.info(f"[AILogger] 数据库已初始化: {DB_PATH}")


def log_ai_message(
    # 必填
    ai_name: str,
    raw_response: str,
    parse_success: bool,
    # 邮件上下文
    mailbox_name: str = "",
    from_email: str = "",
    email_subject: str = "",
    email_id: str = "",
    # AI 信息
    ai_type: str = "",
    model: str = "",
    prompt: str = "",
    # 解析结果
    parse_error: str = "",
    task_type: str = "",
    subject: str = "",
    body: str = "",
    schedule_at: str = "",
    schedule_every: str = "",
    schedule_cron: str = "",
    schedule_until: str = "",
    task_payload: dict = None,
    output: dict = None,
    attachments: list = None,
    # 任务执行结果
    task_executed: bool = False,
    task_result_subject: str = "",
    task_result_body: str = "",
    task_error: str = "",
    # 耗时
    ai_call_ms: int = 0,
    task_exec_ms: int = 0,
    # 语言
    lang: str = "zh",
) -> int:
    """
    记录一次 AI 消息到数据库。

    Returns:
        插入的行 ID
    """
    now = time.time()
    dt = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")

    task_payload_json = json.dumps(task_payload, ensure_ascii=False) if task_payload else None
    output_json = json.dumps(output, ensure_ascii=False) if output else None

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            INSERT INTO ai_messages (
                timestamp, datetime,
                mailbox_name, from_email, email_subject, email_id,
                ai_name, ai_type, model,
                prompt_preview, prompt_length,
                raw_response, raw_response_length,
                parse_success, parse_error,
                task_type, subject, body_preview, body_length,
                schedule_at, schedule_every, schedule_cron, schedule_until,
                task_payload_json, output_json, attachments_count,
                task_executed, task_result_subject, task_result_body_preview, task_result_length, task_error,
                ai_call_ms, task_exec_ms,
                lang
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            now, dt,
            mailbox_name, from_email, email_subject, email_id,
            ai_name, ai_type, model,
            prompt[:200] if prompt else "", len(prompt) if prompt else 0,
            raw_response, len(raw_response) if raw_response else 0,
            1 if parse_success else 0, parse_error,
            task_type, subject, body[:500] if body else "", len(body) if body else 0,
            schedule_at or None, schedule_every or None, schedule_cron or None, schedule_until or None,
            task_payload_json, output_json, len(attachments) if attachments else 0,
            1 if task_executed else 0, task_result_subject, task_result_body[:500] if task_result_body else "",
            len(task_result_body) if task_result_body else 0, task_error,
            ai_call_ms, task_exec_ms,
            lang,
        ))
        row_id = cursor.lastrowid

    if parse_success:
        log.info(f"[AILogger] ✅ 已记录 AI 消息 #{row_id}: ai={ai_name}, task_type={task_type!r}, email={email_subject!r}")
    else:
        log.warning(f"[AILogger] ❌ 已记录 AI 消息(失败) #{row_id}: ai={ai_name}, error={parse_error!r}")

    return row_id


def query_ai_messages(
    limit: int = 50,
    offset: int = 0,
    from_email: str = "",
    task_type: str = "",
    ai_name: str = "",
    parse_success: Optional[bool] = None,
    keyword: str = "",
    start_time: float = 0,
    end_time: float = 0,
    mailbox_name: str = "",
) -> List[Dict[str, Any]]:
    """
    查询 AI 消息记录。

    Returns:
        字典列表，每条包含所有字段
    """
    sql = "SELECT * FROM ai_messages WHERE 1=1"
    params = []

    if from_email:
        sql += " AND from_email LIKE ?"
        params.append(f"%{from_email}%")
    if task_type:
        sql += " AND task_type = ?"
        params.append(task_type)
    if ai_name:
        sql += " AND ai_name = ?"
        params.append(ai_name)
    if parse_success is not None:
        sql += " AND parse_success = ?"
        params.append(1 if parse_success else 0)
    if keyword:
        sql += " AND (email_subject LIKE ? OR subject LIKE ? OR raw_response LIKE ? OR parse_error LIKE ?)"
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw, kw])
    if start_time > 0:
        sql += " AND timestamp >= ?"
        params.append(start_time)
    if end_time > 0:
        sql += " AND timestamp <= ?"
        params.append(end_time)
    if mailbox_name:
        sql += " AND mailbox_name = ?"
        params.append(mailbox_name)

    sql += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql, params)
        rows = cursor.fetchall()

    return [dict(r) for r in rows]


def get_ai_message_detail(msg_id: int) -> Optional[Dict[str, Any]]:
    """获取单条 AI 消息的完整详情（包含完整 raw_response）"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM ai_messages WHERE id = ?", (msg_id,))
        row = cursor.fetchone()
    return dict(row) if row else None


def get_ai_stats() -> Dict[str, Any]:
    """获取 AI 消息统计信息"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN parse_success = 1 THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN parse_success = 0 THEN 1 ELSE 0 END) as fail_count,
                SUM(CASE WHEN task_executed = 1 THEN 1 ELSE 0 END) as executed_count,
                AVG(ai_call_ms) as avg_ai_call_ms,
                AVG(task_exec_ms) as avg_task_exec_ms
            FROM ai_messages
        """)
        row = cursor.fetchone()

        # 按 AI 名称统计
        cursor2 = conn.execute("""
            SELECT ai_name, COUNT(*) as count,
                   SUM(CASE WHEN parse_success = 1 THEN 1 ELSE 0 END) as success
            FROM ai_messages
            GROUP BY ai_name
            ORDER BY count DESC
        """)
        by_ai = [{"ai_name": r[0], "count": r[1], "success": r[2]} for r in cursor2.fetchall()]

        # 按 task_type 统计
        cursor3 = conn.execute("""
            SELECT task_type, COUNT(*) as count
            FROM ai_messages
            WHERE task_type IS NOT NULL AND task_type != ''
            GROUP BY task_type
            ORDER BY count DESC
        """)
        by_type = [{"task_type": r[0], "count": r[1]} for r in cursor3.fetchall()]

    return {
        "total": row[0] or 0,
        "success_count": row[1] or 0,
        "fail_count": row[2] or 0,
        "executed_count": row[3] or 0,
        "avg_ai_call_ms": round(row[4] or 0, 0),
        "avg_task_exec_ms": round(row[5] or 0, 0),
        "by_ai": by_ai,
        "by_type": by_type,
    }


def delete_old_messages(before_timestamp: float) -> int:
    """清理指定时间戳之前的旧消息"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("DELETE FROM ai_messages WHERE timestamp < ?", (before_timestamp,))
        conn.commit()
        deleted = cursor.rowcount
    if deleted > 0:
        log.info(f"[AILogger] 已清理 {deleted} 条旧 AI 消息 (before {datetime.fromtimestamp(before_timestamp)})")
    return deleted


# 初始化数据库
init_db()
