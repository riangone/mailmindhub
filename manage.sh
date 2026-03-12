#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  邮件 AI 守护进程管理脚本
#  用法: bash manage.sh [start|stop|restart|status|log|install]
# ═══════════════════════════════════════════════════════════════

# ─── 配置区（根据实际情况修改）────────────────────────────────
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$INSTALL_DIR/venv/bin/python3"
SCRIPT="$INSTALL_DIR/email_daemon.py"
SERVICE_NAME="email-daemon"
LOG_FILE="$INSTALL_DIR/daemon.log"
PID_FILE="$INSTALL_DIR/daemon.pid"

MAILBOX="126"          # 邮箱: 126 / 163 / qq / gmail / outlook
AI="codex"            # AI:   claude / codex / gemini / anthropic / openai / gemini-api / qwen-api
POLL_INTERVAL="60"     # 轮询间隔（秒）

# ─── 邮箱环境变量（填写你的真实信息）──────────────────────────
export MAIL_126_ADDRESS="your@126.com"
export MAIL_126_PASSWORD="your-auth-code"
export MAIL_126_ALLOWED="your@126.com"

# export MAIL_163_ADDRESS="your@163.com"
# export MAIL_163_PASSWORD="your-auth-code"
# export MAIL_163_ALLOWED="your@163.com"

# export MAIL_QQ_ADDRESS="your@qq.com"
# export MAIL_QQ_PASSWORD="your-auth-code"
# export MAIL_QQ_ALLOWED="your@qq.com"

# Gmail OAuth（推荐）：
#   1. 在 Google Cloud Console 创建项目并启用 Gmail API
#   2. 创建 OAuth 凭据（桌面应用），下载为 credentials_gmail.json 放到本目录
#   3. 首次运行: python3 email_daemon.py --mailbox gmail --auth  （按提示授权）
# export MAIL_GMAIL_ADDRESS="your@gmail.com"
# export MAIL_GMAIL_ALLOWED="your@gmail.com"
# Gmail 应用专用密码（简单方式，需关闭两步验证或生成应用密码）：
#   修改 email_daemon.py 中 gmail 的 "auth": "password"，再填写下面两行
# export MAIL_GMAIL_ADDRESS="your@gmail.com"
# export MAIL_GMAIL_PASSWORD="xxxx xxxx xxxx xxxx"
# export MAIL_GMAIL_ALLOWED="your@gmail.com"

# Outlook OAuth：
#   1. 在 Azure Portal 注册应用，获取 Client ID
#   2. 首次运行: python3 email_daemon.py --mailbox outlook --auth  （设备码授权）
# export MAIL_OUTLOOK_ADDRESS="your@outlook.com"
# export OUTLOOK_CLIENT_ID="your-azure-app-client-id"
# export MAIL_OUTLOOK_ALLOWED="your@outlook.com"

# ─── AI 环境变量（按需填写）────────────────────────────────────
# export ANTHROPIC_API_KEY="sk-ant-xxx"
# export OPENAI_API_KEY="sk-xxx"
# export GEMINI_API_KEY="AIzaxxx"
# export QWEN_API_KEY="sk-xxx"

export POLL_INTERVAL="$POLL_INTERVAL"

# ═══════════════════════════════════════════════════════════════

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
heading() { echo -e "\n${BLUE}══ $* ══${NC}"; }

get_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
        fi
    fi
}

do_start() {
    heading "启动服务"
    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        warn "服务已在运行中 (PID: $pid)"
        return 1
    fi

    if [ ! -f "$VENV_PYTHON" ]; then
        error "找不到虚拟环境: $VENV_PYTHON"
        error "请先运行: python3 -m venv venv && venv/bin/pip install requests"
        return 1
    fi

    nohup "$VENV_PYTHON" "$SCRIPT" --mailbox "$MAILBOX" --ai "$AI" \
        >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 1

    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        info "服务已启动 (PID: $pid)"
        info "日志文件: $LOG_FILE"
        info "邮箱: $MAILBOX | AI: $AI | 轮询: ${POLL_INTERVAL}s"
    else
        error "启动失败，查看日志: tail -f $LOG_FILE"
        return 1
    fi
}

do_stop() {
    heading "停止服务"
    local pid=$(get_pid)
    if [ -z "$pid" ]; then
        warn "服务未在运行"
        return 0
    fi
    kill "$pid"
    rm -f "$PID_FILE"
    info "服务已停止 (PID: $pid)"
}

do_restart() {
    heading "重启服务"
    do_stop
    sleep 2
    do_start
}

do_status() {
    heading "服务状态"
    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        info "状态: ${GREEN}运行中${NC} (PID: $pid)"
        info "邮箱: $MAILBOX | AI: $AI"
        info "日志: $LOG_FILE"
        echo ""
        echo "最近 5 条日志:"
        tail -5 "$LOG_FILE" 2>/dev/null || echo "（暂无日志）"
    else
        warn "状态: 未运行"
    fi
}

do_log() {
    heading "实时日志 (Ctrl+C 退出)"
    tail -f "$LOG_FILE"
}

do_install() {
    heading "安装为 systemd 服务"

    # 生成 service 文件（把环境变量内联进去）
    cat > /tmp/${SERVICE_NAME}.service << EOF
[Unit]
Description=Email AI Daemon
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$INSTALL_DIR
Environment=MAIL_126_ADDRESS=$MAIL_126_ADDRESS
Environment=MAIL_126_PASSWORD=$MAIL_126_PASSWORD
Environment=MAIL_126_ALLOWED=$MAIL_126_ALLOWED
Environment=POLL_INTERVAL=$POLL_INTERVAL
ExecStart=$VENV_PYTHON $SCRIPT --mailbox $MAILBOX --ai $AI
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    sudo cp /tmp/${SERVICE_NAME}.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable "$SERVICE_NAME"
    sudo systemctl start "$SERVICE_NAME"
    sleep 2
    sudo systemctl status "$SERVICE_NAME" --no-pager
    info "systemd 服务已安装"
    info "查看日志: sudo journalctl -u $SERVICE_NAME -f"
}

do_uninstall() {
    heading "卸载 systemd 服务"
    sudo systemctl stop "$SERVICE_NAME" 2>/dev/null
    sudo systemctl disable "$SERVICE_NAME" 2>/dev/null
    sudo rm -f /etc/systemd/system/${SERVICE_NAME}.service
    sudo systemctl daemon-reload
    info "systemd 服务已卸载"
}

# ─── 入口 ──────────────────────────────────────────────────────
case "$1" in
    start)     do_start ;;
    stop)      do_stop ;;
    restart)   do_restart ;;
    status)    do_status ;;
    log)       do_log ;;
    install)   do_install ;;
    uninstall) do_uninstall ;;
    *)
        echo ""
        echo "用法: bash manage.sh <命令>"
        echo ""
        echo "  start      启动守护进程（后台运行）"
        echo "  stop       停止守护进程"
        echo "  restart    重启守护进程"
        echo "  status     查看运行状态和最近日志"
        echo "  log        实时查看日志"
        echo "  install    安装为 systemd 服务（开机自启）"
        echo "  uninstall  卸载 systemd 服务"
        echo ""
        ;;
esac
