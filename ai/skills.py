"""
AI Skills — 通过 AI 原生能力 + 工具调用实现的功能模块

与 Python skill (skills/*.py) 的区别：
- Python skill: 本地 Python 代码执行逻辑，返回结果
- AI skill: 通过 prompt 引导 AI 调用外部工具（MCP/API）完成任务

配置方式（.env）：
  AI_SKILLS_ENABLED=weather,news,stock,web_search
  WEATHER_API_KEY=xxx
  NEWS_API_KEY=xxx  (可选)
"""

import os
import json
import requests
from typing import Optional, Any, Dict, List
from utils.logger import log
from core.config import (
    WEATHER_API_KEY,
    WEATHER_DEFAULT_LOCATION,
    SEARCH_RESULTS_COUNT,
    WEB_SEARCH_ENGINE,
    BRAVE_API_KEY,
    WEB_SEARCH_TIMEOUT,
    NEWS_API_KEY,
    NEWS_DEFAULT_LANGUAGE,
    NEWS_DEFAULT_PAGE_SIZE,
)


# ─────────────────────────────────────────────────────────────────────────────
#  AI Skill 注册表
# ─────────────────────────────────────────────────────────────────────────────

AI_SKILLS: dict = {}


def register_skill(name: str, func: callable, description: str, keywords: list = None):
    """注册一个 AI skill"""
    AI_SKILLS[name] = {
        "name": name,
        "func": func,
        "description": description,
        "keywords": keywords or [],
    }


def get_ai_skill(name: str) -> Optional[dict]:
    """获取指定的 AI skill"""
    return AI_SKILLS.get(name)


def list_ai_skills() -> list:
    """返回所有已注册的 AI skill 列表"""
    return list(AI_SKILLS.values())


# ─────────────────────────────────────────────────────────────────────────────
#  MCP 工具调用支持
# ─────────────────────────────────────────────────────────────────────────────

def call_mcp_tool_wrapper(server: str, tool: str, args: dict) -> Optional[str]:
    """
    通过 MCP 协议调用工具
    返回结果字符串，失败时返回 None
    """
    try:
        from utils.mcp_client import call_mcp_tool as _call_mcp
        result = _call_mcp(server, tool, args)
        if result and not result.startswith("⚠️"):
            return result
        log.warning(f"MCP 调用失败：{result}")
        return None
    except Exception as e:
        log.warning(f"MCP 调用异常：{e}")
        return None


def list_mcp_tools_wrapper(server: str) -> List[dict]:
    """列出 MCP 服务器上的可用工具"""
    try:
        from utils.mcp_client import MCPSession, _get_server_cmd
        if not _get_server_cmd(server):
            return []
        session = MCPSession(server)
        if session.open():
            tools = session.list_tools()
            session.close()
            return tools
    except Exception:
        pass
    return []


# ─────────────────────────────────────────────────────────────────────────────
#  通用工具函数：天气查询（支持 MCP 和 API）
# ─────────────────────────────────────────────────────────────────────────────

def fetch_weather_via_api(location: str) -> Optional[Dict[str, Any]]:
    """通过 WeatherAPI.com 获取天气数据"""
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
        return {
            "location": loc["name"],
            "country": loc["country"],
            "localtime": loc["localtime"],
            "condition": cur["condition"]["text"],
            "temp_c": cur["temp_c"],
            "feelslike_c": cur["feelslike_c"],
            "humidity": cur["humidity"],
            "wind_kph": cur["wind_kph"],
            "wind_dir": cur["wind_dir"],
            "vis_km": cur["vis_km"],
        }
    except Exception as e:
        log.warning(f"WeatherAPI 查询失败：{e}")
        return None


def fetch_weather_via_mcp(location: str) -> Optional[str]:
    """通过 MCP 天气服务器获取天气"""
    return call_mcp_tool_wrapper("weather", "get_weather", {"location": location})


