"""
skills/chain.py — チェーンスキル

エージェント設計の三層モデル（ツール層）に対応：
  複数のスキルを順番に実行し、前のステップの出力を次のステップに渡す。
  例: web_search → summarize → archive

使用例 (AI レスポンス JSON):
{
  "task_type": "chain",
  "task_payload": {
    "on_error": "stop",       // グローバルエラー設定: stop(デフォルト)|continue|retry
    "retry_count": 2,         // retry 時の最大試行回数（デフォルト: 2）
    "steps": [
      {
        "skill": "web_search",
        "payload": {"query": "OpenAI 最新動向"},
        "timeout": 30,        // ステップごとのタイムアウト(秒)
        "on_error": "retry",  // ステップ個別のエラー設定（グローバルを上書き）
        "condition": "prev_output != ''"  // 実行条件（省略時は常に実行）
      },
      {"skill": "summarize",  "payload": {"max_length": 500}},
      {"skill": "translate",  "payload": {"target_lang": "ja"}}
    ]
  }
}

各ステップの payload で "{prev_output}" を使うと前ステップの出力を参照できる。
payload に text/prompt が未設定の場合は自動的に前ステップの出力を渡す。

on_error の挙動:
  stop     — エラー発生時にチェーンを中断し、エラーメッセージを返す（デフォルト）
  continue — エラーをスキップして次ステップへ進む（last_output はエラーメッセージ）
  retry    — retry_count 回まで再試行し、失敗したら stop と同様に中断

condition の評価（単純な文字列比較のみ対応）:
  "prev_output != ''"  — 前ステップに出力がある場合のみ実行
  "prev_output contains ERROR"  — 前ステップ出力に "ERROR" が含まれる場合のみ実行
"""
import threading
from skills import BaseSkill
from utils.logger import log


def _evaluate_condition(condition: str, prev_output: str) -> bool:
    """単純な条件式を評価する。パース失敗時は True（実行する）を返す。"""
    cond = condition.strip()
    try:
        if "contains" in cond:
            parts = cond.split("contains", 1)
            value = parts[1].strip().strip("'\"")
            return value in prev_output
        if "not contains" in cond:
            parts = cond.split("not contains", 1)
            value = parts[1].strip().strip("'\"")
            return value not in prev_output
        if "!=" in cond:
            parts = cond.split("!=", 1)
            value = parts[1].strip().strip("'\"")
            return prev_output != value
        if "==" in cond:
            parts = cond.split("==", 1)
            value = parts[1].strip().strip("'\"")
            return prev_output == value
    except Exception:
        pass
    return True


def _run_with_timeout(skill, step_payload, ai_caller, timeout_sec):
    """タイムアウト付きでスキルを実行する。タイムアウト時は TimeoutError を送出。"""
    result_holder = [None]
    error_holder = [None]

    def target():
        try:
            result_holder[0] = skill.run(step_payload, ai_caller=ai_caller)
        except Exception as e:
            error_holder[0] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    if t.is_alive():
        raise TimeoutError(f"{timeout_sec}秒でタイムアウト")
    if error_holder[0]:
        raise error_holder[0]
    return result_holder[0]


class ChainSkill(BaseSkill):
    name = "chain"
    description = "複数スキルを順番に実行し、前ステップの出力を次ステップへ渡す"
    description_ja = "複数のスキルをチェーン実行し、前のステップの出力を次のステップに渡す"
    description_en = "Chain multiple skills sequentially, passing each step's output to the next"
    keywords = ["chain", "链式", "连续执行", "チェーン", "순서대로", "pipeline"]

    def run(self, payload: dict, ai_caller=None) -> str:
        from skills.loader import get_skill

        steps = payload.get("steps") or []
        if not steps:
            return "⚠️ chain skill には task_payload.steps にステップリストが必要です。"

        global_on_error = payload.get("on_error", "stop")   # stop | continue | retry
        global_retry_count = int(payload.get("retry_count", 2))
        last_output: str = payload.get("initial_input", "")
        results_summary = []

        for i, step in enumerate(steps, 1):
            skill_name = step.get("skill", "")
            step_payload = dict(step.get("payload") or {})
            step_on_error = step.get("on_error", global_on_error)
            step_timeout = step.get("timeout")          # 秒、None なら無制限
            step_condition = step.get("condition")      # 実行条件式

            # 実行条件の評価
            if step_condition and not _evaluate_condition(step_condition, last_output):
                log.info(f"[ChainSkill] ステップ {i}/{len(steps)}: {skill_name} — 条件不一致でスキップ")
                results_summary.append(f"Step {i} ({skill_name}): skipped")
                continue

            # {prev_output} プレースホルダーを展開
            for k, v in list(step_payload.items()):
                if isinstance(v, str):
                    step_payload[k] = v.replace("{prev_output}", last_output)

            # text / prompt が未設定なら前ステップ出力を自動注入
            if last_output and not step_payload.get("text") and not step_payload.get("prompt"):
                step_payload["text"] = last_output

            skill = get_skill(skill_name)
            if not skill:
                msg = f"⚠️ スキルが見つかりません: {skill_name}"
                log.warning(f"[ChainSkill] ステップ {i}: {msg}")
                if step_on_error == "stop":
                    return msg
                last_output = msg
                results_summary.append(f"Step {i} ({skill_name}): skill not found")
                continue

            # 実行（リトライ対応）
            max_attempts = global_retry_count if step_on_error == "retry" else 1
            last_error = None

            for attempt in range(1, max_attempts + 1):
                log.info(f"[ChainSkill] ステップ {i}/{len(steps)}: {skill_name}"
                         + (f" (試行 {attempt}/{max_attempts})" if max_attempts > 1 else ""))
                try:
                    if step_timeout:
                        result = _run_with_timeout(skill, step_payload, ai_caller, step_timeout)
                    else:
                        result = skill.run(step_payload, ai_caller=ai_caller)
                    last_output = result or ""
                    last_error = None
                    results_summary.append(f"Step {i} ({skill_name}): ok")
                    break
                except Exception as e:
                    last_error = e
                    log.warning(f"[ChainSkill] ステップ {i} ({skill_name}) 試行 {attempt} 失敗: {e}")

            if last_error is not None:
                msg = f"⚠️ ステップ {i} ({skill_name}) 実行エラー: {last_error}"
                log.error(f"[ChainSkill] {msg}")
                results_summary.append(f"Step {i} ({skill_name}): error — {last_error}")
                if step_on_error == "stop" or step_on_error == "retry":
                    summary = " | ".join(results_summary)
                    return f"{msg}\n\n実行サマリー: {summary}"
                # continue: エラーメッセージを next ステップへ渡して継続
                last_output = msg

        return last_output


SKILL = ChainSkill()
