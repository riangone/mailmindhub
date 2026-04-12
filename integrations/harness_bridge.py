"""
integrations/harness_bridge.py — MailMind ↔ Harness 桥接 (HTTP API 版)

架构：
  用户 → 邮件 → MailMind → POST harness API → harness 异步执行 → Webhook 回调 → MailMind 回复邮件

harness API 端点：
  POST {base}/api/v1/tasks/from-email  从邮件创建任务
  POST {base}/api/v1/tasks             直接创建任务
  GET  {base}/api/v1/tasks/{id}        查询任务状态
"""

import os
import json
import time
import threading
from typing import Optional, Dict, Any, Callable

import requests
from utils.logger import log


# ============================================
# 配置
# ============================================
HARNESS_API_BASE = os.environ.get("HARNESS_API_BASE", "http://localhost:7500")
HARNESS_API_TOKEN = os.environ.get("HARNESS_API_TOKEN", "")
HARNESS_POLL_TIMEOUT = int(os.environ.get("HARNESS_POLL_TIMEOUT", "300"))  # 轮询超时（秒）
HARNESS_POLL_INTERVAL = int(os.environ.get("HARNESS_POLL_INTERVAL", "10"))  # 轮询间隔（秒）


def _headers() -> Dict[str, str]:
    """构建请求头"""
    h = {"Content-Type": "application/json"}
    if HARNESS_API_TOKEN:
        h["X-API-Key"] = HARNESS_API_TOKEN
    return h