def format_weather_result(data: Dict[str, Any], lang: str = "zh") -> str:
    """格式化天气数据为自然语言"""
    if lang == "ja":
        return (
            f"地点：{data['location']}、{data['country']}\n"
            f"時刻：{data['localtime']}\n"
            f"天気：{data['condition']}\n"
            f"気温：{data['temp_c']}°C（体感 {data['feelslike_c']}°C）\n"
            f"湿度：{data['humidity']}%\n"
            f"風速：{data['wind_kph']} km/h {data['wind_dir']}\n"
            f"視程：{data['vis_km']} km"
        )
    elif lang == "en":
        return (
            f"Location: {data['location']}, {data['country']}\n"
            f"Time: {data['localtime']}\n"
            f"Condition: {data['condition']}\n"
            f"Temperature: {data['temp_c']}°C (feels like {data['feelslike_c']}°C)\n"
            f"Humidity: {data['humidity']}%\n"
            f"Wind: {data['wind_kph']} km/h {data['wind_dir']}\n"
            f"Visibility: {data['vis_km']} km"
        )
    elif lang == "ko":
        return (
            f"위치：{data['location']}, {data['country']}\n"
            f"시간：{data['localtime']}\n"
            f"날씨：{data['condition']}\n"
            f"온도：{data['temp_c']}°C (체감 {data['feelslike_c']}°C)\n"
            f"습도：{data['humidity']}%\n"
            f"풍속：{data['wind_kph']} km/h {data['wind_dir']}\n"
            f"가시거리：{data['vis_km']} km"
        )
    else:
        return (
            f"地点：{data['location']}，{data['country']}\n"
            f"时间：{data['localtime']}\n"
            f"天气：{data['condition']}\n"
            f"温度：{data['temp_c']}°C（体感 {data['feelslike_c']}°C）\n"
            f"湿度：{data['humidity']}%\n"
            f"风速：{data['wind_kph']} km/h {data['wind_dir']}\n"
            f"能见度：{data['vis_km']} km"
        )


# ─────────────────────────────────────────────────────────────────────────────
#  Weather Skill — 天气查询
# ─────────────────────────────────────────────────────────────────────────────

def fetch_weather_data(location: str) -> Optional[dict]:
    """从 WeatherAPI.com 获取天气数据"""
    if not WEATHER_API_KEY:
        log.warning("WeatherAPI: 未配置 WEATHER_API_KEY")
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
        return {
            "location": loc["name"],
            "country": loc["country"],
            "localtime": loc["localtime"],
            "condition": cur["condition"]["text"],
            "temp_c": cur["temp_c"],
            "feelslike_c": cur["feelslike_c"],
            "humidity": cur["humidity"],
            "wind_kph": cur["wind_kph"],
            "wind_dir": cur["wind_dir"],
            "vis_km": cur["vis_km"],
        }
    except Exception as e:
        log.warning(f"WeatherAPI 查询失败：{e}")
        return None


def ai_skill_weather(query: str, lang: str = "zh") -> Optional[str]:
    """
    AI skill: 天气查询
    调用方式：AI 返回 JSON {"skill": "weather", "payload": {"location": "Tokyo"}}

    执行策略（优先级从高到低）:
    1. 返回 None 让 AI 使用 native_web_search 自行搜索（AI 原生优先）
    2. WeatherAPI.com（如果配置了 API Key）
    3. MCP 天气服务器（如果已配置）
    """
    location = query or WEATHER_DEFAULT_LOCATION

    # 1. 优先让 AI 使用 native_web_search 自行搜索（如果 AI 支持）
    # 返回 None 表示让上层调用 AI 自行处理
    # 这样可以让支持联网的 AI（如 Claude CLI、Gemini CLI）使用最新数据
    
    # 2. 尝试 WeatherAPI.com
    data = fetch_weather_via_api(location)
    if data:
        return format_weather_result(data, lang)

    # 3. 尝试 MCP 天气服务器
    mcp_result = fetch_weather_via_mcp(location)
    if mcp_result:
        try:
            data = json.loads(mcp_result)
            if "error" not in data:
                return format_weather_result(data, lang)
        except json.JSONDecodeError:
            # MCP 返回的可能是格式化文本
            return mcp_result

    # 都失败了，返回 None 让 AI 自行搜索
    return None


register_skill(
    "weather",
    ai_skill_weather,
    "天气查询与播报（AI 原生→WeatherAPI→MCP）",
    ["天气", "weather", "天気", "날씨", "气温", "预报"],
)


# ─────────────────────────────────────────────────────────────────────────────
#  News Skill — 新闻搜索
# ─────────────────────────────────────────────────────────────────────────────

