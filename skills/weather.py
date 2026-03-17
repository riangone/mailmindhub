from skills import BaseSkill
from tasks.registry import pick_task_ai, fetch_weather_data
from ai.providers import get_ai_provider
from core.config import WEATHER_DEFAULT_LOCATION


class WeatherSkill(BaseSkill):
    name = "weather"
    description = "天气查询与播报"
    description_ja = "天気情報の取得と配信"
    description_en = "Weather lookup and broadcast"
    keywords = ["天气", "weather", "天気", "날씨", "气温", "预报"]

    def run(self, payload: dict, ai_caller=None) -> str:
        loc = payload.get("location") or WEATHER_DEFAULT_LOCATION
        ai_name, backend = pick_task_ai(payload)
        ai = ai_caller or get_ai_provider(ai_name, backend)
        weather_data = fetch_weather_data(loc)
        if weather_data:
            prompt = f"以下是 {loc} 的实时天气数据，请用自然语言整理成简洁的天气播报：\n\n{weather_data}"
        else:
            prompt = f"请搜索并告诉我现在 {loc} 的天气情况，包括温度和天气现象。"
        return ai.call(prompt) or "⚠️ 天气信息获取失败。"


SKILL = WeatherSkill()
