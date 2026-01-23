#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/home/sunfayao/monitor"
cd "$BASE_DIR"

VENV_PY="$BASE_DIR/.venv/bin/python"
MAIN="$BASE_DIR/agent/workflow_main.py"

LOG_DIR="$BASE_DIR/logs"
mkdir -p "$LOG_DIR"
TIMESTAMP="$(date +'%Y%m%d_%H%M%S')"
LOG_FILE="$LOG_DIR/workflow_${TIMESTAMP}.log"
PID_FILE="$BASE_DIR/workflow.pid"

# 设置 PYTHONPATH 确保可以导入 config 和其他模块
export PYTHONPATH="$BASE_DIR:${PYTHONPATH:-}"

# 启动前先清理旧进程
echo "检查并清理旧的 workflow 进程..."
PIDS=$(ps aux | grep "python.*workflow_main.py" | grep -v grep | awk '{print $2}' || true)

if [[ -n "$PIDS" ]]; then
  echo "  发现旧进程，正在发送停止信号..."
  for pid in $PIDS; do
    echo "    停止进程 PID=$pid (SIGTERM)"
    kill -SIGTERM "$pid" 2>/dev/null || true
  done
  
  # 等待优雅退出（最多30秒，每秒检查一次）
  echo "    等待进程优雅退出..."
  for i in {1..30}; do
    sleep 1
    REMAINING=$(ps aux | grep "python.*workflow_main.py" | grep -v grep | wc -l | tr -d ' ')
    if [[ "${REMAINING:-0}" -eq 0 ]]; then
      echo "    ✅ 旧进程已停止"
      break
    fi
    # 每5秒显示一次等待进度
    if [[ $((i % 5)) -eq 0 ]]; then
      echo "    等待中... (${i}s)"
    fi
  done
  
  # 检查是否还有残留进程
  REMAINING=$(ps aux | grep "python.*workflow_main.py" | grep -v grep | wc -l | tr -d ' ')
  if [[ "${REMAINING:-0}" -ne 0 ]]; then
    echo "    ⚠️ 警告：进程在30秒后仍未退出"
    echo "    请手动检查进程状态，或使用 stop_python.sh 强制停止"
    echo "    继续启动新进程可能会导致冲突"
    exit 1
  fi
fi

echo "启动工作流主进程..."
nohup "$VENV_PY" "$MAIN" >> "$LOG_FILE" 2>&1 &
PID=$!
echo "$PID" > "$PID_FILE"

echo "已启动: PID=$PID"
echo "日志文件: $LOG_FILE"

echo "查看实时日志: tail -f \"$LOG_FILE\""

if [[ "${1:-}" == "-f" || "${1:-}" == "follow" ]]; then
  echo "跟随日志输出 (Ctrl+C退出跟随，不影响后台进程)"
  tail -f "$LOG_FILE"
fi