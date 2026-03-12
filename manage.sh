#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  邮件 AI 守护进程管理脚本
#  用法: bash manage.sh [start|stop|restart|status|log|install]
# ═══════════════════════════════════════════════════════════════

# ─── 固定路径 ──────────────────────────────────────────────────
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$INSTALL_DIR/venv/bin/python3"
SCRIPT="$INSTALL_DIR/email_daemon.py"
SERVICE_NAME="email-daemon"
LOG_FILE="$INSTALL_DIR/daemon.log"
PID_FILE="$INSTALL_DIR/daemon.pid"

# ─── 加载本地配置（不提交到 git）──────────────────────────────
ENV_FILE="$INSTALL_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=.env.example
    source "$ENV_FILE"
    set +a
else
    echo -e "\033[0;31m[ERROR]\033[0m 找不到配置文件: $ENV_FILE"
    echo "       请复制模板并填写真实信息: cp .env.example .env"
    exit 1
fi

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

    # 根据 MODE 决定是否加 --poll 参数
    EXTRA_ARGS=""
    if [ "${MODE:-idle}" = "poll" ]; then
        EXTRA_ARGS="--poll"
    fi

    # shellcheck disable=SC2086
    nohup "$VENV_PYTHON" "$SCRIPT" --mailbox "$MAILBOX" --ai "$AI" $EXTRA_ARGS \
        >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 1

    local pid=$(get_pid)
    if [ -n "$pid" ]; then
        info "服务已启动 (PID: $pid)"
        info "日志文件: $LOG_FILE"
        info "邮箱: $MAILBOX | AI: $AI | 模式: ${MODE:-idle}"
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

    # 使用 EnvironmentFile 直接读取 .env，切换邮箱只需修改 .env 后 restart
    # \$MAILBOX 和 \$AI 转义后由 systemd 在运行时从 EnvironmentFile 读取
    cat > /tmp/${SERVICE_NAME}.service << EOF
[Unit]
Description=Email AI Daemon
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV_PYTHON $SCRIPT --mailbox \$MAILBOX --ai \$AI
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
