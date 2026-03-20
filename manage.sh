#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  MailMindHub 统一管理脚本
#  用法: bash manage.sh [setup|start|stop|restart|status|log|webui ...]
# ═══════════════════════════════════════════════════════════════

# ─── 固定路径 ──────────────────────────────────────────────────
INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$INSTALL_DIR/venv/bin/python3"
VENV_PIP="$INSTALL_DIR/venv/bin/pip"
SCRIPT="$INSTALL_DIR/email_daemon.py"
SERVICE_NAME="email-daemon"
LOG_FILE="$INSTALL_DIR/daemon.log"
PID_FILE="$INSTALL_DIR/daemon.pid"
WEBUI_LOG_FILE="$INSTALL_DIR/webui.log"
WEBUI_PID_FILE="$INSTALL_DIR/webui.pid"
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
    heading "MailMindHub 一键配置向导"
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
    echo "  --- 国际模型 ---"
    echo "   1) DeepSeek API（推荐，性价比高）"
    echo "   2) OpenAI API（gpt-4o）"
    echo "   3) Anthropic API（claude-sonnet）"
    echo "   4) Gemini API"
    echo "   5) Groq API（Llama，速度快）"
    echo "   6) Perplexity API（sonar-pro）"
    echo "   7) Cohere API（command-r-plus）"
    echo "  --- 中国模型 ---"
    echo "   8) 通义千问 API（qwen-max）"
    echo "   9) 月之暗面 Kimi API"
    echo "  10) 智谱 GLM API"
    echo "  11) 讯飞星火 API"
    echo "  12) 百度文心一言 API"
    echo "  13) 零一万物 Yi API"
    echo "  --- CLI 工具 ---"
    echo "  14) claude CLI（需本地已安装 claude 命令）"
    echo "  15) gemini CLI（需本地已安装 gemini 命令）"
    echo "  16) qwen CLI（需本地已安装 qwen 命令）"
    echo "  17) codex CLI（需本地已安装 codex 命令）"
    echo ""
    read -rp "请输入数字 [1-17]: " AI_CHOICE

    case "$AI_CHOICE" in
        1)  AI_BACKEND="deepseek";   AI_KEY_VAR="DEEPSEEK_API_KEY";    AI_TYPE="api" ;;
        2)  AI_BACKEND="openai";     AI_KEY_VAR="OPENAI_API_KEY";      AI_TYPE="api" ;;
        3)  AI_BACKEND="anthropic";  AI_KEY_VAR="ANTHROPIC_API_KEY";   AI_TYPE="api" ;;
        4)  AI_BACKEND="gemini-api"; AI_KEY_VAR="GEMINI_API_KEY";      AI_TYPE="api" ;;
        5)  AI_BACKEND="groq";       AI_KEY_VAR="GROQ_API_KEY";        AI_TYPE="api" ;;
        6)  AI_BACKEND="perplexity"; AI_KEY_VAR="PERPLEXITY_API_KEY";  AI_TYPE="api" ;;
        7)  AI_BACKEND="cohere";     AI_KEY_VAR="COHERE_API_KEY";      AI_TYPE="api" ;;
        8)  AI_BACKEND="qwen-api";   AI_KEY_VAR="QWEN_API_KEY";        AI_TYPE="api" ;;
        9)  AI_BACKEND="moonshot";   AI_KEY_VAR="MOONSHOT_API_KEY";    AI_TYPE="api" ;;
        10) AI_BACKEND="glm";        AI_KEY_VAR="GLM_API_KEY";         AI_TYPE="api" ;;
        11) AI_BACKEND="spark";      AI_KEY_VAR="SPARK_API_KEY";       AI_TYPE="api" ;;
        12) AI_BACKEND="ernie";      AI_KEY_VAR="ERNIE_API_KEY";       AI_TYPE="api" ;;
        13) AI_BACKEND="yi";         AI_KEY_VAR="YI_API_KEY";          AI_TYPE="api" ;;
        14) AI_BACKEND="claude";     AI_KEY_VAR="";                    AI_TYPE="cli" ;;
        15) AI_BACKEND="gemini";     AI_KEY_VAR="";                    AI_TYPE="cli" ;;
        16) AI_BACKEND="qwen";       AI_KEY_VAR="";                    AI_TYPE="cli" ;;
        17) AI_BACKEND="codex";      AI_KEY_VAR="";                    AI_TYPE="cli" ;;
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
    local pidfile="${1:-$PID_FILE}"
    if [ -f "$pidfile" ]; then
        local pid
        pid=$(cat "$pidfile")
        if kill -0 "$pid" 2>/dev/null; then
            echo "$pid"
        fi
    fi
}

