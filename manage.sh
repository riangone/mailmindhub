#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  邮件 AI 守护进程管理脚本
#  用法: bash manage.sh [setup|start|stop|restart|status|log|install]
# ═══════════════════════════════════════════════════════════════

# ─── 固定路径 ──────────────────────────────────────────────────
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$INSTALL_DIR/venv/bin/python3"
VENV_PIP="$INSTALL_DIR/venv/bin/pip"
SCRIPT="$INSTALL_DIR/email_daemon.py"
SERVICE_NAME="email-daemon"
LOG_FILE="$INSTALL_DIR/daemon.log"
PID_FILE="$INSTALL_DIR/daemon.pid"
ENV_FILE="$INSTALL_DIR/.env"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }
heading() { echo -e "\n${BLUE}══ $* ══${NC}"; }

# ─── 加载 .env（仅需要配置的命令才调用）──────────────────────
load_env() {
    if [ -f "$ENV_FILE" ]; then
        set -a
        # shellcheck source=.env.example
        source "$ENV_FILE"
        set +a
    else
        error "找不到配置文件: $ENV_FILE"
        echo "       首次使用请运行: bash manage.sh setup"
        exit 1
    fi
}

# ─── 确保 venv 存在，不存在则自动创建 ─────────────────────────
ensure_venv() {
    if [ ! -f "$VENV_PYTHON" ]; then
        info "未检测到虚拟环境，正在自动创建..."
        python3 -m venv "$INSTALL_DIR/venv" || {
            error "创建虚拟环境失败，请确认已安装 python3-venv"
            exit 1
        }
        info "正在安装依赖..."
        "$VENV_PIP" install --quiet -r "$INSTALL_DIR/requirements.txt" || {
            error "依赖安装失败，请检查网络连接或 requirements.txt"
            exit 1
        }
        info "依赖安装完成"
    fi
}

# ─── Mozilla Autoconfig 查询（返回 imap_host|imap_port|smtp_host|smtp_port|smtp_ssl）
autoconfig_lookup() {
    local domain="$1"
    local urls=(
        "https://autoconfig.thunderbird.net/v1.1/${domain}"
        "https://autoconfig.${domain}/mail/config-v1.1.xml"
        "https://${domain}/.well-known/autoconfig/mail/config-v1.1.xml"
    )
    local xml=""
    for url in "${urls[@]}"; do
        xml=$(curl -fsS --max-time 6 "$url" 2>/dev/null) && \
        echo "$xml" | grep -q "<incomingServer" && break || xml=""
    done
    [ -z "$xml" ] && return 1

    python3 - <<PYEOF
import sys, xml.etree.ElementTree as ET
try:
    root = ET.fromstring("""${xml//\"/\\\"}""")
    imap = root.find('.//incomingServer[@type="imap"]')
    smtp = root.find('.//outgoingServer[@type="smtp"]')
    if imap is None or smtp is None:
        sys.exit(1)
    imap_host = imap.findtext('hostname', '').strip()
    imap_port = imap.findtext('port', '993').strip()
    smtp_host = smtp.findtext('hostname', '').strip()
    smtp_port = smtp.findtext('port', '465').strip()
    ssl_type  = (smtp.findtext('socketType') or '').upper()
    smtp_ssl  = 'true' if ssl_type == 'SSL' else 'false'
    if imap_host and smtp_host:
        print(f'{imap_host}|{imap_port}|{smtp_host}|{smtp_port}|{smtp_ssl}')
    else:
        sys.exit(1)
except Exception:
    sys.exit(1)
PYEOF
}

