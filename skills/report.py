from skills import BaseSkill
from tasks.registry import pick_task_ai, fetch_system_status, fetch_weather_data
from ai.providers import get_ai_provider
from utils.search import web_search, format_search_results
from core.config import SEARCH_RESULTS_COUNT


class ReportSkill(BaseSkill):
    name = "report"
    description = "综合日报生成"
    description_ja = "総合日報生成"
    description_en = "Composite daily report"
    keywords = ["日报", "report", "日報", "리포트", "周报", "汇总"]

    def run(self, payload: dict, ai_caller=None) -> str:
        report_text = ""
        if payload.get("include_system_status"):
            report_text += "【系统运行状态】\n" + fetch_system_status(payload) + "\n"
        for loc in payload.get("weather_locations") or []:
            weather_data = fetch_weather_data(loc)
            if weather_data:
                report_text += f"\n【天气：{loc}】\n{weather_data}\n"
        news_query = payload.get("news_query")
        if news_query:
            results = web_search(news_query, SEARCH_RESULTS_COUNT)
            if results:
                report_text += f"\n【新闻：{news_query}】\n{format_search_results(results)}\n"
        if payload.get("use_ai_summary", True):
            ai_name, backend = pick_task_ai(payload)
            ai = ai_caller or get_ai_provider(ai_name, backend)
            if report_text:
                prompt = (
                    "请将以下内容汇总成简洁日报，分点输出，重点突出。"
                    "⚠️ 核心要求：必须完整保留并显示所有新闻和网页检索结果中的原始链接（URL），严禁删减链接信息！"
                    f"\n\n内容如下：\n{report_text}"
                )
                return ai.call(prompt).strip() or report_text
            prompt_text = payload.get("prompt") or ""
            if prompt_text:
                return ai.call(prompt_text) or "没有可汇总的内容。"
        return report_text or "没有可汇总的内容。请在任务中指定 include_system_status、weather_locations 或 news_query。"


SKILL = ReportSkill()
