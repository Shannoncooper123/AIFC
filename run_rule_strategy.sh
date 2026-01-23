#!/bin/bash

# BB+RSI 金字塔规则交易策略启动脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

LOG_DIR="logs"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/rule_strategy_${TIMESTAMP}.log"

echo "========================================"
echo "BB+RSI 金字塔规则交易策略"
echo "========================================"
echo "启动时间: $(date)"
echo "日志文件: $LOG_FILE"
echo ""

# 激活虚拟环境（如果存在）
if [ -d "venv" ]; then
    echo "激活虚拟环境..."
    source venv/bin/activate
fi

# 检查配置文件
if [ ! -f "config.yaml" ]; then
    echo "错误: config.yaml 不存在"
    exit 1
fi

# 检查是否启用规则策略
ENABLED=$(python3 -c "import yaml; config=yaml.safe_load(open('config.yaml')); print(config.get('rule_strategy', {}).get('enabled', False))")
if [ "$ENABLED" != "True" ]; then
    echo "错误: 规则策略未启用"
    echo "请在 config.yaml 中设置: rule_strategy.enabled = true"
    exit 1
fi

echo "✅ 规则策略已启用"
echo ""
echo "启动策略执行器（后台运行）..."
echo "日志文件: $LOG_FILE"
echo ""

# 使用 nohup 在后台运行策略
nohup python3 -m agent.rule_strategy.main >> "$LOG_FILE" 2>&1 &

PID=$!

echo "✅ 策略已启动"
echo "进程 ID: $PID"
echo "日志文件: $LOG_FILE"
echo ""
echo "查看实时日志："
echo "  tail -f $LOG_FILE"
echo ""
echo "停止策略："
echo "  kill $PID"
echo ""
echo "========================================"