do_start() {
    load_env
    heading "启动邮件守护进程"
    local pid
    pid=$(get_pid "$PID_FILE")
    if [ -n "$pid" ]; then
        warn "邮件守护进程已在运行中 (PID: $pid)"
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

    pid=$(get_pid "$PID_FILE")
    if [ -n "$pid" ]; then
        info "邮件守护进程已启动 (PID: $pid)"
        info "日志: $LOG_FILE"
        info "邮箱: $MAILBOX | AI: $AI | 模式: ${MODE:-idle}"
    else
        error "启动失败，查看日志: tail -f $LOG_FILE"
        return 1
    fi
}

do_stop() {
    load_env
    heading "停止邮件守护进程"
    local pid
    pid=$(get_pid "$PID_FILE")
    if [ -z "$pid" ]; then
        warn "邮件守护进程未在运行"
        return 0
    fi
    kill "$pid"
    rm -f "$PID_FILE"
    info "邮件守护进程已停止 (PID: $pid)"
}

do_restart() {
    load_env
    heading "重启邮件守护进程"
    do_stop
    sleep 2
    do_start
}

do_status() {
    load_env
    heading "运行状态"
    local pid wpid
    pid=$(get_pid "$PID_FILE")
    wpid=$(get_pid "$WEBUI_PID_FILE")

    echo ""
    if [ -n "$pid" ]; then
        echo -e "  邮件守护进程  ${GREEN}● 运行中${NC}  PID=$pid  邮箱=$MAILBOX  AI=$AI"
    else
        echo -e "  邮件守护进程  ${RED}○ 未运行${NC}"
    fi
    if [ -n "$wpid" ]; then
        local webui_host webui_port
        webui_host=$(grep -o 'WEBUI_HOST=[^ ]*' "$WEBUI_PID_FILE.meta" 2>/dev/null | cut -d= -f2 || echo "0.0.0.0")
        webui_port=$(grep -o 'WEBUI_PORT=[^ ]*' "$WEBUI_PID_FILE.meta" 2>/dev/null | cut -d= -f2 || echo "8000")
        echo -e "  Web UI        ${GREEN}● 运行中${NC}  PID=$wpid  http://${webui_host}:${webui_port}"
    else
        echo -e "  Web UI        ${RED}○ 未运行${NC}"
    fi
    echo ""

    if [ -n "$pid" ]; then
        echo "邮件守护进程最近日志:"
        tail -5 "$LOG_FILE" 2>/dev/null || echo "（暂无日志）"
        echo ""
    fi
}

do_log() {
    heading "邮件守护进程实时日志 (Ctrl+C 退出)"
    tail -f "$LOG_FILE"
}

# ─── 多实例管理（支持多个管理邮箱）──────────────────────────
# 用法：bash manage.sh instances list
#       bash manage.sh instance start sort
#       bash manage.sh instance stop sort
#       bash manage.sh start-all
#       bash manage.sh stop-all
#       bash manage.sh restart-all
#       bash manage.sh status-all

# 获取所有已配置的管理邮箱（sort, sort2, sort3, ...）
get_manage_mailboxes() {
    load_env
    local boxes=()
    for suffix in "" "2" "3" "4" "5"; do
        local var_name="MAIL_SORT${suffix}_ADDRESS"
        local address="${!var_name}"
        if [ -n "$address" ]; then
            if [ -z "$suffix" ]; then
                boxes+=("sort")
            else
                boxes+=("sort${suffix}")
            fi
        fi
    done
    echo "${boxes[@]}"
}

