#!/usr/bin/env python3
"""
创建中国股市定时简报任务
每天 09:00 和 16:00 发送中国股市最新行情及简评
"""

import os
import sys
import time
from datetime import datetime, timedelta
from tasks.scheduler import TaskScheduler

def get_next_time(hour, minute):
    """获取下一个指定时间点的时间戳"""
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= target:
        # 如果已经过了今天的时间点，则设为明天
        target += timedelta(days=1)
    return target.timestamp()

def create_stock_task(scheduler, task_name, hour, minute, lang="zh"):
    """创建中国股市简报定时任务"""
    
    # 使用 cron 表达式来指定每天固定时间
    cron_expr = f"{minute} {hour} * * *"
    
    # 任务主题
    subject = f"中国股市简报 ({hour:02d}:{minute:02d})"
    
    # 任务正文 - 指示 AI 获取最新股市信息
    body = f"""请提供中国股市的最新简报，包括：

1. **主要指数行情**
   - 上证指数（开盘、收盘、涨跌幅）
   - 深证成指（开盘、收盘、涨跌幅）
   - 创业板指（开盘、收盘、涨跌幅）

2. **市场简评**
   - 今日市场热点板块
   - 成交量情况
   - 北向资金流向
   - 重要消息面

3. **后市展望**
   - 技术面分析
   - 短期走势研判

请使用最新的市场数据，简明扼要地总结。
"""
    
    # 任务负载 - 指定使用搜索技能获取最新数据
    payload = {
        "task_type": "web_search",
        "query": "中国股市 今日行情 上证指数 深证成指 创业板指 最新",
        "ai_name": None  # 使用默认 AI
    }
    
    # 输出配置 - 仅发送邮件
    output = {
        "email": True,
        "archive": True,
        "archive_dir": "reports"
    }
    
    # 获取默认邮箱配置
    mailbox_name = "126"  # 默认使用 126 邮箱
    
    # 计算下一个执行时间
    next_run = datetime.fromtimestamp(get_next_time(hour, minute))
    print(f"创建任务：{subject}")
    print(f"Cron 表达式：{cron_expr}")
    print(f"下次执行时间：{next_run.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 添加任务
    success = scheduler.add_task(
        mailbox_name=mailbox_name,
        to="",  # 留空则使用配置中的默认地址
        subject=subject,
        body=body,
        schedule_cron=cron_expr,
        task_type="ai_job",
        task_payload=payload,
        output=output,
        lang=lang
    )
    
    if success:
        print(f"✅ 任务创建成功！\n")
    else:
        print(f"❌ 任务创建失败！\n")
    
    return success

def main():
    print("=" * 60)
    print("创建中国股市定时简报任务")
    print("=" * 60)
    print()
    
    # 初始化调度器
    scheduler = TaskScheduler()
    
    # 创建两个任务：09:00 和 16:00
    tasks_created = 0
    
    # 早上 09:00 - 开盘前简报
    print("【任务 1】早盘简报 (09:00)")
    print("-" * 40)
    if create_stock_task(scheduler, "早盘简报", 9, 0):
        tasks_created += 1
    
    # 下午 16:00 - 收盘后简报
    print("【任务 2】收盘简报 (16:00)")
    print("-" * 40)
    if create_stock_task(scheduler, "收盘简报", 16, 0):
        tasks_created += 1
    
    print("=" * 60)
    print(f"完成：成功创建 {tasks_created}/2 个任务")
    print()
    print("提示：")
    print("- 任务将在指定时间自动执行")
    print("- 可通过回复「查看任务」或「任务列表」查看当前任务")
    print("- 可通过「取消任务 ID:N」取消指定任务")
    print("=" * 60)

if __name__ == "__main__":
    main()
