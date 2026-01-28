#!/bin/bash
# =============================================================================
# Crypto Monitor - 生产环境停止脚本
# 功能：优雅地停止前后端服务
# =============================================================================

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# PID 文件目录
PID_DIR="$PROJECT_DIR/.pids"
BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"

# =============================================================================
# 工具函数
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# =============================================================================
# 停止服务
# =============================================================================

kill_process_tree() {
    local pid="$1"
    local signal="${2:-TERM}"
    
    local children=$(pgrep -P "$pid" 2>/dev/null)
    for child in $children; do
        kill_process_tree "$child" "$signal"
    done
    
    kill -"$signal" "$pid" 2>/dev/null
}

kill_port_processes() {
    local port="$1"
    local signal="${2:-TERM}"
    
    local pids=$(lsof -t -i :"$port" 2>/dev/null | sort -u)
    if [ -n "$pids" ]; then
        log_info "发现占用端口 $port 的进程: $pids"
        for pid in $pids; do
            kill -"$signal" "$pid" 2>/dev/null
        done
    fi
}

stop_service() {
    local name="$1"
    local pid_file="$2"
    local timeout="${3:-10}"
    
    if [ ! -f "$pid_file" ]; then
        log_warn "$name PID 文件不存在"
        return 0
    fi
    
    local pid=$(cat "$pid_file")
    
    if ! kill -0 "$pid" 2>/dev/null; then
        log_warn "$name 进程 (PID: $pid) 已不存在"
        rm -f "$pid_file"
        return 0
    fi
    
    log_info "正在停止 $name (PID: $pid) 及其子进程..."
    
    kill_process_tree "$pid" "TERM"
    
    local count=0
    while kill -0 "$pid" 2>/dev/null && [ $count -lt $timeout ]; do
        sleep 1
        count=$((count + 1))
        echo -n "."
    done
    echo ""
    
    if kill -0 "$pid" 2>/dev/null; then
        log_warn "$name 未能优雅关闭，强制终止..."
        kill_process_tree "$pid" "9"
        sleep 1
    fi
    
    rm -f "$pid_file"
    
    if ! kill -0 "$pid" 2>/dev/null; then
        log_success "$name 已停止"
    else
        log_error "$name 停止失败"
        return 1
    fi
}

stop_backend() {
    stop_service "后端服务" "$BACKEND_PID_FILE" 15
    
    # 额外清理：确保 8000 端口上的所有进程都被终止
    log_info "清理端口 8000 上的残留进程..."
    kill_port_processes 8000 "TERM"
    sleep 2
    
    # 检查是否还有残留进程
    local remaining=$(lsof -t -i :8000 2>/dev/null | wc -l)
    if [ "$remaining" -gt 0 ]; then
        log_warn "仍有 $remaining 个进程占用端口 8000，强制终止..."
        kill_port_processes 8000 "9"
        sleep 1
    fi
    
    # 最终检查
    remaining=$(lsof -t -i :8000 2>/dev/null | wc -l)
    if [ "$remaining" -gt 0 ]; then
        log_error "无法清理端口 8000 上的所有进程"
    else
        log_success "端口 8000 已清理干净"
    fi
}

stop_frontend() {
    stop_service "前端服务" "$FRONTEND_PID_FILE" 10
}

# =============================================================================
# 查看状态
# =============================================================================

show_status() {
    echo ""
    echo "=============================================="
    echo "   服务状态"
    echo "=============================================="
    echo ""
    
    # 后端状态
    if [ -f "$BACKEND_PID_FILE" ]; then
        local backend_pid=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$backend_pid" 2>/dev/null; then
            echo -e "  后端服务: ${GREEN}运行中${NC} (PID: $backend_pid)"
        else
            echo -e "  后端服务: ${RED}已停止${NC} (PID 文件存在但进程不存在)"
        fi
    else
        echo -e "  后端服务: ${YELLOW}未启动${NC}"
    fi
    
    # 前端状态
    if [ -f "$FRONTEND_PID_FILE" ]; then
        local frontend_pid=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$frontend_pid" 2>/dev/null; then
            echo -e "  前端服务: ${GREEN}运行中${NC} (PID: $frontend_pid)"
        else
            echo -e "  前端服务: ${RED}已停止${NC} (PID 文件存在但进程不存在)"
        fi
    else
        echo -e "  前端服务: ${YELLOW}未启动${NC}"
    fi
    
    echo ""
    echo "=============================================="
    echo ""
}

# =============================================================================
# 主流程
# =============================================================================

main() {
    echo ""
    echo "=============================================="
    echo "   Crypto Monitor - 停止服务"
    echo "=============================================="
    echo ""
    
    # 解析参数
    case "${1:-all}" in
        backend)
            stop_backend
            ;;
        frontend)
            stop_frontend
            ;;
        status)
            show_status
            ;;
        all|*)
            stop_frontend
            stop_backend
            ;;
    esac
    
    echo ""
    echo "=============================================="
    log_success "操作完成"
    echo "=============================================="
    echo ""
    
    # 显示当前状态
    show_status
}

# 显示帮助
show_help() {
    echo "用法: $0 [命令]"
    echo ""
    echo "命令:"
    echo "  all       停止所有服务 (默认)"
    echo "  backend   仅停止后端服务"
    echo "  frontend  仅停止前端服务"
    echo "  status    查看服务状态"
    echo "  help      显示此帮助信息"
    echo ""
}

if [ "$1" = "help" ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    show_help
    exit 0
fi

main "$@"