# ─── 交互式配置向导 ───────────────────────────────────────────
do_setup() {
    heading "MailMind 一键配置向导"
    echo ""
    echo "本向导将引导您完成所有配置，结束后自动生成 .env 并安装依赖。"
    echo ""

    # ── 1. 输入邮箱地址，自动判断类型 ───────────────────────
    echo -e "${CYAN}【1/4】邮箱地址：${NC}"
    read -rp "邮箱地址: " MAIL_ADDRESS
    [ -z "$MAIL_ADDRESS" ] && { error "邮箱地址不能为空"; exit 1; }

    DOMAIN=$(echo "$MAIL_ADDRESS" | awk -F'@' '{print tolower($2)}')
    OUTLOOK_CLIENT_ID=""
    CUSTOM_IMAP_SERVER="" CUSTOM_IMAP_PORT="" CUSTOM_SMTP_SERVER="" CUSTOM_SMTP_PORT="" CUSTOM_SMTP_SSL=""

    case "$DOMAIN" in
        gmail.com)
            echo ""
            echo "检测到 Gmail，选择认证方式："
            echo "  1) 应用专用密码（简单，在 myaccount.google.com/apppasswords 生成）"
            echo "  2) OAuth（推荐，需 Google Cloud 项目）"
            read -rp "请输入数字 [1-2]: " gmail_choice
            MAILBOX="gmail"; MAIL_ENV_PREFIX="MAIL_GMAIL"
            if [ "$gmail_choice" = "2" ]; then
                AUTH_TYPE="oauth_google"
            else
                AUTH_TYPE="app_password"
            fi
            ;;
        outlook.com|hotmail.com|live.com|live.cn|msn.com)
            info "检测到 Outlook / Hotmail，使用 OAuth 认证"
            MAILBOX="outlook"; MAIL_ENV_PREFIX="MAIL_OUTLOOK"; AUTH_TYPE="oauth_microsoft"
            read -rp "Azure App Client ID: " OUTLOOK_CLIENT_ID
            [ -z "$OUTLOOK_CLIENT_ID" ] && { error "Client ID 不能为空"; exit 1; }
            ;;
        126.com)
            info "检测到 126 邮箱"
            MAILBOX="126"; MAIL_ENV_PREFIX="MAIL_126"; AUTH_TYPE="password"
            ;;
        163.com|yeah.net)
            info "检测到 163 邮箱"
            MAILBOX="163"; MAIL_ENV_PREFIX="MAIL_163"; AUTH_TYPE="password"
            ;;
        qq.com|foxmail.com)
            info "检测到 QQ 邮箱"
            MAILBOX="qq"; MAIL_ENV_PREFIX="MAIL_QQ"; AUTH_TYPE="password"
            ;;
        icloud.com|me.com|mac.com)
            info "检测到 iCloud 邮箱"
            MAILBOX="icloud"; MAIL_ENV_PREFIX="MAIL_ICLOUD"; AUTH_TYPE="password"
            ;;
        protonmail.com|proton.me|pm.me)
            info "检测到 Proton Mail（需要先运行 Proton Mail Bridge）"
            MAILBOX="proton"; MAIL_ENV_PREFIX="MAIL_PROTON"; AUTH_TYPE="password"
            ;;
        *)
            MAILBOX="custom"; MAIL_ENV_PREFIX="MAIL_CUSTOM"; AUTH_TYPE="password"
            info "正在查询 $DOMAIN 的邮件服务器配置..."
            _ac=$(autoconfig_lookup "$DOMAIN")
            if [ -n "$_ac" ]; then
                IFS='|' read -r CUSTOM_IMAP_SERVER CUSTOM_IMAP_PORT \
                                 CUSTOM_SMTP_SERVER CUSTOM_SMTP_PORT CUSTOM_SMTP_SSL <<< "$_ac"
                info "自动获取成功："
                echo "    IMAP  $CUSTOM_IMAP_SERVER:$CUSTOM_IMAP_PORT"
                echo "    SMTP  $CUSTOM_SMTP_SERVER:$CUSTOM_SMTP_PORT  SSL=$CUSTOM_SMTP_SSL"
                read -rp "使用以上配置？[Y/n]: " _confirm
                if [[ "$_confirm" =~ ^[Nn] ]]; then
                    _ac=""   # 用户拒绝，走手动流程
                fi
            fi
            if [ -z "$_ac" ]; then
                warn "未能自动获取配置，请手动填写服务器信息"
                echo ""
                read -rp "IMAP 服务器（如 imap.example.com）: " CUSTOM_IMAP_SERVER
                [ -z "$CUSTOM_IMAP_SERVER" ] && { error "IMAP 服务器不能为空"; exit 1; }
                read -rp "IMAP 端口 [993]: " CUSTOM_IMAP_PORT
                CUSTOM_IMAP_PORT="${CUSTOM_IMAP_PORT:-993}"
                read -rp "SMTP 服务器（如 smtp.example.com）: " CUSTOM_SMTP_SERVER
                [ -z "$CUSTOM_SMTP_SERVER" ] && { error "SMTP 服务器不能为空"; exit 1; }
                read -rp "SMTP 端口 [465]: " CUSTOM_SMTP_PORT
                CUSTOM_SMTP_PORT="${CUSTOM_SMTP_PORT:-465}"
                read -rp "SMTP 使用 SSL？[Y/n]: " _ssl
                [[ "$_ssl" =~ ^[Nn] ]] && CUSTOM_SMTP_SSL="false" || CUSTOM_SMTP_SSL="true"
            fi
            ;;
    esac

    # ── 2. 授权码 / 密码 ──────────────────────────────────────
    MAIL_PASSWORD=""
    if [ "$AUTH_TYPE" = "password" ]; then
        echo ""
        echo -e "${CYAN}【2/4】授权码 / 密码：${NC}"
        echo "（提示：需要邮箱授权码，不是登录密码。在邮箱设置 → POP3/IMAP 开启服务时获取）"
        read -rp "授权码: " MAIL_PASSWORD
        [ -z "$MAIL_PASSWORD" ] && { error "授权码不能为空"; exit 1; }
    elif [ "$AUTH_TYPE" = "app_password" ]; then
        echo ""
        echo -e "${CYAN}【2/4】应用专用密码：${NC}"
        read -rp "应用专用密码（格式：xxxx xxxx xxxx xxxx）: " MAIL_PASSWORD
        [ -z "$MAIL_PASSWORD" ] && { error "应用专用密码不能为空"; exit 1; }
    else
        info "【2/4】OAuth 模式无需密码，跳过"
    fi

    # ── 3. 白名单 ─────────────────────────────────────────────
    echo ""
    echo -e "${CYAN}【3/4】发件人白名单（只处理来自这些地址的邮件）：${NC}"
    echo "  直接回车 = 仅允许自己的地址: $MAIL_ADDRESS"
    read -rp "白名单（多个地址用英文逗号分隔）: " MAIL_ALLOWED_INPUT
    MAIL_ALLOWED="${MAIL_ALLOWED_INPUT:-$MAIL_ADDRESS}"

    # ── 4. 选择 AI 后端 + API Key ────────────────────────────
    echo ""
    echo -e "${CYAN}【4/4】选择 AI 后端：${NC}"
    echo "  1) DeepSeek API（推荐，性价比高）"
    echo "  2) OpenAI API（gpt-4o）"
    echo "  3) Anthropic API（claude-sonnet）"
    echo "  4) Gemini API"
    echo "  5) claude CLI（需本地已安装 claude 命令）"
    echo "  6) gemini CLI（需本地已安装 gemini 命令）"
    echo ""
    read -rp "请输入数字 [1-6]: " AI_CHOICE

    case "$AI_CHOICE" in
        1) AI_BACKEND="deepseek";   AI_KEY_VAR="DEEPSEEK_API_KEY";  AI_TYPE="api" ;;
        2) AI_BACKEND="openai";     AI_KEY_VAR="OPENAI_API_KEY";    AI_TYPE="api" ;;
        3) AI_BACKEND="anthropic";  AI_KEY_VAR="ANTHROPIC_API_KEY"; AI_TYPE="api" ;;
        4) AI_BACKEND="gemini-api"; AI_KEY_VAR="GEMINI_API_KEY";    AI_TYPE="api" ;;
        5) AI_BACKEND="claude";     AI_KEY_VAR="";                  AI_TYPE="cli" ;;
        6) AI_BACKEND="gemini";     AI_KEY_VAR="";                  AI_TYPE="cli" ;;
        *) error "无效选项"; exit 1 ;;
    esac

    AI_KEY_VALUE=""
    if [ "$AI_TYPE" = "api" ]; then
        read -rp "$AI_KEY_VAR: " AI_KEY_VALUE
        [ -z "$AI_KEY_VALUE" ] && { error "API Key 不能为空"; exit 1; }
    fi

    # ── 创建 venv + 安装依赖 ──────────────────────────────────
    echo ""
    heading "安装 Python 依赖"
    ensure_venv

    if [ "$AUTH_TYPE" = "oauth_google" ]; then
        info "安装 Gmail OAuth 依赖..."
        "$VENV_PIP" install --quiet google-auth google-auth-oauthlib google-auth-httplib2 \
            || warn "OAuth 依赖安装失败，请手动运行: pip install google-auth google-auth-oauthlib google-auth-httplib2"
    elif [ "$AUTH_TYPE" = "oauth_microsoft" ]; then
        info "安装 Outlook OAuth 依赖..."
        "$VENV_PIP" install --quiet msal \
            || warn "msal 安装失败，请手动运行: pip install msal"
    fi

    # ── 写入 .env ─────────────────────────────────────────────
    echo ""
    heading "生成配置文件"

    {
        echo "# 由 bash manage.sh setup 自动生成"
        echo "MAILBOX=\"$MAILBOX\""
        echo "AI=\"$AI_BACKEND\""
        echo "MODE=\"idle\""
        echo "POLL_INTERVAL=\"60\""
        echo ""
        echo "# 邮箱配置"
        echo "${MAIL_ENV_PREFIX}_ADDRESS=\"$MAIL_ADDRESS\""
        [ -n "$MAIL_PASSWORD" ]          && echo "${MAIL_ENV_PREFIX}_PASSWORD=\"$MAIL_PASSWORD\""
        echo "${MAIL_ENV_PREFIX}_ALLOWED=\"$MAIL_ALLOWED\""
        [ "$AUTH_TYPE" = "app_password" ] && echo "MAIL_GMAIL_AUTH=\"password\""
        [ -n "$OUTLOOK_CLIENT_ID" ]       && echo "OUTLOOK_CLIENT_ID=\"$OUTLOOK_CLIENT_ID\""
        if [ -n "$CUSTOM_IMAP_SERVER" ]; then
            echo "MAIL_CUSTOM_IMAP_SERVER=\"$CUSTOM_IMAP_SERVER\""
            echo "MAIL_CUSTOM_IMAP_PORT=\"$CUSTOM_IMAP_PORT\""
            echo "MAIL_CUSTOM_SMTP_SERVER=\"$CUSTOM_SMTP_SERVER\""
            echo "MAIL_CUSTOM_SMTP_PORT=\"$CUSTOM_SMTP_PORT\""
            echo "MAIL_CUSTOM_SMTP_SSL=\"$CUSTOM_SMTP_SSL\""
        fi
        if [ -n "$AI_KEY_VALUE" ]; then
            echo ""
            echo "# AI 配置"
            echo "${AI_KEY_VAR}=\"$AI_KEY_VALUE\""
        fi
    } > "$ENV_FILE"

    info ".env 已写入: $ENV_FILE"

    # ── 下一步提示 ────────────────────────────────────────────
    echo ""
    heading "配置完成！"

    if [ "$AUTH_TYPE" = "oauth_google" ]; then
        warn "Gmail OAuth 还需额外步骤："
        echo "  1. 在 Google Cloud Console 创建项目，启用 Gmail API"
        echo "  2. 下载 OAuth 凭据文件，重命名为 credentials_gmail.json 放到本目录"
        echo "  3. 运行授权（仅首次）: $VENV_PYTHON $SCRIPT --mailbox gmail --auth"
        echo "  4. 授权完成后: bash manage.sh start"
    elif [ "$AUTH_TYPE" = "oauth_microsoft" ]; then
        warn "Outlook OAuth 还需额外步骤："
        echo "  1. 运行授权（按终端提示在浏览器输入设备码）:"
        echo "     $VENV_PYTHON $SCRIPT --mailbox outlook --auth"
        echo "  2. 授权完成后: bash manage.sh start"
    else
        echo ""
        echo "  启动服务:   bash manage.sh start"
        echo "  查看状态:   bash manage.sh status"
        echo "  查看日志:   bash manage.sh log"
    fi
    echo ""
}

