#!/usr/bin/env bash
set -euo pipefail

# 目录配置
BASE_DIR="/home/sunfayao/monitor"
cd "$BASE_DIR"

# Python与主程序路径
VENV_PY="$BASE_DIR/.venv/bin/python"
DASHBOARD_APP="$BASE_DIR/web_dashboard/app.py"

# 日志目录与文件
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"
TIMESTAMP="$(date +'%Y%m%d_%H%M%S')"
LOG_FILE="$LOG_DIR/dashboard_${TIMESTAMP}.log"
PID_FILE="$BASE_DIR/dashboard.pid"

# 检查虚拟环境
if [[ ! -f "$VENV_PY" ]]; then
    echo "错误: 未找到Python虚拟环境: $VENV_PY"
    echo "请先运行: poetry install"
    exit 1
fi

# 检查依赖包
echo "检查依赖包..."
"$VENV_PY" -c "import flask" 2>/dev/null || {
    echo "正在安装依赖..."
    cd "$BASE_DIR"
    poetry install --no-root
}

# 启动前先清理旧进程
echo "检查并清理旧的 dashboard 进程..."
PIDS=$(ps aux | grep "python.*web_dashboard/app.py" | grep -v grep | awk '{print $2}' || true)

if [[ -n "$PIDS" ]]; then
  echo "  发现旧进程，正在停止..."
  for pid in $PIDS; do
    echo "    停止进程 PID=$pid"
    kill -SIGTERM "$pid" 2>/dev/null || true
  done
  
  # 等待优雅退出（最多3秒）
  for i in {1..6}; do
    sleep 0.5
    REMAINING=$(ps aux | grep "python.*web_dashboard/app.py" | grep -v grep | wc -l | tr -d ' ')
    if [[ "${REMAINING:-0}" -eq 0 ]]; then
      echo "    ✅ 旧进程已停止"
      break
    fi
  done
  
  # 如果还有进程，强制停止
  PIDS=$(ps aux | grep "python.*web_dashboard/app.py" | grep -v grep | awk '{print $2}' || true)
  if [[ -n "$PIDS" ]]; then
    echo "    强制停止残留进程..."
    for pid in $PIDS; do
      kill -9 "$pid" 2>/dev/null || true
    done
    sleep 0.5
  fi
fi

# 清理过期的 PID 文件
if [[ -f "$PID_FILE" ]]; then
  rm -f "$PID_FILE"
fi

# 设置 PYTHONPATH 确保可以导入 config 和其他模块
export PYTHONPATH="$BASE_DIR:${PYTHONPATH:-}"

# 启动后台进程
echo "启动监控数据推送服务..."
nohup "$VENV_PY" "$DASHBOARD_APP" >> "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

# 等待启动
sleep 2

# 检查进程是否还在运行
if ps -p "$PID" > /dev/null 2>&1; then
    echo "✓ 数据推送服务已启动"
    echo "  PID: $PID"
    echo "  日志文件: $LOG_FILE"
    echo ""
    echo "查看实时日志: tail -f \"$LOG_FILE\""
    echo "停止服务: ./stop_dashboard.sh"
else
    echo "✗ 启动失败，请查看日志: $LOG_FILE"
    rm -f "$PID_FILE"
    exit 1
fi