# 列出所有已配置的管理邮箱
do_instances() {
    heading "已配置的管理邮箱"
    load_env
    local found=0
    for suffix in "" "2" "3" "4" "5"; do
        local var_name="MAIL_SORT${suffix}_ADDRESS"
        local address="${!var_name}"
        if [ -n "$address" ]; then
            local name="sort${suffix}"
            local pid_file="$INSTALL_DIR/daemon_${name}.pid"
            local log_file="$INSTALL_DIR/daemon_${name}.log"
            local pid=$(cat "$pid_file" 2>/dev/null)
            local status="${RED}○ 未运行${NC}"
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                status="${GREEN}● 运行中${NC} (PID: $pid)"
            fi
            echo -e "  ${name:6s}  $address  $status"
            found=1
        fi
    done
    if [ $found -eq 0 ]; then
        warn "未配置任何管理邮箱"
        echo "       请在 .env 中设置 MAIL_SORT_ADDRESS 等变量"
    fi
}

# 启动/停止/重启单个管理邮箱实例
do_instance() {
    local subcmd="$1"
    local name="$2"

    if [ -z "$name" ]; then
        error "请指定管理邮箱名称 (sort, sort2, sort3, ...)"
        echo "  用法：bash manage.sh instance [start|stop|restart] <name>"
        exit 1
    fi

    local pid_file="$INSTALL_DIR/daemon_${name}.pid"
    local log_file="$INSTALL_DIR/daemon_${name}.log"

    case "$subcmd" in
        start)
            heading "启动管理邮箱实例：$name"
            load_env
            ensure_venv

            local address_var="MAIL_SORT${name#sort}_ADDRESS"
            local address="${!address_var}"
            if [ -z "$address" ]; then
                error "未配置管理邮箱：$name"
                exit 1
            fi

            nohup "$VENV_PYTHON" "$SCRIPT" --mailbox "$name" --ai "${AI:-claude}" >> "$log_file" 2>&1 &
            echo $! > "$pid_file"
            sleep 1

            local pid=$(cat "$pid_file" 2>/dev/null)
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                info "管理邮箱实例已启动 (PID: $pid)"
                info "日志：$log_file"
            else
                error "启动失败，查看日志：tail -f $log_file"
                exit 1
            fi
            ;;
        stop)
            heading "停止管理邮箱实例：$name"
            local pid=$(cat "$pid_file" 2>/dev/null)
            if [ -z "$pid" ]; then
                warn "实例 $name 未在运行"
                return 0
            fi
            kill "$pid" 2>/dev/null
            rm -f "$pid_file"
            info "实例 $name 已停止 (PID: $pid)"
            ;;
        restart)
            do_instance stop "$name"
            sleep 1
            do_instance start "$name"
            ;;
        *)
            error "未知子命令：$subcmd"
            echo "  用法：bash manage.sh instance [start|stop|restart] <name>"
            exit 1
            ;;
    esac
}

# 启动所有管理邮箱实例
do_start_all() {
    heading "启动所有管理邮箱实例"
    load_env
    ensure_venv

    local started=0
    for suffix in "" "2" "3" "4" "5"; do
        local var_name="MAIL_SORT${suffix}_ADDRESS"
        local address="${!address_var}"
        if [ -n "$address" ]; then
            local name="sort${suffix}"
            do_instance start "$name"
            ((started++))
        fi
    done

    if [ $started -eq 0 ]; then
        warn "未配置任何管理邮箱"
    else
        info "已启动 $started 个管理邮箱实例"
    fi
}

# 停止所有管理邮箱实例
do_stop_all() {
    heading "停止所有管理邮箱实例"
    local stopped=0
    for suffix in "" "2" "3" "4" "5"; do
        local name="sort${suffix}"
        local pid_file="$INSTALL_DIR/daemon_${name}.pid"
        local pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$pid" ]; then
            kill "$pid" 2>/dev/null
            rm -f "$pid_file"
            info "实例 $name 已停止"
            ((stopped++))
        fi
    done
    if [ $stopped -eq 0 ]; then
        warn "没有运行中的管理邮箱实例"
    fi
}