get_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
        fi
    fi
}

do_start() {
    load_env
    heading "启动服务"
    local pid
    pid=$(get_pid)
    if [ -n "$pid" ]; then
        warn "服务已在运行中 (PID: $pid)"
        return 1
    fi

    if [ -z "$MAILBOX" ]; then
        error "未配置邮箱（MAILBOX 为空）"
        echo "       请先运行: bash manage.sh setup"
        echo "       或打开 Web UI 配置邮箱后重试"
        exit 1
    fi
    if [ -z "$AI" ]; then
        error "未配置 AI（AI 为空）"
        echo "       请先运行: bash manage.sh setup"
        exit 1
    fi

    ensure_venv

    EXTRA_ARGS=""
    if [ "${MODE:-idle}" = "poll" ]; then
        EXTRA_ARGS="--poll"
    fi

    # shellcheck disable=SC2086
    nohup "$VENV_PYTHON" "$SCRIPT" --mailbox "$MAILBOX" --ai "$AI" $EXTRA_ARGS \
        >> "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    sleep 1

    pid=$(get_pid)
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
    load_env
    heading "停止服务"
    local pid
    pid=$(get_pid)
    if [ -z "$pid" ]; then
        warn "服务未在运行"
        return 0
    fi
    kill "$pid"
    rm -f "$PID_FILE"
    info "服务已停止 (PID: $pid)"
}