def fetch_news_via_api(query: str, lang: str = "zh") -> Optional[List[Dict[str, Any]]]:
    """通过 NewsAPI 获取新闻"""
    if not NEWS_API_KEY:
        return None
    try:
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": query,
                "language": lang,
                "pageSize": NEWS_DEFAULT_PAGE_SIZE,
                "sortBy": "publishedAt",
                "apiKey": NEWS_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "ok":
            return None
        articles = []
        for art in data.get("articles", [])[:NEWS_DEFAULT_PAGE_SIZE]:
            articles.append({
                "title": art.get("title", ""),
                "description": art.get("description", ""),
                "url": art.get("url", ""),
                "source": art.get("source", {}).get("name", ""),
                "published_at": art.get("publishedAt", ""),
            })
        return articles
    except Exception as e:
        log.warning(f"NewsAPI 查询失败：{e}")
        return None


def fetch_news_via_search(query: str, num_results: int = 5) -> Optional[List[Dict[str, Any]]]:
    """通过网页搜索获取新闻"""
    try:
        from utils.search import web_search
        results = web_search(f"{query} 最新新闻", num_results, engine="google")
        if results:
            return [
                {
                    "title": r.get("title", ""),
                    "description": r.get("snippet", ""),
                    "url": r.get("url", ""),
                    "source": "",
                    "published_at": "",
                }
                for r in results
            ]
        return None
    except Exception as e:
        log.warning(f"网页搜索新闻失败：{e}")
        return None


def format_news_result(articles: List[Dict[str, Any]], lang: str = "zh") -> str:
    """格式化新闻列表"""
    if not articles:
        return ""
    
    lines = []
    for i, art in enumerate(articles, 1):
        title = art.get("title", "无标题")
        desc = art.get("description", "")
        url = art.get("url", "")
        source = art.get("source", "")
        published = art.get("published_at", "")
        
        if lang == "ja":
            lines.append(f"{i}. 【{title}】")
            if source: lines.append(f"   出典：{source}")
            if published: lines.append(f"   公開：{published}")
            if desc: lines.append(f"   {desc}")
            if url: lines.append(f"   🔗 {url}")
        elif lang == "en":
            lines.append(f"{i}. 【{title}】")
            if source: lines.append(f"   Source: {source}")
            if published: lines.append(f"   Published: {published}")
            if desc: lines.append(f"   {desc}")
            if url: lines.append(f"   🔗 {url}")
        elif lang == "ko":
            lines.append(f"{i}. 【{title}】")
            if source: lines.append(f"   출처：{source}")
            if published: lines.append(f"   게시：{published}")
            if desc: lines.append(f"   {desc}")
            if url: lines.append(f"   🔗 {url}")
        else:
            lines.append(f"{i}. 【{title}】")
            if source: lines.append(f"   来源：{source}")
            if published: lines.append(f"   发布：{published}")
            if desc: lines.append(f"   {desc}")
            if url: lines.append(f"   🔗 {url}")
    
    return "\n".join(lines)


def ai_skill_news(query: str, lang: str = "zh") -> Optional[str]:
    """
    AI skill: 新闻搜索
    执行策略（优先级从高到低）:
    1. 返回 None 让 AI 使用 native_web_search 自行搜索（AI 原生优先）
    2. NewsAPI（如果配置了 API Key）
    3. 网页搜索（本地搜索引擎）
    """
    q = query or "最新新闻"

    # 1. 优先让 AI 使用 native_web_search 自行搜索
    # 返回 None 表示让上层调用 AI 自行处理
    
    # 2. 尝试 NewsAPI
    articles = fetch_news_via_api(q, lang)
    if articles:
        return format_news_result(articles, lang)

    # 3. 尝试网页搜索
    results = fetch_news_via_search(q)
    if results:
        return format_news_result(results, lang)

    # 都失败了，返回 None 让 AI 自行搜索
    return None


register_skill(
    "news",
    ai_skill_news,
    "新闻搜索与摘要（AI 原生→NewsAPI→网页搜索）",
    ["新闻", "新闻摘要", "news", "ニュース", "뉴스", "资讯"],
)


# ─────────────────────────────────────────────────────────────────────────────
#  Stock Skill — 股票/加密货币行情
# ─────────────────────────────────────────────────────────────────────────────

def fetch_stock_via_search(query: str, num_results: int = 5) -> Optional[List[Dict[str, Any]]]:
    """通过网页搜索获取股票/加密货币行情"""
    try:
        from utils.search import web_search
        # 智能判断查询类型
        search_query = query.lower()
        if any(kw in search_query for kw in ["btc", "bitcoin", "eth", "crypto", "币"]):
            search_q = f"{query} price today USD"
        else:
            search_q = f"{query} stock price today"
        
        results = web_search(search_q, num_results, engine="google")
        if results:
            return [
                {
                    "title": r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                    "url": r.get("url", ""),
                }
                for r in results
            ]
        return None
    except Exception as e:
        log.warning(f"股票搜索失败：{e}")
        return None


