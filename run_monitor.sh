#!/usr/bin/env bash
set -euo pipefail

# 目录配置
BASE_DIR="/home/sunfayao/monitor"
cd "$BASE_DIR"

# Python与主程序路径
VENV_PY="$BASE_DIR/.venv/bin/python"
MAIN="$BASE_DIR/monitor_module/main.py"

# 日志目录与文件
LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"
TIMESTAMP="$(date +'%Y%m%d_%H%M%S')"
LOG_FILE="$LOG_DIR/monitor_${TIMESTAMP}.log"
PID_FILE="$BASE_DIR/monitor.pid"

# 设置 PYTHONPATH 确保可以导入 config 模块
export PYTHONPATH="$BASE_DIR:${PYTHONPATH:-}"

# 启动前先清理旧进程
echo "检查并清理旧的 monitor 进程..."
PIDS=$(ps aux | grep "python.*monitor_module/main.py" | grep -v grep | awk '{print $2}' || true)

if [[ -n "$PIDS" ]]; then
  echo "  发现旧进程，正在停止..."
  for pid in $PIDS; do
    echo "    停止进程 PID=$pid"
    kill -SIGTERM "$pid" 2>/dev/null || true
  done
  
  # 等待优雅退出（最多3秒）
  for i in {1..6}; do
    sleep 0.5
    REMAINING=$(ps aux | grep "python.*monitor_module/main.py" | grep -v grep | wc -l | tr -d ' ')
    if [[ "${REMAINING:-0}" -eq 0 ]]; then
      echo "    ✅ 旧进程已停止"
      break
    fi
  done
  
  # 如果还有进程，强制停止
  PIDS=$(ps aux | grep "python.*monitor_module/main.py" | grep -v grep | awk '{print $2}' || true)
  if [[ -n "$PIDS" ]]; then
    echo "    强制停止残留进程..."
    for pid in $PIDS; do
      kill -9 "$pid" 2>/dev/null || true
    done
    sleep 0.5
  fi
fi

# 启动后台进程（关闭终端不受影响）
echo "启动加密货币监控系统..."
nohup "$VENV_PY" "$MAIN" >> "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

# 启动结果与日志提示
echo "已启动: PID=$PID"
echo "日志文件: $LOG_FILE"
echo "查看实时日志: tail -f \"$LOG_FILE\""

# 可选：跟随日志输出（不影响后台运行）
if [[ "${1:-}" == "-f" || "${1:-}" == "follow" ]]; then
  echo "跟随日志输出 (Ctrl+C退出跟随，不影响后台进程)"
  tail -f "$LOG_FILE"
fi