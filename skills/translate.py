from skills import BaseSkill
from tasks.registry import pick_task_ai
from ai.providers import get_ai_provider


class TranslateSkill(BaseSkill):
    name = "translate"
    description = "将文本翻译为指定语言（通过 AI）"
    description_ja = "テキストを指定言語に翻訳（AI使用）"
    description_en = "Translate text to a specified language via AI"
    keywords = ["翻译", "translate", "翻訳", "번역", "translation"]

    def run(self, payload: dict, ai_caller=None) -> str:
        text = payload.get("text") or payload.get("prompt") or ""
        target = payload.get("target_lang") or payload.get("lang") or "English"
        if not text:
            return "⚠️ 请在 task_payload 中提供 text 字段。"
        ai_name, backend = pick_task_ai(payload)
        ai = get_ai_provider(ai_name, backend)
        prompt = f"请将以下文本翻译为{target}，仅返回译文，不加任何解释：\n\n{text}"
        return ai.call(prompt) or "⚠️ 翻译失败，AI 无响应。"


SKILL = TranslateSkill()
