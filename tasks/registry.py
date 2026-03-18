import os
import shutil
import time
import subprocess
import requests
from typing import Optional
from core.config import WEATHER_API_KEY, WEATHER_DEFAULT_LOCATION, AI_BACKENDS, DEFAULT_TASK_AI, PROMPT_LANG
from ai.providers import get_ai_provider
from utils.logger import log


def fetch_weather_data(location: str) -> Optional[str]:
    """WeatherAPI.com で天気を取得し、整形テキストを返す。失敗時は None。"""
    if not WEATHER_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.weatherapi.com/v1/current.json",
            params={"key": WEATHER_API_KEY, "q": location, "lang": "zh"},
            timeout=10,
        )
        resp.raise_for_status()
        d = resp.json()
        loc = d["location"]
        cur = d["current"]
        return (
            f"地点：{loc['name']}，{loc['country']}\n"
            f"时间：{loc['localtime']}\n"
            f"天气：{cur['condition']['text']}\n"
            f"温度：{cur['temp_c']}°C（体感 {cur['feelslike_c']}°C）\n"
            f"湿度：{cur['humidity']}%\n"
            f"风速：{cur['wind_kph']} km/h {cur['wind_dir']}\n"
            f"能见度：{cur['vis_km']} km"
        )
    except Exception as e:
        log.warning(f"WeatherAPI 查询失败：{e}")
        return None

def _read_meminfo_kb() -> dict:
    info = {}
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if ":" not in line: continue
                key, rest = line.split(":", 1)
                val = rest.strip().split()[0]
                if val.isdigit(): info[key] = int(val)
    except Exception: pass
    return info

def _read_cpu_times() -> tuple[float, float]:
    try:
        with open("/proc/stat", "r", encoding="utf-8") as f:
            parts = f.readline().strip().split()
            if parts and parts[0] == "cpu":
                nums = [float(x) for x in parts[1:]]
                total = sum(nums)
                idle = nums[3] + (nums[4] if len(nums) > 4 else 0.0)
                return total, idle
    except Exception: pass
    return 0.0, 0.0

