from skills import BaseSkill
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider


class CalculatorSkill(BaseSkill):
    name = "calculator"
    description = "数学计算和单位换算"
    description_ja = "数式計算・単位換算"
    description_en = "Mathematical calculation and unit conversion"
    keywords = ["计算", "calc", "calculate", "计算器", "算一下", "換算", "計算", "단위변환", "계산"]

    def run(self, payload: dict, ai_caller=None) -> str:
        expr = payload.get("expression") or payload.get("query") or payload.get("prompt") or ""
        if not expr:
            return "⚠️ Please provide an expression in task_payload.query"
        ai_name, backend = pick_task_ai(payload)
        ai = get_ai_provider(ai_name, backend)
        prompt = f"请计算以下表达式或回答数学/单位换算问题，直接给出结果和简短说明：\n\n{expr}"
        return ai.call(prompt) or "⚠️ 计算失败。"


SKILL = CalculatorSkill()
