#!/bin/bash
set -ex
cd "$(dirname "$0")"

# 默认端口和主机绑定，支持通过环境变量覆盖
export PORT="${PORT:-3000}"
BIND_ADDR="0.0.0.0"

# 安装依赖
npm install

# 使用 nohup 和 & 在后台启动服务
echo "Starting server with npm run dev on all interfaces in the background..."
nohup npm run dev -- -H "$BIND_ADDR" -p "$PORT" > faas.log 2>&1 &
echo $! > faas.pid