# Crypto Monitor Backend

FastAPI 后端服务，提供加密货币异动监控系统的 API 接口。

## 功能

- **服务管理**: 启动/停止/重启 Monitor、Agent、Workflow 服务
- **告警查询**: 获取历史告警记录
- **持仓管理**: 查看当前持仓和历史持仓
- **配置管理**: 读取和更新系统配置
- **实时事件**: WebSocket 推送实时事件

## 快速开始

```bash
# 安装依赖
uv sync

# 启动开发服务器
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API 文档

启动服务后访问:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 目录结构

```
backend/
├── app/                    # FastAPI 应用
│   ├── api/               # API 路由
│   ├── core/              # 核心配置
│   ├── models/            # 数据模型
│   └── services/          # 业务服务
├── modules/               # 业务模块
│   ├── monitor/           # 市场监控
│   ├── agent/             # 交易代理
│   └── config/            # 配置管理
├── data/                  # 数据文件
├── logs/                  # 日志文件
└── config.yaml            # 配置文件
```
