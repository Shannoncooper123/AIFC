#!/bin/bash
# =============================================================================
# Crypto Monitor - 生产环境启动脚本
# 功能：一键配置依赖环境并以后台方式启动前后端服务
# =============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 项目根目录
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

# PID 文件目录
PID_DIR="$PROJECT_DIR/.pids"
BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"

# 日志目录
LOG_DIR="$PROJECT_DIR/logs"
BACKEND_LOG="$LOG_DIR/backend.log"
FRONTEND_LOG="$LOG_DIR/frontend.log"

# 默认端口
BACKEND_PORT=${BACKEND_PORT:-8000}
FRONTEND_PORT=${FRONTEND_PORT:-3000}

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

check_command() {
    if ! command -v "$1" &> /dev/null; then
        log_error "$1 未安装，请先安装 $1"
        return 1
    fi
    return 0
}

# =============================================================================
# 环境检查
# =============================================================================

check_environment() {
    log_info "检查运行环境..."
    
    # 检查 Node.js
    if ! check_command "node"; then
        log_error "请安装 Node.js (推荐 v18+)"
        exit 1
    fi
    log_info "Node.js 版本: $(node --version)"
    
    # 检查 npm
    if ! check_command "npm"; then
        log_error "请安装 npm"
        exit 1
    fi
    log_info "npm 版本: $(npm --version)"
    
    # 检查 Python
    if ! check_command "python3"; then
        log_error "请安装 Python 3.11+"
        exit 1
    fi
    log_info "Python 版本: $(python3 --version)"
    
    # 检查 uv (Python 包管理器)
    if ! check_command "uv"; then
        log_warn "uv 未安装，正在安装..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
        if ! check_command "uv"; then
            log_error "uv 安装失败，请手动安装: https://docs.astral.sh/uv/"
            exit 1
        fi
    fi
    log_info "uv 版本: $(uv --version)"
    
    log_success "环境检查通过"
}

# =============================================================================
# 依赖安装
# =============================================================================

install_dependencies() {
    log_info "安装项目依赖..."
    
    # 安装后端依赖
    log_info "安装后端 Python 依赖..."
    cd "$BACKEND_DIR"
    uv sync
    log_success "后端依赖安装完成"
    
    # 安装前端依赖
    log_info "安装前端 Node.js 依赖..."
    cd "$FRONTEND_DIR"
    npm install
    log_success "前端依赖安装完成"
    
    cd "$PROJECT_DIR"
}

# =============================================================================
# 构建前端
# =============================================================================

build_frontend() {
    log_info "构建前端生产版本..."
    cd "$FRONTEND_DIR"
    npm run build
    log_success "前端构建完成"
    cd "$PROJECT_DIR"
}

# =============================================================================
# 启动服务
# =============================================================================

start_backend() {
    log_info "启动后端服务 (端口: $BACKEND_PORT)..."
    
    # 检查是否已经在运行
    if [ -f "$BACKEND_PID_FILE" ]; then
        local pid=$(cat "$BACKEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_warn "后端服务已在运行 (PID: $pid)"
            return 0
        fi
    fi
    
    cd "$BACKEND_DIR"
    
    # 使用 nohup 启动后端服务
    nohup uv run uvicorn app.main:app \
        --host 0.0.0.0 \
        --port "$BACKEND_PORT" \
        --workers 1 \
        > "$BACKEND_LOG" 2>&1 &
    
    local pid=$!
    echo "$pid" > "$BACKEND_PID_FILE"
    
    # 等待服务启动
    sleep 3
    
    if kill -0 "$pid" 2>/dev/null; then
        log_success "后端服务已启动 (PID: $pid)"
    else
        log_error "后端服务启动失败，请检查日志: $BACKEND_LOG"
        exit 1
    fi
    
    cd "$PROJECT_DIR"
}

start_frontend() {
    log_info "启动前端服务 (端口: $FRONTEND_PORT)..."
    
    # 检查是否已经在运行
    if [ -f "$FRONTEND_PID_FILE" ]; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            log_warn "前端服务已在运行 (PID: $pid)"
            return 0
        fi
    fi
    
    cd "$FRONTEND_DIR"
    
    # 检查是否有构建产物
    if [ ! -d "dist" ]; then
        log_warn "未找到前端构建产物，正在构建..."
        npm run build
    fi
    
    # 使用 nohup 启动前端预览服务
    nohup npm run preview -- --host 0.0.0.0 --port "$FRONTEND_PORT" \
        > "$FRONTEND_LOG" 2>&1 &
    
    local pid=$!
    echo "$pid" > "$FRONTEND_PID_FILE"
    
    # 等待服务启动
    sleep 3
    
    if kill -0 "$pid" 2>/dev/null; then
        log_success "前端服务已启动 (PID: $pid)"
    else
        log_error "前端服务启动失败，请检查日志: $FRONTEND_LOG"
        exit 1
    fi
    
    cd "$PROJECT_DIR"
}

# =============================================================================
# 主流程
# =============================================================================

main() {
    echo ""
    echo "=============================================="
    echo "   Crypto Monitor - 生产环境启动"
    echo "=============================================="
    echo ""
    
    # 创建必要的目录
    mkdir -p "$PID_DIR"
    mkdir -p "$LOG_DIR"
    
    # 检查环境
    check_environment
    
    # 解析参数
    SKIP_INSTALL=false
    SKIP_BUILD=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-install)
                SKIP_INSTALL=true
                shift
                ;;
            --skip-build)
                SKIP_BUILD=true
                shift
                ;;
            --backend-port)
                BACKEND_PORT="$2"
                shift 2
                ;;
            --frontend-port)
                FRONTEND_PORT="$2"
                shift 2
                ;;
            *)
                log_warn "未知参数: $1"
                shift
                ;;
        esac
    done
    
    # 安装依赖
    if [ "$SKIP_INSTALL" = false ]; then
        install_dependencies
    else
        log_info "跳过依赖安装"
    fi
    
    # 构建前端
    if [ "$SKIP_BUILD" = false ]; then
        build_frontend
    else
        log_info "跳过前端构建"
    fi
    
    # 启动服务
    start_backend
    start_frontend
    
    echo ""
    echo "=============================================="
    log_success "所有服务已启动!"
    echo "=============================================="
    echo ""
    echo "  后端 API:  http://localhost:$BACKEND_PORT"
    echo "  前端界面:  http://localhost:$FRONTEND_PORT"
    echo ""
    echo "  日志文件:"
    echo "    后端: $BACKEND_LOG"
    echo "    前端: $FRONTEND_LOG"
    echo ""
    echo "  停止服务: ./stop_production.sh"
    echo "=============================================="
    echo ""
}

main "$@"