do_restart() {
    load_env
    heading "重启服务"
    do_stop
    sleep 2
    do_start
}

do_status() {
    load_env
    heading "服务状态"
    local pid
    pid=$(get_pid)
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
    load_env
    heading "安装为 systemd 服务"

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
    load_env
    heading "卸载 systemd 服务"
    sudo systemctl stop "$SERVICE_NAME" 2>/dev/null
    sudo systemctl disable "$SERVICE_NAME" 2>/dev/null
    sudo rm -f /etc/systemd/system/${SERVICE_NAME}.service
    sudo systemctl daemon-reload
    info "systemd 服务已卸载"
}

do_webui() {
    ensure_venv
    local host="${2:-0.0.0.0}"
    local port="${3:-8000}"
    # 检查 fastapi 是否已安装
    if ! "$VENV_PYTHON" -c "import fastapi" 2>/dev/null; then
        info "正在安装 Web UI 依赖..."
        "$VENV_PIP" install "fastapi>=0.110.0" "uvicorn[standard]>=0.29.0" "jinja2>=3.1.0" "python-multipart>=0.0.9" --quiet || {
            error "依赖安装失败"
            exit 1
        }
    fi
    heading "启动 Web UI"
    info "地址: http://${host}:${port}"
    info "按 Ctrl+C 停止"
    cd "$INSTALL_DIR"
    exec "$VENV_PYTHON" -m webui.server --host "$host" --port "$port"
}

# ─── 入口 ──────────────────────────────────────────────────────
case "$1" in
    setup)     do_setup ;;
    start)     do_start ;;
    stop)      do_stop ;;
    restart)   do_restart ;;
    status)    do_status ;;
    log)       do_log ;;
    webui)     do_webui "$@" ;;
    install)   do_install ;;
    uninstall) do_uninstall ;;
    *)
        echo ""
        echo "用法: bash manage.sh <命令>"
        echo ""
        echo "  setup      一键配置向导（首次使用从这里开始）"
        echo "  start      启动守护进程（后台运行）"
        echo "  stop       停止守护进程"
        echo "  restart    重启守护进程"
        echo "  status     查看运行状态和最近日志"
        echo "  log        实时查看日志"
        echo "  webui      启动 Web 管理界面 [host] [port]（默认 0.0.0.0:8000）"
        echo "  install    安装为 systemd 服务（开机自启）"
        echo "  uninstall  卸载 systemd 服务"
        echo ""
        ;;
esac
