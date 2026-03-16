import os
import shutil
import time
import subprocess
import logging
import requests
from typing import Optional
from core.config import WEATHER_API_KEY, WEATHER_DEFAULT_LOCATION, SEARCH_RESULTS_COUNT, AI_BACKENDS, DEFAULT_TASK_AI
from utils.search import web_search, format_search_results
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
        # 尝试从已配置的后端中选一个可用的
        priorities = ["claude", "openai", "gemini", "qwen"]
        for p in priorities:
            if p not in AI_BACKENDS:
                continue
            b = AI_BACKENDS[p]
            if b.get("type") == "cli":
                cmd = b.get("cmd", "")
                if cmd and (shutil.which(cmd) or os.path.isfile(cmd)):
                    ai_name = p
                    break
            elif b.get("api_key"):
                ai_name = p
                break
        if not ai_name or ai_name not in AI_BACKENDS:
            ai_name = list(AI_BACKENDS.keys())[0]

    backend = AI_BACKENDS.get(ai_name)
    return ai_name, backend

def execute_task_logic(task: dict):
    task_type = (task.get("type") or "email").lower()
    payload = task.get("payload") or {}
    subject = task.get("subject") or "定时任务结果"
    body = task.get("body") or ""

    if task_type == "email": pass
    elif task_type == "weather":
        loc = payload.get("location") or WEATHER_DEFAULT_LOCATION
        ai_name, backend = pick_task_ai(payload)
        ai = get_ai_provider(ai_name, backend)
        weather_data = fetch_weather_data(loc)
        if weather_data:
            prompt = f"以下是 {loc} 的实时天气数据，请用自然语言整理成简洁的天气播报：\n\n{weather_data}"
        else:
            prompt = f"请搜索并告诉我现在 {loc} 的天气情况，包括温度和天气现象。"
        body = ai.call(prompt)
        subject = subject or f"天气更新：{loc}"
    elif task_type == "news":
        ai_name, backend = pick_task_ai(payload)
        ai = get_ai_provider(ai_name, backend)
        q = payload.get("query") or body or "最新的新闻"
        if backend.get("native_web_search"):
            prompt = f"请搜索并总结关于以下主题的最新新闻：{q}。重要提示：必须在回复中包含每条新闻的原始链接（URL），不要删减链接信息。"
            body = ai.call(prompt)
        else:
            results = web_search(q, SEARCH_RESULTS_COUNT)
            if results:
                search_ctx = format_search_results(results)
                prompt = f"以下是关于「{q}」的网络搜索结果，请将其整理为新闻摘要，按重要性排列，保留并完整显示每条的原始链接（URL）。\n\n{search_ctx}"
            else:
                prompt = f"请搜索并总结关于以下主题的最新新闻：{q}。重要提示：必须在回复中包含每条新闻的原始链接（URL），不要删减链接信息。"
            body = ai.call(prompt)
        subject = subject or "新闻汇总"
    elif task_type == "web_search":
        q = payload.get("query") or ""
        results = web_search(q, payload.get("count", 5), payload.get("engine"))
        body = format_search_results(results) if results else "没有找到结果。"
        subject = subject or f"网页检索：{q}"
    elif task_type == "system_status":
        body = fetch_system_status(payload)
        subject = subject or "OS 系统运行状态"
    elif task_type == "ai_job":
        ai_name, backend = pick_task_ai(payload)
        ai = get_ai_provider(ai_name, backend)
        prompt = payload.get("prompt") or body
        body = ai.call(prompt) or "AI 没有返回内容。"
        subject = subject or f"AI 任务结果 ({ai_name})"
    elif task_type == "report":
        report_text = ""
        if payload.get("include_system_status"):
            report_text += "【系统运行状态】\n" + fetch_system_status(payload)
        if payload.get("use_ai_summary", True):
            ai_name, backend = pick_task_ai(payload)
            ai = get_ai_provider(ai_name, backend)
            prompt = f"请将以下内容汇总成简洁日报，分点输出，重点突出。⚠️ 核心要求：必须完整保留并显示所有新闻和网页检索结果中的原始链接（URL），严禁删减链接信息！\n\n内容如下：\n{report_text}"
            body = ai.call(prompt).strip() or report_text
            subject = subject or f"日报 ({ai_name})"
        else:
            body = report_text
            subject = subject or "日报"
    else:
        body = f"⚠️ 未知任务类型：{task_type}"

    return subject, body
