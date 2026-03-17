from skills import BaseSkill
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider


class AiJobSkill(BaseSkill):
    name = "ai_job"
    description = "AI 自定义任务"
    description_ja = "AIカスタムタスク"
    description_en = "Custom AI job"
    keywords = ["ai任务", "ai job", "AIタスク", "自定义ai", "AI分析"]

    def run(self, payload: dict, ai_caller=None) -> str:
        prompt = payload.get("prompt") or ""
        if not prompt:
            return "⚠️ 请在 task_payload 中提供 prompt 字段。"
        ai_name, backend = pick_task_ai(payload)
        ai = ai_caller or get_ai_provider(ai_name, backend)
        return ai.call(prompt) or "AI 没有返回内容。"


SKILL = AiJobSkill()
