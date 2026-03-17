from skills import BaseSkill
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider


class CodeReviewSkill(BaseSkill):
    name = "code_review"
    description = "对代码进行专业审查，指出问题并给出改进建议"
    description_ja = "コードの専門的なレビューと改善提案"
    description_en = "Professionally review code and suggest improvements"
    keywords = ["代码审查", "code review", "コードレビュー", "코드 리뷰", "review code", "审查代码", "代码检查"]

    def run(self, payload: dict, ai_caller=None) -> str:
        code = payload.get("code") or payload.get("text") or payload.get("prompt") or ""
        lang = payload.get("lang") or ""
        if not code:
            return "⚠️ 请在 task_payload 中提供 code 字段。"
        ai_name, backend = pick_task_ai(payload)
        ai = get_ai_provider(ai_name, backend)
        lang_hint = f"编程语言：{lang}\n" if lang else ""
        prompt = (
            f"请对以下代码进行专业代码审查，指出潜在 Bug、安全隐患、性能问题，并给出具体改进建议：\n"
            f"{lang_hint}\n```\n{code}\n```"
        )
        return ai.call(prompt) or "⚠️ 代码审查失败，AI 无响应。"


SKILL = CodeReviewSkill()
