"""
utils/parser.py - 简化版

只保留核心功能：
- detect_lang: 语言检测
- trim_email_body: 邮件正文截断
- parse_ai_response: 解析 AI 响应

移除自动任务检测，因为 AI 会自己处理所有任务
"""
import json
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple
from utils.logger import log


def detect_lang(text: str) -> str:
    """检测文本语言：zh / ja / ko / en"""
    if not text:
        return "en"
        
    # 韩文权重最高
    if re.search(r'[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F]', text):
        return "ko"
        
    # 日文次之（包含假名）
    if re.search(r'[\u3040-\u309F\u30A0-\u30FF]', text):
        return "ja"
        
    # 中文检测：如果包含一定数量的汉字，即判定为中文（汉字在混合文本中通常表示主语言）
    cjk_count = len(re.findall(r'[\u4E00-\u9FFF]', text))
    # 如果汉字超过 3 个，或者在极短文本中汉字占比显著（如“帮我写代码”），通常就是中文指令
    if cjk_count > 3 or (len(text) < 50 and cjk_count >= 2) or (len(text) < 20 and cjk_count >= 1):
        return "zh"
        
    return "en"


def trim_email_body(body: str, max_chars: int = 4000) -> str:
    """截断邮件正文，移除引用和签名"""
    if not body:
        return ""
    
    body = body.replace("\r\n", "\n").replace("\r", "\n")
    trimmed = body
    
    # 移除引用分隔符
    markers = [
        "-----Original Message-----",
        "--- Original Message ---",
        "----- Forwarded message -----",
        "Begin forwarded message:",
        "________________________________",
    ]
    for marker in markers:
        if marker in trimmed:
            trimmed = trimmed.split(marker)[0]
    
    # 移除 "On ... wrote:" 引用头
    trimmed = re.split(r'\nOn\s+\w{3},?\s+\d', trimmed)[0]
    trimmed = re.split(r'\n在\s+\S.*写道 [：:]', trimmed)[0]
    
    # 移除签名分隔符
    lines = trimmed.splitlines()
    for i, line in enumerate(lines):
        if i >= 3 and line.strip() in ("--", "---", "—", "__"):
            trimmed = "\n".join(lines[:i])
            break
    
    # 截断过长内容
    if len(trimmed) > max_chars:
        trimmed = trimmed[:max_chars] + "...(已截断)"
    
    return trimmed.strip()


def parse_ai_response(raw: str) -> Tuple:
    """
    解析 AI 的 JSON 响应
    
    返回：(subject, body, schedule_at, schedule_every, schedule_until, schedule_cron, attachments, task_type, task_payload, output)
    """
    json_str = None
    
    # 尝试从代码块中提取 JSON
    outer = re.search(r'```(?:json)?\s*(\{[\s\S]*\})\s*`*', raw)
    if outer:
        json_str = outer.group(1)
    else:
        # 直接查找 JSON 对象
        m = re.search(r'\{[\s\S]*\}', raw)
        if m:
            json_str = m.group()
    
    if json_str:
        try:
            data = json.loads(json_str)
            return (
                data.get("subject", ""),
                data.get("body") or "",
                data.get("schedule_at"),
                data.get("schedule_every"),
                data.get("schedule_until"),
                data.get("schedule_cron"),
                data.get("attachments", []),
                data.get("task_type"),
                data.get("task_payload"),
                data.get("output"),
            )
        except json.JSONDecodeError as e:
            log.warning(f"AI 响应 JSON 解析失败：{e}")
    
    # 没有 JSON，直接返回原文作为 body
    cleaned = re.sub(r'```(?:json)?', '', raw).strip()
    return "", cleaned, None, None, None, None, [], None, None, None
