import json
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from core.config import WEATHER_DEFAULT_LOCATION, NEWS_DEFAULT_QUERY

def _parse_time_hhmm(text: str):
    m = re.search(r"(\d{1,2})[:：](\d{2})", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})\s*点(?:半)?", text)
    if m:
        h = int(m.group(1))
        if "半" in m.group(0):
            return h, 30
        return h, 0
    return None, None

def _next_weekday(base: datetime, weekday: int):
    days_ahead = (weekday - base.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return base + timedelta(days=days_ahead)

def parse_schedule_from_text(text: str):
    low = text.lower()
    schedule_at = None
    schedule_every = None
    schedule_until = None

    rel_min = re.search(r"(?:每|every|毎|매)\s*(\d+)\s*(分钟|min|minutes|分|분)", low)
    rel_hour = re.search(r"(?:每|every|毎|매)\s*(\d+)\s*(小时|hour|hours|h|時間|시간)", low)
    rel_day = re.search(r"(?:每|every|毎|매)\s*(\d+)\s*(天|day|days|d|日|일)", low)
    if rel_min:
        schedule_every = f"{rel_min.group(1)}m"
    elif rel_hour:
        schedule_every = f"{rel_hour.group(1)}h"
    elif rel_day:
        schedule_every = f"{rel_day.group(1)}d"

    if any(k in text for k in ["每天", "毎日", "매일"]) and not schedule_every:
        schedule_every = "1d"

    if any(k in text for k in ["每周", "毎週", "매주"]) and not schedule_every:
        schedule_every = "7d"

    date_time = re.search(r"(\d{4}-\d{2}-\d{2})(?:\s*[tT ]\s*(\d{1,2}:\d{2}))?", low)
    if date_time:
        d = date_time.group(1)
        t = date_time.group(2) or "09:00"
        schedule_at = f"{d}T{t}:00"

    until_match = re.search(r"(?:截止|直到|until)\s*(\d{4}-\d{2}-\d{2}(?:[tT ]\d{1,2}:\d{2})?)", low)
    if until_match:
        schedule_until = until_match.group(1).replace(" ", "T")

    now = datetime.now()
    if not schedule_at:
        if any(k in text for k in ["今天", "今日", "今日", "오늘"]):
            h, m = _parse_time_hhmm(text)
            if h is not None:
                dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if dt <= now:
                    dt = dt + timedelta(days=1)
                schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["明天", "明日", "明日", "내일"]):
            h, m = _parse_time_hhmm(text)
            h = 9 if h is None else h
            m = 0 if m is None else m
            dt = (now + timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
            schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["今晚", "今夜", "晚上", "今晚", "오늘 밤", "저녁"]):
            h, m = _parse_time_hhmm(text)
            h = 20 if h is None else h
            m = 0 if m is None else m
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if dt <= now:
                dt = dt + timedelta(days=1)
            schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["早上", "上午", "朝", "午前", "아침", "오전"]):
            h, m = _parse_time_hhmm(text)
            h = 9 if h is None else h
            m = 0 if m is None else m
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if dt <= now:
                dt = dt + timedelta(days=1)
            schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["下午", "午後", "오후"]):
            h, m = _parse_time_hhmm(text)
            h = 15 if h is None else h
            m = 0 if m is None else m
            dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if dt <= now:
                dt = dt + timedelta(days=1)
            schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["每周", "毎週", "매주"]):
            weekday_map = {
                "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6,
                "月": 0, "火": 1, "水": 2, "木": 3, "金": 4, "土": 5, "日曜": 6, "日": 6,
                "월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6,
            }
            m = re.search(r"(?:每周|毎週|매주)([一二三四五六日天月火水木金土日曜월화수목금토일])", text)
            if m:
                target = weekday_map[m.group(1)]
                h, m2 = _parse_time_hhmm(text)
                h = 9 if h is None else h
                m2 = 0 if m2 is None else m2
                dt = _next_weekday(now, target).replace(hour=h, minute=m2, second=0, microsecond=0)
                schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")
        if any(k in text for k in ["每天", "毎日", "매일"]):
            h, m = _parse_time_hhmm(text)
            if h is not None:
                dt = now.replace(hour=h, minute=m, second=0, microsecond=0)
                if dt <= now:
                    dt = dt + timedelta(days=1)
                schedule_at = dt.strftime("%Y-%m-%dT%H:%M:%S")

    return schedule_at, schedule_every, schedule_until

