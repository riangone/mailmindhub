from skills import BaseSkill
from utils.search import web_search, format_search_results


class WebSearchSkill(BaseSkill):
    name = "web_search"
    description = "网页搜索"
    description_ja = "ウェブ検索"
    description_en = "Web search"
    keywords = ["搜索", "检索", "search", "検索", "검색", "查找"]

    def run(self, payload: dict, ai_caller=None) -> str:
        q = payload.get("query") or ""
        if not q:
            return "⚠️ 请在 task_payload 中提供 query 字段。"
        results = web_search(q, payload.get("count", 5), payload.get("engine"))
        return format_search_results(results) if results else "没有找到结果。"


SKILL = WebSearchSkill()
