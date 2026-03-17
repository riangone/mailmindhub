from skills import BaseSkill
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider


class SummarizeSkill(BaseSkill):
    name = "summarize"
    description = "对文本或邮件内容进行摘要精简"
    description_ja = "テキスト・メール内容を要約"
    description_en = "Summarize text or email content"
    keywords = ["摘要", "总结", "summarize", "summary", "要約", "まとめ", "요약", "정리"]

    def run(self, payload: dict, ai_caller=None) -> str:
        text = payload.get("text") or payload.get("prompt") or ""
        lang = payload.get("lang") or ""
        if not text:
            return "⚠️ 请在 task_payload 中提供 text 字段。"
        ai_name, backend = pick_task_ai(payload)
        ai = get_ai_provider(ai_name, backend)
        lang_hint = f"，用{lang}回答" if lang else ""
        prompt = f"请对以下内容进行简洁摘要，分要点列出关键信息{lang_hint}：\n\n{text}"
        return ai.call(prompt) or "⚠️ 摘要失败，AI 无响应。"


SKILL = SummarizeSkill()