# 重启所有管理邮箱实例
do_restart_all() {
    heading "重启所有管理邮箱实例"
    do_stop_all
    sleep 2
    do_start_all
}

# 查看所有管理邮箱实例状态
do_status_all() {
    heading "所有管理邮箱实例状态"
    load_env
    local found=0
    for suffix in "" "2" "3" "4" "5"; do
        local var_name="MAIL_SORT${suffix}_ADDRESS"
        local address="${!address_var}"
        if [ -n "$address" ]; then
            local name="sort${suffix}"
            local pid_file="$INSTALL_DIR/daemon_${name}.pid"
            local log_file="$INSTALL_DIR/daemon_${name}.log"
            local pid=$(cat "$pid_file" 2>/dev/null)
            local status="${RED}○ 未运行${NC}"
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                status="${GREEN}● 运行中${NC} (PID: $pid)"
            fi
            echo -e "  ${name:6s}  $address  $status"
            if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
                echo "         日志：$log_file"
                echo "         最近 3 条:"
                tail -3 "$log_file" 2>/dev/null | sed 's/^/           /'
            fi
            found=1
        fi
    done
    if [ $found -eq 0 ]; then
        warn "未配置任何管理邮箱"
    fi
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

_ensure_webui_deps() {
    ensure_venv
    if ! "$VENV_PYTHON" -c "import fastapi, itsdangerous" 2>/dev/null; then
        info "正在安装 Web UI 依赖..."
        "$VENV_PIP" install "fastapi>=0.110.0" "uvicorn[standard]>=0.29.0" "jinja2>=3.1.0" "python-multipart>=0.0.9" "itsdangerous>=2.1.0" --quiet || {
            error "依赖安装失败"
            exit 1
        }
    fi
}

do_webui() {
    [ -f "$ENV_FILE" ] && load_env
    local subcmd="${2:-start}"
    local host="${WEBUI_HOST:-0.0.0.0}"
    local port="${WEBUI_PORT:-8000}"

    # 允许 bash manage.sh webui <host> <port> 直接传参（兼容旧用法）
    if [[ "${2}" =~ ^[0-9] ]] || [[ "${2}" == *"."* ]]; then
        host="${2:-0.0.0.0}"
        port="${3:-8000}"
        subcmd="start"
    fi

    case "$subcmd" in
        start)
            _ensure_webui_deps
            local wpid
            wpid=$(get_pid "$WEBUI_PID_FILE")
            if [ -n "$wpid" ]; then
                warn "Web UI 已在运行中 (PID: $wpid)  http://${host}:${port}"
                return 1
            fi
            heading "启动 Web UI"
            cd "$INSTALL_DIR"
            nohup "$VENV_PYTHON" -m webui.server --host "$host" --port "$port" \
                >> "$WEBUI_LOG_FILE" 2>&1 &
            echo $! > "$WEBUI_PID_FILE"
            echo "WEBUI_HOST=${host} WEBUI_PORT=${port}" > "${WEBUI_PID_FILE}.meta"
            sleep 1
            wpid=$(get_pid "$WEBUI_PID_FILE")
            if [ -n "$wpid" ]; then
                info "Web UI 已启动 (PID: $wpid)"
                info "地址: http://${host}:${port}"
                info "日志: $WEBUI_LOG_FILE"
            else
                error "Web UI 启动失败，查看日志: tail -f $WEBUI_LOG_FILE"
                return 1
            fi
            ;;
        stop)
            heading "停止 Web UI"
            local wpid
            wpid=$(get_pid "$WEBUI_PID_FILE")
            if [ -z "$wpid" ]; then
                warn "Web UI 未在运行"
                return 0
            fi
            kill "$wpid"
            rm -f "$WEBUI_PID_FILE" "${WEBUI_PID_FILE}.meta"
            info "Web UI 已停止 (PID: $wpid)"
            ;;
        restart)
            do_webui "" stop
            sleep 1
            do_webui "" start
            ;;
        status)
            heading "Web UI 状态"
            local wpid
            wpid=$(get_pid "$WEBUI_PID_FILE")
            if [ -n "$wpid" ]; then
                info "状态: ${GREEN}运行中${NC} (PID: $wpid)"
                info "地址: http://${host}:${port}"
                info "日志: $WEBUI_LOG_FILE"
                echo ""
                echo "最近 5 条日志:"
                tail -5 "$WEBUI_LOG_FILE" 2>/dev/null || echo "（暂无日志）"
            else
                warn "状态: 未运行"
            fi
            ;;
        log)
            heading "Web UI 实时日志 (Ctrl+C 退出)"
            tail -f "$WEBUI_LOG_FILE"
            ;;
        *)
            error "未知子命令: $subcmd"
            echo "  用法: bash manage.sh webui [start|stop|restart|status|log]"
            exit 1
            ;;
    esac
}