def _health_check() -> bool:
    """检查 harness API 是否可达"""
    try:
        resp = requests.get(f"{HARNESS_API_BASE}/api/v1/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


# ============================================
# 异步任务 + 轮询（无需 Webhook 回调）
# ============================================
def run_harness_pipeline(
    prompt: str,
    work_dir: Optional[str] = None,
    pipeline_mode: str = "full",
    project_name: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Dict[str, Any]:
    """
    调用 Harness 多 AI 管道（异步 + 轮询模式）

    流程：
      1. POST /api/v1/tasks 创建任务 → 获 task_id
      2. 轮询 GET /api/v1/tasks/{id} 等待完成
      3. 返回最终结果

    参数:
        prompt: 任务描述（自然语言）
        work_dir: 工作目录（可选）
        pipeline_mode: "full" (planner→generator→evaluator) 或 "single" (单 AI)
        project_name: 项目名称（可选）
        timeout: 超时秒数（可选，默认 300）

    返回:
        {"status": "completed"|"failed", "output": "结果文本", "work_dir": "路径"}
    """
    if not _health_check():
        log.error(f"[Harness] ✗ Harness API 不可达: {HARNESS_API_BASE}")
        return {
            "status": "failed",
            "output": f"⚠️ Harness API 不可达 ({HARNESS_API_BASE})。\n请确认 harness 服务已启动。",
            "work_dir": work_dir or "",
        }

    effective_timeout = timeout or HARNESS_POLL_TIMEOUT
    log.info(f"[Harness] 🚀 创建任务: prompt={prompt[:60]}... pipeline_mode={pipeline_mode}")

    try:
        # 1. 创建任务
        payload = {
            "title": prompt[:80],
            "prompt": prompt,
            "success_criteria": "",
            "pipeline_mode": pipeline_mode == "full",
        }
        if work_dir:
            payload["metadata"] = {"work_dir": work_dir}
        if project_name:
            payload["metadata"] = payload.get("metadata", {})
            payload["metadata"]["project_name"] = project_name

        resp = requests.post(
            f"{HARNESS_API_BASE}/api/v1/tasks",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        create_result = resp.json()
        task_id = create_result["task_id"]
        log.info(f"[Harness] ✓ 任务已创建: task_id={task_id}")

        # 2. 轮询等待完成
        start_time = time.time()
        while time.time() - start_time < effective_timeout:
            time.sleep(HARNESS_POLL_INTERVAL)

            status_resp = requests.get(
                f"{HARNESS_API_BASE}/api/v1/tasks/{task_id}",
                headers=_headers(),
                timeout=10,
            )
            status_resp.raise_for_status()
            task = status_resp.json()

            status = task.get("status", "running")
            log.info(f"[Harness] ⏳ task_id={task_id} status={status}")

            if status in ("completed", "failed"):
                break
        else:
            # 超时
            log.error(f"[Harness] ✗ 任务超时: task_id={task_id}")
            return {
                "status": "failed",
                "output": f"⚠️ Harness 任务执行超时（{effective_timeout} 秒）。\ntask_id={task_id}\n可通过 harness WebUI 或 API 继续查询状态。",
                "work_dir": work_dir or "",
            }

        # 3. 构建返回结果
        if task.get("status") == "completed":
            output = task.get("result", "") or ""
            # 附加 run 日志摘要
            if task.get("runs"):
                run_summary = "\n\n--- 执行步骤 ---\n"
                for r in task["runs"]:
                    icon = "✅" if r.get("status") == "completed" else "❌"
                    run_summary += f"{icon} {r.get('phase', '?')} ({r.get('agent', '?')})\n"
                output += run_summary

            log.info(f"[Harness] ✓ 任务完成: task_id={task_id}")
            return {
                "status": "completed",
                "output": output,
                "work_dir": work_dir or "",
            }
        else:
            # failed
            error_detail = task.get("result", "未知错误")
            # 从 run 日志中提取更详细的错误
            if task.get("runs"):
                for r in task["runs"]:
                    if r.get("status") == "failed" and r.get("result"):
                        error_detail = r["result"]
                        break

            log.error(f"[Harness] ✗ 任务失败: task_id={task_id}, error={error_detail[:200]}")
            return {
                "status": "failed",
                "output": f"❌ Harness 任务执行失败:\n\n{error_detail[:2000]}",
                "work_dir": work_dir or "",
            }

    except requests.RequestException as e:
        log.error(f"[Harness] ✗ HTTP 请求异常: {e}")
        return {
            "status": "failed",
            "output": f"⚠️ Harness API 请求失败:\n{str(e)}",
            "work_dir": work_dir or "",
        }
    except Exception as e:
        log.error(f"[Harness] ✗ 桥接异常: {e}")
        return {
            "status": "failed",
            "output": f"⚠️ Harness 桥接错误:\n{str(e)}",
            "work_dir": work_dir or "",
        }


# ============================================
# 邮件模式（from-email 端点 + Webhook 回调）
# ============================================
def run_from_email_with_callback(
    subject: str,
    body: str,
    from_addr: str,
    callback_url: Optional[str] = None,
    original_message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    从邮件创建任务（支持 Webhook 回调）

    流程：
      1. POST /api/v1/tasks/from-email → 获 task_id
      2. harness 异步执行 → 完成后 POST 回调到 callback_url
      3. MailMind 收到回调 → 回复邮件给用户

    参数:
        subject: 邮件主题
        body: 邮件正文
        from_addr: 发件人地址
        callback_url: Webhook 回调 URL（可选，默认不回调，使用轮询）
        original_message_id: 原始邮件的 Message-ID（用于回复时设置 In-Reply-To）

    返回:
        {"status": "pending"|"unknown_command", "task_id": int, "message": str}
    """
    if not _health_check():
        log.error(f"[Harness] ✗ Harness API 不可达: {HARNESS_API_BASE}")
        return {
            "status": "failed",
            "message": f"⚠️ Harness API 不可达 ({HARNESS_API_BASE})。",
        }

    log.info(f"[Harness] 📧 邮件任务: from={from_addr}, subject={subject[:60]}")

    try:
        payload = {
            "subject": subject,
            "body": body,
            "from_addr": from_addr,
        }
        if callback_url:
            payload["callback_url"] = callback_url
        if original_message_id:
            payload["original_message_id"] = original_message_id

        resp = requests.post(
            f"{HARNESS_API_BASE}/api/v1/tasks/from-email",
            headers=_headers(),
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()

        task_id = result.get("task_id")
        status = result.get("status", "")

        if task_id:
            log.info(f"[Harness] ✓ 邮件任务已创建: task_id={task_id}, status={status}")
        else:
            log.info(f"[Harness] ⚠️ 邮件任务: {result.get('message', '')}")

        return result

    except requests.RequestException as e:
        log.error(f"[Harness] ✗ HTTP 请求异常: {e}")
        return {
            "status": "failed",
            "message": f"⚠️ Harness API 请求失败:\n{str(e)}",
        }
    except Exception as e:
        log.error(f"[Harness] ✗ 桥接异常: {e}")
        return {
            "status": "failed",
            "message": f"⚠️ Harness 桥接错误:\n{str(e)}",
        }


# ============================================
# 工具函数
# ============================================
def get_task_status(task_id: int) -> Optional[Dict[str, Any]]:
    """查询任务状态"""
    try:
        resp = requests.get(
            f"{HARNESS_API_BASE}/api/v1/tasks/{task_id}",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.error(f"[Harness] 查询任务状态失败: {e}")
        return None


def list_agents() -> list:
    """获取可用 Agent 列表（用于邮件帮助回复）"""
    try:
        resp = requests.get(
            f"{HARNESS_API_BASE}/api/v1/agents",
            headers=_headers(),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("agents", [])
    except Exception:
        return []
