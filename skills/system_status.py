from skills import BaseSkill
from tasks.registry import fetch_system_status


class SystemStatusSkill(BaseSkill):
    name = "system_status"
    description = "系统运行状态"
    description_ja = "システム稼働状況"
    description_en = "System status report"
    keywords = ["系统状态", "system status", "システム状態", "서버 상태", "服务器", "运行状态"]

    def run(self, payload: dict, ai_caller=None) -> str:
        return fetch_system_status(payload)


SKILL = SystemStatusSkill()