def format_stock_result(results: List[Dict[str, Any]], lang: str = "zh") -> str:
    """格式化股票/加密货币行情"""
    if not results:
        return ""
    
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "无标题")
        snippet = r.get("snippet", "")
        url = r.get("url", "")
        
        if lang == "ja":
            lines.append(f"{i}. 【{title}】")
            if snippet: lines.append(f"   {snippet}")
            if url: lines.append(f"   🔗 {url}")
        elif lang == "en":
            lines.append(f"{i}. 【{title}】")
            if snippet: lines.append(f"   {snippet}")
            if url: lines.append(f"   🔗 {url}")
        elif lang == "ko":
            lines.append(f"{i}. 【{title}】")
            if snippet: lines.append(f"   {snippet}")
            if url: lines.append(f"   🔗 {url}")
        else:
            lines.append(f"{i}. 【{title}】")
            if snippet: lines.append(f"   {snippet}")
            if url: lines.append(f"   🔗 {url}")
    
    return "\n".join(lines)


def ai_skill_stock(query: str, lang: str = "zh") -> Optional[str]:
    """
    AI skill: 股票/加密货币行情查询
    执行策略（优先级从高到低）:
    1. 返回 None 让 AI 使用 native_web_search 自行搜索（AI 原生优先）
    2. 网页搜索获取实时行情
    """
    if not query:
        return None

    # 1. 优先让 AI 使用 native_web_search 自行搜索
    # 返回 None 表示让上层调用 AI 自行处理
    
    # 2. 尝试网页搜索
    results = fetch_stock_via_search(query)
    if results:
        return format_stock_result(results, lang)

    # 都失败了，返回 None 让 AI 自行搜索
    return None


register_skill(
    "stock",
    ai_skill_stock,
    "查询股票/加密货币行情及分析（AI 原生→网页搜索）",
    ["股票", "股市", "行情", "stock", "stocks", "crypto", "bitcoin", "加密货币", "株価", "相場", "주식", "코인"],
)


# ─────────────────────────────────────────────────────────────────────────────
#  Web Search Skill — 网页搜索
# ─────────────────────────────────────────────────────────────────────────────

def ai_skill_web_search(query: str, lang: str = "zh") -> str:
    """
    AI skill: 网页搜索
    如果配置了本地搜索引擎，则返回搜索结果；否则让 AI 自行处理
    """
    # 这个 skill 主要由 AI 通过 native_web_search 自行处理
    return None


register_skill(
    "web_search",
    ai_skill_web_search,
    "网页搜索",
    ["搜索", "检索", "search", "検索", "검색", "查找"],
)


# ─────────────────────────────────────────────────────────────────────────────
#  工具函数：生成 AI skill 提示词
# ─────────────────────────────────────────────────────────────────────────────

def get_ai_skills_prompt(lang: str = "zh") -> str:
    """
    生成 AI skill 提示词，告知 AI 可用的技能及调用方式
    使用 get_skills_prompt_section 生成统一格式的技能列表
    """
    section = get_skills_prompt_section(lang)
    if not section:
        return ""
    
    # 添加示例
    if lang == "ja":
        examples = [
            "例：",
            '  - 天気：`{"skill": "weather", "payload": {"location": "東京"}}`',
            '  - ニュース：`{"skill": "news", "payload": {"query": "AI 最新ニュース"}}`',
            '  - 株価：`{"skill": "stock", "payload": {"query": "TSLA"}}`',
            '  - 検索：`{"skill": "web_search", "payload": {"query": "OpenAI 発表"}}`',
        ]
    elif lang == "en":
        examples = [
            "Examples:",
            '  - Weather: `{"skill": "weather", "payload": {"location": "Tokyo"}}`',
            '  - News: `{"skill": "news", "payload": {"query": "latest AI news"}}`',
            '  - Stock: `{"skill": "stock", "payload": {"query": "TSLA"}}`',
            '  - Search: `{"skill": "web_search", "payload": {"query": "OpenAI announcement"}}`',
        ]
    elif lang == "ko":
        examples = [
            "예시:",
            '  - 날씨：`{"skill": "weather", "payload": {"location": "서울"}}`',
            '  - 뉴스：`{"skill": "news", "payload": {"query": "AI 최신 뉴스"}}`',
            '  - 주식：`{"skill": "stock", "payload": {"query": "TSLA"}}`',
            '  - 검색：`{"skill": "web_search", "payload": {"query": "OpenAI 발표"}}`',
        ]
    else:
        examples = [
            "示例：",
            '  - 天气：`{"skill": "weather", "payload": {"location": "北京"}}`',
            '  - 新闻：`{"skill": "news", "payload": {"query": "AI 最新动态"}}`',
            '  - 股票：`{"skill": "stock", "payload": {"query": "TSLA"}}`',
            '  - 搜索：`{"skill": "web_search", "payload": {"query": "OpenAI 发布会"}}`',
        ]
    
    return section + "\n".join(examples)


