"""
tasks/registry.py - 定时任务执行逻辑

增强版：集成通用 AI 执行框架和技能系统
"""
from typing import Optional, Dict, Any
from core.config import AI_BACKENDS, DEFAULT_TASK_AI, PROMPT_LANG, AI_CLI_TIMEOUT, AI_PROGRESS_INTERVAL
from ai.providers import get_ai_provider
from utils.logger import log


def pick_task_ai(task_payload: Optional[dict] = None):
    """选择一个可用的 AI 后端（CLI 优先，然后 API）"""
    task_payload = task_payload or {}
    ai_name = task_payload.get("ai_name") or DEFAULT_TASK_AI

    if ai_name and ai_name in AI_BACKENDS:
        return ai_name, AI_BACKENDS[ai_name]

    # 动态选择：CLI 优先
    import os, shutil
    cli_candidates = []
    api_candidates = []
    for name, b in AI_BACKENDS.items():
        if b.get("type") == "cli":
            cmd = b.get("cmd", "")
            if cmd and (shutil.which(cmd) or os.path.isfile(cmd)):
                cli_candidates.append(name)
        elif b.get("api_key"):
            api_candidates.append(name)

    candidates = cli_candidates + api_candidates
    ai_name = candidates[0] if candidates else list(AI_BACKENDS.keys())[0]
    return ai_name, AI_BACKENDS.get(ai_name)


def _handle_task_manage(payload: Optional[dict], subject: str, lang: str = "zh") -> str:
    """处理任务管理请求（查看/取消/暂停/恢复/删除）"""
    from tasks.scheduler import scheduler

    payload = payload or {}
    action = payload.get("action", "list")
    task_id = payload.get("task_id")
    filt = payload.get("filter", {})

    def _t(zh: str, ja: str, en: str, ko: str) -> str:
        return {"zh": zh, "ja": ja, "en": en, "ko": ko}.get(lang, zh)

    if action == "list":
        tasks = scheduler.list_tasks(
            status_filter=filt.get("status"),
            type_filter=filt.get("type"),
            subject_filter=filt.get("subject"),
        )
        if not tasks:
            return _t("当前没有活跃的定时任务。", "アクティブな定期タスクはありません。", "No active scheduled tasks.", "현재 활성화된 정기 작업이 없습니다.")

        header = _t(f"当前有 {len(tasks)} 个任务：", f"アクティブなタスク：{len(tasks)} 件", f"Active tasks: {len(tasks)}", f"활성 작업: {len(tasks)}개")
        rows = []
        for t in tasks:
            status_icon = {"pending": "⏳", "paused": "⏸️", "cancelled": "❌", "completed": "✅", "failed": "⚠️", "processing": "🔄"}.get(t.get("status", ""), "❓")
            next_run = ""
            if t.get("trigger_time"):
                from datetime import datetime
                try:
                    next_run = datetime.fromtimestamp(t["trigger_time"]).strftime("%Y-%m-%d %H:%M")
                except Exception:
                    pass
            repeat = ""
            if t.get("cron_expr"):
                repeat = f"cron:{t['cron_expr']}"
            elif t.get("interval_seconds"):
                secs = t["interval_seconds"]
                if secs >= 86400: repeat = f"每{secs//86400}天"
                elif secs >= 3600: repeat = f"每{secs//3600}时"
                elif secs >= 60: repeat = f"每{secs//60}分"
                else: repeat = f"每{secs}秒"
            rows.append(f"[ID:{t['id']}] {status_icon} {t.get('subject','')[:40]}\n  下次:{next_run or '-'}  {repeat}")

        hint = _t(
            "\n\n回复「取消任务 ID:N」「暂停任务 ID:N」「恢复任务 ID:N」「删除任务 ID:N」进行管理。",
            "\n\n「タスクキャンセル ID:N」「一時停止 ID:N」「再開 ID:N」「削除 ID:N」と返信して管理できます。",
            "\n\nReply 'cancel task ID:N', 'pause task ID:N', 'resume task ID:N', or 'delete task ID:N' to manage.",
            "\n\n'작업 취소 ID:N', '작업 일시정지 ID:N', '작업 재개 ID:N', '작업 삭제 ID:N'으로 관리할 수 있습니다."
        )
        return header + "\n\n" + "\n\n".join(rows) + hint

    if action in ("cancel", "pause", "resume", "delete"):
        if task_id:
            task_id = int(task_id)
            ok = {
                "cancel": scheduler.cancel_task,
                "pause":  scheduler.pause_task,
                "resume": scheduler.resume_task,
                "delete": scheduler.delete_task,
            }[action](task_id)
            verb = {
                "cancel": ("取消", "キャンセル", "cancelled", "취소됨"),
                "pause":  ("暂停", "一時停止", "paused", "일시정지됨"),
                "resume": ("恢复", "再開", "resumed", "재개됨"),
                "delete": ("删除", "削除", "deleted", "삭제됨"),
            }[action]
            if ok:
                return _t(f"✅ 已{verb[0]}任务 ID:{task_id}。", f"✅ タスク ID:{task_id} を{verb[1]}しました。", f"✅ Task ID:{task_id} {verb[2]}.", f"✅ 작업 ID:{task_id} {verb[3]}.")
            else:
                return _t(f"⚠️ 未找到可{verb[0]}的任务 ID:{task_id}。", f"⚠️ タスク ID:{task_id} は{verb[1]}できませんでした。", f"⚠️ Task ID:{task_id} could not be {verb[2]}.", f"⚠️ 작업 ID:{task_id} {verb[3]}할 수 없습니다.")
        else:
            if action == "cancel":
                count = scheduler.cancel_tasks_by_filter(filt.get("type"), filt.get("subject"))
                return _t(f"✅ 已取消 {count} 个匹配的任务。", f"✅ {count} 件のタスクをキャンセルしました。", f"✅ Cancelled {count} matching tasks.", f"✅ 일치하는 작업 {count}개를 취소했습니다.")
            return _t("⚠️ 批量操作仅支持取消。", "⚠️ 一括操作はキャンセルのみ対応です。", "⚠️ Batch operation only supports cancel.", "⚠️ 일괄 작업은 취소만 지원합니다.")

    return _t(f"⚠️ 未知操作：{action}", f"⚠️ 不明な操作：{action}", f"⚠️ Unknown action: {action}", f"⚠️ 알 수 없는 작업: {action}")