def fetch_system_status(payload: Optional[dict] = None) -> str:
    payload = payload or {}
    lines = ["# 🖥️ 系统运行状态", ""]
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as f:
            uptime_seconds = float(f.read().split()[0])
        uptime_h = int(uptime_seconds // 3600)
        uptime_m = int((uptime_seconds % 3600) // 60)
        load1, load5, load15 = os.getloadavg()
        lines.append(f"- 运行时间：{uptime_h}h {uptime_m}m")
        lines.append(f"- Load Average：{load1:.2f} / {load5:.2f} / {load15:.2f}")
    except Exception as e:
        lines.append(f"- 运行时间/负载：⚠️ 无法获取 ({e})")

    try:
        t1, i1 = _read_cpu_times()
        time.sleep(0.1)
        t2, i2 = _read_cpu_times()
        cpu_usage = 0.0
        if t2 > t1: cpu_usage = (1.0 - (i2 - i1) / (t2 - t1)) * 100.0
        lines.append(f"- CPU 使用率：{cpu_usage:.1f}%")
    except Exception as e:
        lines.append(f"- CPU 使用率：⚠️ 无法获取 ({e})")

    mem = _read_meminfo_kb()
    if mem:
        mem_total = mem.get("MemTotal", 0) / 1024
        mem_avail = mem.get("MemAvailable", 0) / 1024
        mem_used = max(mem_total - mem_avail, 0)
        swap_total = mem.get("SwapTotal", 0) / 1024
        swap_free = mem.get("SwapFree", 0) / 1024
        swap_used = max(swap_total - swap_free, 0)
        lines.append(f"- 内存：{mem_used:.0f}MB / {mem_total:.0f}MB（可用 {mem_avail:.0f}MB）")
        if swap_total > 0: lines.append(f"- Swap：{swap_used:.0f}MB / {swap_total:.0f}MB")
    else:
        lines.append("- 内存：⚠️ 无法获取")

    try:
        du = shutil.disk_usage("/")
        total_gb = du.total / (1024 ** 3)
        used_gb = du.used / (1024 ** 3)
        free_gb = du.free / (1024 ** 3)
        lines.append(f"- 磁盘 /：{used_gb:.1f}GB / {total_gb:.1f}GB（剩余 {free_gb:.1f}GB）")
    except Exception as e:
        lines.append(f"- 磁盘：⚠️ 无法获取 ({e})")

    if payload.get("include_processes", True):
        try:
            proc = subprocess.run(["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%cpu"], capture_output=True, text=True, timeout=5)
            rows = [r for r in proc.stdout.strip().splitlines() if r.strip()]
            top = rows[1:6] if len(rows) > 1 else []
            if top:
                lines.append("")
                lines.append("## Top 进程（CPU）")
                for r in top: lines.append(f"- {r}")
        except Exception as e:
            lines.append(f"- 进程：⚠️ 无法获取 ({e})")
    return "\n".join(lines).strip()

def pick_task_ai(task_payload: dict):
    # 如果 payload 没指定，且没有全局默认配置，则尝试使用常见后端或列表第一个
    ai_name = (task_payload or {}).get("ai_name") or DEFAULT_TASK_AI
    if not ai_name or ai_name not in AI_BACKENDS:
        # 动态从 AI_BACKENDS 中选择可用的后端（CLI 优先，然后 API）
        cli_candidates = []
        api_candidates = []
        for name, b in AI_BACKENDS.items():
            if b.get("type") == "cli":
                cmd = b.get("cmd", "")
                if cmd and (shutil.which(cmd) or os.path.isfile(cmd)):
                    cli_candidates.append(name)
            elif b.get("api_key"):
                api_candidates.append(name)
        candidates = cli_candidates + api_candidates
        ai_name = candidates[0] if candidates else list(AI_BACKENDS.keys())[0]

    backend = AI_BACKENDS.get(ai_name)
    return ai_name, backend

def _t(zh: str, ja: str, en: str) -> str:
    return {"zh": zh, "ja": ja, "en": en}.get(PROMPT_LANG, zh)


def _fmt_task_row(t: dict) -> str:
    """Format a single task row for display."""
    from datetime import datetime as _dt
    status_icon = {"pending": "⏳", "paused": "⏸️", "cancelled": "❌", "completed": "✅", "failed": "⚠️", "processing": "🔄"}.get(t.get("status", ""), "❓")
    next_run = ""
    if t.get("trigger_time"):
        try:
            next_run = _dt.fromtimestamp(t["trigger_time"]).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    repeat = ""
    if t.get("cron_expr"):
        repeat = f"cron:{t['cron_expr']}"
    elif t.get("interval_seconds"):
        secs = t["interval_seconds"]
        if secs >= 86400:
            repeat = f"每{secs//86400}天"
        elif secs >= 3600:
            repeat = f"每{secs//3600}时"
        elif secs >= 60:
            repeat = f"每{secs//60}分"
        else:
            repeat = f"每{secs}秒"
    parts = [f"[ID:{t['id']}] {status_icon} {t.get('subject','')[:40]}"]
    parts.append(f"  类型:{t.get('type','')}  下次:{next_run or '-'}  {repeat}")
    return "\n".join(parts)


def _handle_task_manage(payload: dict, subject: str) -> str:
    from tasks.scheduler import scheduler
    action      = (payload or {}).get("action", "list")
    task_id     = (payload or {}).get("task_id")
    filt        = (payload or {}).get("filter", {})
    type_filt   = filt.get("type")
    subj_filt   = filt.get("subject")
    status_filt = filt.get("status")

    if action == "list":
        tasks = scheduler.list_tasks(
            status_filter=status_filt,
            type_filter=type_filt,
            subject_filter=subj_filt,
        )
        if not tasks:
            return _t("当前没有活跃的定时任务。", "アクティブな定期タスクはありません。", "No active scheduled tasks.")
        header = _t(f"当前有 {len(tasks)} 个任务：", f"アクティブなタスク：{len(tasks)} 件", f"Active tasks: {len(tasks)}")
        rows = "\n\n".join(_fmt_task_row(t) for t in tasks)
        hint = _t(
            "\n\n─────\n可回复「取消任务 ID:N」「暂停任务 ID:N」「恢复任务 ID:N」「删除任务 ID:N」进行管理。",
            "\n\n─────\n「タスクキャンセル ID:N」「一時停止 ID:N」「再開 ID:N」「削除 ID:N」と返信して管理できます。",
            "\n\n─────\nReply 'cancel task ID:N', 'pause task ID:N', 'resume task ID:N', or 'delete task ID:N' to manage.",
        )
        return header + "\n\n" + rows + hint

    if action in ("cancel", "pause", "resume", "delete"):
        if task_id:
            task_id = int(task_id)
            ok = {
                "cancel": scheduler.cancel_task,
                "pause":  scheduler.pause_task,
                "resume": scheduler.resume_task,
                "delete": scheduler.delete_task,
            }[action](task_id)
            verb_zh = {"cancel": "取消", "pause": "暂停", "resume": "恢复", "delete": "删除"}[action]
            verb_ja = {"cancel": "キャンセル", "pause": "一時停止", "resume": "再開", "delete": "削除"}[action]
            verb_en = {"cancel": "cancelled", "pause": "paused", "resume": "resumed", "delete": "deleted"}[action]
            if ok:
                return _t(f"✅ 已{verb_zh}任务 ID:{task_id}。", f"✅ タスク ID:{task_id} を{verb_ja}しました。", f"✅ Task ID:{task_id} {verb_en}.")
            else:
                return _t(f"⚠️ 未找到可{verb_zh}的任务 ID:{task_id}（已完成或不存在）。",
                          f"⚠️ タスク ID:{task_id} は{verb_ja}できませんでした（完了済みか存在しません）。",
                          f"⚠️ Task ID:{task_id} could not be {verb_en} (already done or not found).")
        else:
            # Batch cancel by filter
            if action == "cancel":
                count = scheduler.cancel_tasks_by_filter(type_filt, subj_filt)
                return _t(f"✅ 已取消 {count} 个匹配的任务。", f"✅ {count} 件のタスクをキャンセルしました。", f"✅ Cancelled {count} matching tasks.")
            return _t("⚠️ 批量操作仅支持取消，请提供 task_id 进行暂停/恢复/删除。",
                      "⚠️ 一括操作はキャンセルのみ対応です。一時停止/再開/削除はtask_idを指定してください。",
                      "⚠️ Batch operation only supports cancel. Provide task_id for pause/resume/delete.")

    return _t(f"⚠️ 未知 task_manage 操作：{action}", f"⚠️ 不明な操作：{action}", f"⚠️ Unknown action: {action}")


def execute_task_logic(task: dict, lang: str = "zh"):
    task_type = (task.get("type") or "email").lower()
    payload = task.get("payload") or {}
    subject = task.get("subject") or "定时任务结果"
    body = task.get("body") or ""

    # Helper for task logic to return translated results
    def _tl(zh, ja, en, ko):
        return {"zh": zh, "ja": ja, "en": en, "ko": ko}.get(lang, zh)

    if task_type == "email":
        pass
    elif task_type == "email_manage":
        # email_manage is handled interactively in process_email(); scheduled runs are not supported.
        body = _tl("⚠️ email_manage 仅支持即时执行，不支持定时任务。",
                   "⚠️ email_manage は即時実行のみ対応で、定期実行はサポートされていません。",
                   "⚠️ email_manage only supports immediate execution; scheduled runs are not supported.",
                   "⚠️ email_manage는 즉시 실행만 지원하며 예약된 작업은 지원하지 않습니다.")
    elif task_type == "task_manage":
        # Note: _handle_task_manage already uses internal i18n if available
        body = _handle_task_manage(payload, subject)
        subject = subject or _tl("任务管理结果", "タスク管理結果", "Task management result", "작업 관리 결과")
    elif task_type == "mcp_call":
        from utils.mcp_client import call_mcp_tool, list_mcp_tools
        server = payload.get("server", "")
        tool = payload.get("tool", "")
        args = payload.get("args") or {}
        if tool == "__list__":
            body = list_mcp_tools(server)
        else:
            body = call_mcp_tool(server, tool, args)
        subject = subject or f"MCP: {server}/{tool}"
    else:
        # Dispatch to skills (includes built-ins: weather, news, web_search, system_status, ai_job, report)
        try:
            from skills.loader import get_skill
            skill = get_skill(task_type)
        except Exception as e:
            log.warning(f"スキル '{task_type}' の読み込みに失敗: {e}")
            skill = None
        if skill:
            ai_name, backend = pick_task_ai(payload)
            ai = get_ai_provider(ai_name, backend)
            # If payload has no text content, inject task body/subject as fallback prompt
            if not payload.get("prompt") and not payload.get("text") and not payload.get("code"):
                payload = {**payload, "prompt": body or subject}
            # Pass lang if skill supports it
            try:
                body = skill.run(payload, ai_caller=ai, lang=lang)
            except TypeError:
                body = skill.run(payload, ai_caller=ai)
            subject = subject or skill.description
        else:
            body = _tl(f"⚠️ 未知任务类型：{task_type}", f"⚠️ 不明なタスク：{task_type}", f"⚠️ Unknown task type: {task_type}", f"⚠️ 알 수 없는 작업 유형: {task_type}")

    return subject, body
