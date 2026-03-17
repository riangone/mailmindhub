from skills import BaseSkill
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider
from utils.search import web_search, format_search_results
from core.config import SEARCH_RESULTS_COUNT


class NewsSkill(BaseSkill):
    name = "news"
    description = "新闻搜索与摘要"
    description_ja = "ニュース検索と要約"
    description_en = "News search and summarization"
    keywords = ["新闻", "新闻摘要", "news", "ニュース", "뉴스", "资讯"]

    def run(self, payload: dict, ai_caller=None) -> str:
        ai_name, backend = pick_task_ai(payload)
        ai = ai_caller or get_ai_provider(ai_name, backend)
        q = payload.get("query") or "最新的新闻"
        if backend.get("native_web_search"):
            prompt = f"请搜索并总结关于以下主题的最新新闻：{q}。重要提示：必须在回复中包含每条新闻的原始链接（URL），不要删减链接信息。"
            return ai.call(prompt) or "⚠️ 新闻获取失败。"
        results = web_search(q, SEARCH_RESULTS_COUNT)
        if results:
            search_ctx = format_search_results(results)
            prompt = f"以下是关于「{q}」的网络搜索结果，请将其整理为新闻摘要，按重要性排列，保留并完整显示每条的原始链接（URL）。\n\n{search_ctx}"
        else:
            prompt = f"请搜索并总结关于以下主题的最新新闻：{q}。重要提示：必须在回复中包含每条新闻的原始链接（URL），不要删减链接信息。"
        return ai.call(prompt) or "⚠️ 新闻获取失败。"


SKILL = NewsSkill()
