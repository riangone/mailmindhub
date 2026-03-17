from skills import BaseSkill


class RemindSkill(BaseSkill):
    name = "remind"
    description = "发送提醒邮件（支持定时）"
    description_ja = "リマインダーメールを送信（スケジュール対応）"
    description_en = "Send a reminder email (supports scheduling)"
    keywords = ["提醒", "reminder", "remind", "リマインダー", "알림", "remindme"]

    def run(self, payload: dict, ai_caller=None) -> str:
        message = (
            payload.get("message")
            or payload.get("prompt")
            or payload.get("text")
            or ""
        )
        if not message:
            return "⚠️ 请在 task_payload 中提供 message 字段。"
        return f"⏰ 提醒：{message}"


SKILL = RemindSkill()
