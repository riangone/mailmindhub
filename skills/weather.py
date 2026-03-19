"""
Weather Skill — 天气查询

支持多种执行方式（优先级从高到低）:
1. AI 原生搜索（如果 AI 支持 native_web_search）
2. WeatherAPI.com（如果配置了 API Key）
3. MCP 天气服务器（如果已配置）
"""

from skills import BaseSkill
from ai.skills import execute_ai_skill, fetch_weather_via_api, format_weather_result
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider
from core.config import WEATHER_DEFAULT_LOCATION, PROMPT_LANG


class WeatherSkill(BaseSkill):
    name = "weather"
    description = "天气查询与播报"
    description_ja = "天気情報の取得と配信"
    description_en = "Weather lookup and broadcast"
    keywords = ["天气", "weather", "天気", "날씨", "气温", "预报"]

    def run(self, payload: dict, ai_caller=None) -> str:
        loc = payload.get("location") or WEATHER_DEFAULT_LOCATION
        lang = payload.get("lang", PROMPT_LANG)
        
        # 获取 AI 后端配置
        ai_name, backend = pick_task_ai(payload)
        ai = ai_caller or get_ai_provider(ai_name, backend)
        
        # 1. 优先使用 AI 原生搜索（如果 AI 支持）
        if backend.get("native_web_search"):
            prompt = f"请搜索并告诉我现在 {loc} 的天气情况，包括温度、湿度、风速等详细信息。"
            result = ai.call(prompt)
            if result:
                return result
        
        # 2. 尝试 WeatherAPI.com
        weather_data = fetch_weather_via_api(loc)
        if weather_data:
            prompt = f"以下是 {loc} 的实时天气数据，请用自然语言整理成简洁的天气播报：\n\n{format_weather_result(weather_data, lang)}"
            return ai.call(prompt) or "⚠️ 天气信息获取失败。"
        
        # 3. 尝试 MCP 天气服务器
        from ai.skills import fetch_weather_via_mcp
        mcp_result = fetch_weather_via_mcp(loc)
        if mcp_result:
            try:
                import json
                data = json.loads(mcp_result)
                if "error" not in data:
                    prompt = f"以下是 {loc} 的实时天气数据，请用自然语言整理成简洁的天气播报：\n\n{format_weather_result(data, lang)}"
                    return ai.call(prompt) or "⚠️ 天气信息获取失败。"
            except json.JSONDecodeError:
                # MCP 返回的可能是格式化文本
                return mcp_result
        
        return "⚠️ 天气信息获取失败。"


SKILL = WeatherSkill()
