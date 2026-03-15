# 使用 Python 3.12 轻量版
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖 (如有 CLI AI 工具需要另外安装)
RUN apt-get update && apt-get install -y \
    procps \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . .

# 暴露 Web UI 端口
EXPOSE 8000

# 默认启动守护进程 (可以通过环境变量覆盖模式)
CMD ["python", "email_daemon.py", "--mailbox", "126", "--ai", "claude"]
