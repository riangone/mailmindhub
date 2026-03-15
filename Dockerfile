FROM python:3.12-slim

WORKDIR /app

# System deps (procps for ps/kill; add more if needed for CLI AI tools)
RUN apt-get update && apt-get install -y \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies into system Python (no venv needed in container)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code (runtime files are bind-mounted at run time)
COPY . .

# WebUI port
EXPOSE 7000

# Default: start daemon using MAILBOX and AI from env (set in .env / env_file)
CMD ["sh", "-c", "python email_daemon.py --mailbox ${MAILBOX:-126} --ai ${AI:-deepseek}"]