def execute_task_logic(task: Dict[str, Any], lang: str = "zh", progress_cb=None) -> tuple:
    """
    执行定时任务逻辑

    增强版：
    1. 集成通用 AI 执行框架
    2. 支持技能链式调用
    3. 自动执行模式（无需确认）
    """
    task_type = (task.get("type") or "email").lower()
    payload = task.get("payload") or {}
    subject = task.get("subject") or "定时任务结果"
    body = task.get("body") or ""

    def _t(zh: str, ja: str, en: str, ko: str) -> str:
        return {"zh": zh, "ja": ja, "en": en, "ko": ko}.get(lang, zh)

    # 1. 任务管理
    if task_type == "task_manage":
        body = _handle_task_manage(payload, subject, lang)
        subject = subject or _t("任务管理结果", "タスク管理結果", "Task management result", "작업 관리 결과")

    # 2. MCP 工具调用
    elif task_type == "mcp_call":
        from utils.mcp_client import call_mcp_tool, list_mcp_tools
        server = payload.get("server", "")
        tool = payload.get("tool", "")
        args = payload.get("args") or {}
        if tool == "__list__":
            body = list_mcp_tools(server)
        else:
            body = call_mcp_tool(server, tool, args)
        subject = subject or f"MCP: {server}/{tool}"

    # 3. email_manage 不支持定时执行
    elif task_type == "email_manage":
        body = _t("⚠️ email_manage 仅支持即时执行。", "⚠️ email_manage は即時実行のみ対応です。", "⚠️ email_manage only supports immediate execution.", "⚠️ email_manage 는 즉시 실행만 지원합니다.")

    # 4. 尝试执行已注册的技能
    from skills.loader import get_skill

    # 映射逻辑：将 news 映射到 news_briefing 以统一格式
    effective_task_type = task_type
    if task_type == "news":
        effective_task_type = "news_briefing"

    skill = get_skill(effective_task_type)
    if skill:
        log.info(f"🚀 执行技能: {effective_task_type}")
        # 确保 payload 包含必要的上下文
        if "prompt" not in payload and body:
            payload["prompt"] = body
        if "subject" not in payload and subject:
            payload["subject"] = subject

        # 验证 payload
        is_valid, error_msg = skill.validate_payload(payload)
        if not is_valid:
            body = f"⚠️ 参数验证失败: {error_msg}"
        else:
            body = skill.run(payload)
        subject = subject or f"Skill: {effective_task_type}"

    # 5. 其他所有任务：使用增强版 AI 执行框架
    else:
        ai_name, backend = pick_task_ai(payload)
        ai = get_ai_provider(ai_name, backend)

        # 构建 prompt：包含原始指令和上下文
        prompt = body or subject
        if task_type and task_type not in ("email", "ai_job"):
            # 如果指定了任务类型，告诉 AI 这是什么类型的任务
            prompt = f"请执行以下{task_type}任务：{prompt}"

        # 注入技能列表（让 AI 知道可用工具）
        from skills import get_all_skills_prompt
        skills_hint = get_all_skills_prompt(lang)
        if skills_hint:
            prompt = f"{prompt}\n\n{skills_hint}"

        # 添加强制执行指令
        exec_instruction = {
            "zh": """
【重要执行指令】
这是一个自动执行任务，请遵守：
1. 直接完成任务，不要询问确认
2. 如需写代码/文件，直接写入和执行
3. 如需搜索/查询，直接调用相应技能
4. 在最后给出简短总结
""",
            "ja": """
【重要実行指示】
これは自動実行タスクです。以下のルールに従ってください：
1. 確認せずに直接タスクを完了
2. コード/ファイルが必要な場合は直接作成・実行
3. 検索/問い合わせが必要な場合は該当スキルを直接呼び出し
4. 最後に簡単なまとめを出力
""",
            "en": """
[IMPORTANT EXECUTION INSTRUCTION]
This is an auto-execution task. Please follow these rules:
1. Complete the task directly without asking for confirmation
2. If code/files are needed, create and execute them directly
3. If search/query is needed, call the relevant skill directly
4. Output a brief summary at the end
""",
            "ko": """
[중요 실행 지침]
이것은 자동 실행 작업입니다. 다음 규칙을 따르세요:
1. 확인 없이 작업을 직접 완료
2. 코드/파일이 필요하면 직접 생성 및 실행
3. 검색/조회가 필요하면 관련 스킬을 직접 호출
4. 마지막에 간단한 요약 출력
""",
        }
        prompt = f"{prompt}\n\n{exec_instruction.get(lang, exec_instruction['zh'])}"

        # 调用 AI（使用 execute_task 模式，而非普通 call）
        log.info(f"⚡ 定时任务调用 AI: {ai_name} | 类型：{task_type}")
        
        # 检查 AI 是否有 execute_task 方法（CLI Provider 有）
        if hasattr(ai, 'execute_task'):
            # 使用任务执行模式（非交互式）
            is_cli = (backend or {}).get("type") == "cli"
            if is_cli and progress_cb and AI_PROGRESS_INTERVAL > 0:
                body = ai.execute_task(prompt, progress_cb=progress_cb, timeout=AI_CLI_TIMEOUT)
            else:
                body = ai.execute_task(prompt, timeout=AI_CLI_TIMEOUT)
        else:
            # API Provider 使用普通 call
            is_cli = (backend or {}).get("type") == "cli"
            if is_cli and progress_cb and AI_PROGRESS_INTERVAL > 0:
                body = ai.call(prompt, progress_cb=progress_cb, timeout=AI_CLI_TIMEOUT, progress_interval=AI_PROGRESS_INTERVAL)
            else:
                body = ai.call(prompt)
        
        body = body or _t("⚠️ AI 处理失败", "⚠️ AI 処理に失敗しました", "⚠️ AI processing failed", "⚠️ AI 처리 실패")
        subject = subject or f"AI: {task_type or 'task'}"

    return subject, body