# ─── 入口 ──────────────────────────────────────────────────────
case "$1" in
    setup)          do_setup ;;
    start)          do_start ;;
    stop)           do_stop ;;
    restart)        do_restart ;;
    status)         do_status ;;
    log)            do_log ;;
    webui)          do_webui "$@" ;;
    install)        do_install ;;
    uninstall)      do_uninstall ;;
    push-templates)
        load_env
        if [ -z "$MAILBOX" ]; then error "未配置邮箱（MAILBOX 为空）"; fi
        if [ -n "$2" ]; then
            heading "发送邮件模板到 $2"
            "$VENV_PYTHON" "$SCRIPT" --mailbox "$MAILBOX" --push-templates-to "$2"
        else
            heading "写入邮件模板"
            "$VENV_PYTHON" "$SCRIPT" --mailbox "$MAILBOX" --push-templates
        fi
        ;;
    # 多实例管理命令
    instances)      do_instances ;;
    instance)       do_instance "$2" "$3" ;;
    start-all)      do_start_all ;;
    stop-all)       do_stop_all ;;
    restart-all)    do_restart_all ;;
    status-all)     do_status_all ;;
    *)
        echo ""
        echo "用法: bash manage.sh <命令>"
        echo ""
        echo "  setup                   一键配置向导（首次使用从这里开始）"
        echo ""
        echo "  邮件守护进程:"
        echo "    start                 后台启动邮件守护进程"
        echo "    stop                  停止邮件守护进程"
        echo "    restart               重启邮件守护进程"
        echo "    status                查看两个服务的运行状态"
        echo "    log                   实时查看邮件守护进程日志"
        echo ""
        echo "  Web UI:"
        echo "    webui [start]         后台启动 Web 管理界面（默认 0.0.0.0:8000）"
        echo "    webui stop            停止 Web UI"
        echo "    webui restart         重启 Web UI"
        echo "    webui status          查看 Web UI 状态"
        echo "    webui log             实时查看 Web UI 日志"
        echo ""
        echo "  多实例管理（管理邮箱）:"
echo "    instances             列出所有已配置的管理邮箱"
echo "    instance start <名>    启动单个管理邮箱实例（如：bash manage.sh instance start sort）"
echo "    instance stop <名>     停止单个管理邮箱实例"
echo "    instance restart <名>  重启单个管理邮箱实例"
echo "    start-all             启动所有管理邮箱实例"
echo "    stop-all              停止所有管理邮箱实例"
echo "    restart-all           重启所有管理邮箱实例"
echo "    status-all            查看所有管理邮箱实例状态"
echo ""
echo "  其他:"
        echo "    push-templates        将指令模板写入邮箱文件夹（方便直接使用）"
        echo ""
        echo "  系统服务:"
        echo "    install               安装为 systemd 服务（开机自启）"
        echo "    uninstall             卸载 systemd 服务"
        echo ""
        ;;
esac