# ─────────────────────────────────────────────────────────────────────────────
#  执行 AI skill
# ─────────────────────────────────────────────────────────────────────────────

def execute_ai_skill(skill_name: str, payload: dict, lang: str = "zh") -> Optional[str]:
    """
    执行指定的 AI skill
    返回结果字符串，或 None（表示让 AI 自行处理）
    """
    skill = get_ai_skill(skill_name)
    if not skill:
        log.warning(f"AI skill '{skill_name}' 不存在")
        return None

    query = payload.get("query") or payload.get("location") or payload.get("prompt") or ""
    try:
        result = skill["func"](query, lang)
        if result:
            log.debug(f"AI skill '{skill_name}' 执行成功")
        return result
    except Exception as e:
        log.warning(f"AI skill '{skill_name}' 执行失败：{e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  生成技能列表提示（用于注入到 prompt 模板）
# ─────────────────────────────────────────────────────────────────────────────

def get_skills_prompt_section(lang: str = "zh") -> str:
    """
    生成技能列表提示段落，可注入到 prompt 模板中
    """
    skills = list_ai_skills()
    if not skills:
        return ""
    
    if lang == "ja":
        lines = [
            "## 利用可能な AI スキル",
            "以下の方法でスキルを呼び出せます：",
            "1. task_type=\"ai_skill\", task_payload={\"skill\": \"スキル名\", \"payload\": {...}}",
            "2. スキル名を task_type として直接使用：task_type=\"スキル名\", task_payload={...}",
            "",
            "スキル一覧：",
        ]
        for sk in skills:
            kw = "、".join(sk["keywords"][:3]) if sk["keywords"] else "なし"
            lines.append(f"- **{sk['name']}**: {sk['description']}（キーワード：{kw}）")
        lines.append("")
    elif lang == "en":
        lines = [
            "## Available AI Skills",
            "You can invoke skills using:",
            "1. task_type=\"ai_skill\", task_payload={\"skill\": \"skill_name\", \"payload\": {...}}",
            "2. Skill name directly as task_type: task_type=\"skill_name\", task_payload={...}",
            "",
            "Skill list:",
        ]
        for sk in skills:
            kw = ", ".join(sk["keywords"][:3]) if sk["keywords"] else "none"
            lines.append(f"- **{sk['name']}**: {sk['description']} (keywords: {kw})")
        lines.append("")
    elif lang == "ko":
        lines = [
            "## 사용 가능한 AI 스킬",
            "다음 방법으로 스킬을 호출할 수 있습니다:",
            "1. task_type=\"ai_skill\", task_payload={\"skill\": \"스킬명\", \"payload\": {...}}",
            "2. 스킬 이름을 task_type 으로 직접 사용: task_type=\"스킬명\", task_payload={...}",
            "",
            "스킬 목록:",
        ]
        for sk in skills:
            kw = "、".join(sk["keywords"][:3]) if sk["keywords"] else "없음"
            lines.append(f"- **{sk['name']}**: {sk['description']}（키워드：{kw}）")
        lines.append("")
    else:
        lines = [
            "## 可用 AI 技能",
            "你可以通过以下方式调用技能：",
            "1. task_type=\"ai_skill\", task_payload={\"skill\": \"技能名\", \"payload\": {...}}",
            "2. 直接使用技能名作为 task_type: task_type=\"技能名\", task_payload={...}",
            "",
            "技能列表：",
        ]
        for sk in skills:
            kw = "、".join(sk["keywords"][:3]) if sk["keywords"] else "无"
            lines.append(f"- **{sk['name']}**: {sk['description']}（关键词：{kw}）")
        lines.append("")
    
    return "\n".join(lines)