def auto_detect_task(instruction: str):
    low = instruction.lower()
    task_type = None
    payload = {}
    output = {}

    sys_keywords = ["系统", "os", "系统运行状态", "系统状态", "运行状态", "资源使用", "cpu", "内存", "磁盘", "进程", "sysinfo", "system status"]
    if any(k in low for k in sys_keywords):
        task_type = "system_status"
        if any(k in low for k in ["进程", "process"]):
            payload["include_processes"] = True
    
    if not task_type:
        if any(k in low for k in ["天气", "weather", "天気", "날씨"]):
            task_type = "weather"
            m = re.search(r"(?:天气|weather|天気|날씨)[：: ]?([^\n，,;；]+)", instruction, re.I)
            if m:
                payload["location"] = m.group(1).strip()
        elif any(k in low for k in ["新闻", "news", "ニュース", "뉴스"]):
            task_type = "news"
            m = re.search(r"(?:新闻|news|ニュース|뉴스)[：: ]?([^\n，,;；]+)", instruction, re.I)
            if m:
                payload["query"] = m.group(1).strip()
        elif any(k in low for k in ["检索", "搜索", "网页", "search", "look up", "find", "検索", "검색"]):
            task_type = "web_search"
            m = re.search(r"(?:检索|搜索|网页检索|search|look up|find|検索|검색)[：: ]?([^\n]+)", instruction, re.I)
            if m:
                payload["query"] = m.group(1).strip()
    
    if any(k in low for k in ["日报", "周报", "月报", "report", "summary", "レポート", "보고서", "리포트"]):
        if task_type == "system_status":
            task_type = "report"
            payload["include_system_status"] = True
        elif not task_type:
            task_type = "report"
            if any(k in low for k in sys_keywords):
                payload["include_system_status"] = True
            if any(k in low for k in ["天气", "weather", "天気", "날씨"]):
                payload["weather_locations"] = [WEATHER_DEFAULT_LOCATION]
            if any(k in low for k in ["新闻", "news", "ニュース", "뉴스"]):
                payload["news_query"] = NEWS_DEFAULT_QUERY

    if any(k in low for k in ["ai", "分析", "总结", "润色", "翻译", "生成", "分析", "要約", "翻訳", "生成", "분석", "요약", "번역", "생성"]):
        if not task_type:
            task_type = "ai_job"
        payload.setdefault("prompt", instruction.strip())

    if any(k in low for k in ["归档", "archive", "保存", "save", "保存", "アーカイブ", "저장", "아카이브"]):
        output["archive"] = True
        output["archive_dir"] = "reports"
    if any(k in low for k in ["仅归档", "no email", "不要发邮件", "メール不要", "메일 보내지", "이메일 필요없음"]):
        output["email"] = False

    schedule_at, schedule_every, schedule_until = parse_schedule_from_text(instruction)
    return task_type, payload, output, schedule_at, schedule_every, schedule_until

def auto_detect_tasks(instruction: str):
    parts = [p.strip() for p in re.split(r"[；;\n]+", instruction) if p.strip()]
    tasks = []
    for part in parts:
        task_type, payload, output, sch_at, sch_every, sch_until = auto_detect_task(part)
        if task_type or sch_at or sch_every:
            tasks.append({
                "task_type": task_type or "email",
                "task_payload": payload or {},
                "output": output or {},
                "schedule_at": sch_at,
                "schedule_every": sch_every,
                "schedule_until": sch_until,
                "raw": part,
            })
    return tasks

def trim_email_body(body: str, max_chars: int = 4000) -> str:
    """截断邮件正文，移除引用历史和过长的签名，减少 Token 消耗"""
    if not body:
        return ""

    # 精确匹配邮件引用分隔符（避免误截断正文内容）
    exact_markers = [
        "-----Original Message-----",
        "--- Original Message ---",
        "________________________________",
        "--- 会话历史 ---",
    ]
    trimmed_body = body
    for marker in exact_markers:
        if marker in trimmed_body:
            trimmed_body = trimmed_body.split(marker)[0]

    # 英文引用头：必须以换行开头，"On <日期/时间> ... wrote:" 格式
    trimmed_body = re.split(r'\nOn\s+\w{3},?\s+\d', trimmed_body)[0]

    # 中文引用头："在 <日期> 写道：" 完整格式（行首）
    trimmed_body = re.split(r'\n在\s+\S.*写道[：:]', trimmed_body)[0]

    # 截断过长的单封邮件正文（防止超长垃圾邮件或日志文件）
    if len(trimmed_body) > max_chars:
        trimmed_body = trimmed_body[:max_chars] + "...(正文过长已截断)"

    return trimmed_body.strip()

def parse_ai_response(raw: str):
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return (
                data.get("subject", ""),
                data.get("body", raw),
                data.get("schedule_at"),
                data.get("schedule_every"),
                data.get("schedule_until"),
                data.get("schedule_cron"),
                data.get("attachments", []),
                data.get("task_type"),
                data.get("task_payload"),
                data.get("output"),
            )
        except Exception:
            pass
    return "", raw, None, None, None, None, [], None, None, None
