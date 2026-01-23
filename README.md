# 加密货币异动监控系统

专业的加密货币市场异动监控系统，基于币安WebSocket API，使用量化技术指标（ATR、标准差、Z-Score）实时检测市场异常波动，并通过QQ邮箱发送告警。

## 功能特性

- 🔍 **实时监控**：监控200+个USDT永续合约的1分钟K线数据
- 📊 **专业指标**：ATR、标准差、成交量Z-Score等量化指标
- 🎯 **动态检测**：基于Z-Score的自适应异常检测算法
- 📧 **邮件告警**：支持QQ邮箱的HTML格式告警邮件
- ⚙️ **灵活配置**：所有参数可配置（K线间隔、指标周期、阈值等）
- 🔄 **增量更新**：定期自动更新交易对列表，自动监控新币、移除冷门币
- 🏗️ **模块化设计**：高度解耦的分层架构

## 项目结构

```
monitor/
├── config/              # 配置管理层
├── src/
│   ├── clients/        # 外部服务客户端
│   ├── core/           # 核心业务逻辑
│   ├── data/           # 数据管理
│   ├── indicators/     # 技术指标
│   ├── detection/      # 异常检测
│   ├── alerts/         # 告警系统
│   └── utils/          # 工具函数
├── tests/              # 测试文件
└── main.py             # 主程序入口
```

## 快速开始

### 1. 安装依赖

```bash
# 安装Poetry（Windows）
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# 安装项目依赖
poetry install
```

### 2. 配置QQ邮箱

1. 登录 [QQ邮箱](https://mail.qq.com)
2. 进入 **设置 → 账户**
3. 找到 **POP3/IMAP/SMTP/Exchange/CardDAV/CalDAV服务**
4. 开启 **SMTP服务**
5. 点击 **生成授权码**，按提示发送短信获取16位授权码
6. 复制配置文件并填入授权码：

```bash
cp .env.example .env
# 编辑 .env 文件，填入你的QQ邮箱和授权码
```

### 3. 测试配置

```bash
poetry run python tests/test_config.py
```

### 4. 运行系统

```bash
poetry run python main.py
```

## 配置说明

### .env 文件（敏感信息）

```env
SMTP_HOST=smtp.qq.com
SMTP_PORT=587
SMTP_USER=your_qq_number@qq.com
SMTP_PASSWORD=your_16_digit_authorization_code
SMTP_USE_TLS=true
ALERT_EMAIL=your_qq_number@qq.com
LOG_LEVEL=INFO
```

### config.yaml 文件（系统参数）

所有技术参数都可以在此文件中配置：

- **K线配置**：间隔（1m/3m/5m等）、历史数据量
- **指标周期**：ATR周期、标准差周期、成交量MA周期
- **检测阈值**：各指标的Z-Score阈值
- **告警配置**：冷却时间（0表示不限制）、聚合周期、邮件容量
- **交易对过滤**：最小成交量、排除列表、更新间隔等

## 异常检测逻辑

系统使用多维度指标组合检测异常：

1. **ATR突增**：Z-Score > 2.5（波动剧烈）
2. **价格变化率**：Z-Score > 2.0（急涨急跌）
3. **成交量异常**：Z-Score > 3.0（放量）
4. **外包线形态**：当前K线完全包住上一根K线（强势突破信号）

当至少2个指标同时异常时触发告警，并计算异常等级（1-5星）。

## 技术栈

- **Python 3.9+**
- **WebSocket**：实时数据推送
- **NumPy**：高性能数值计算
- **Poetry**：依赖管理
- **YAML**：配置管理

## 运行流程

```
加载配置 → 测试邮箱 → 获取交易对列表 → 预加载历史数据 
→ 建立WebSocket连接 → 启动动态更新器 → 实时监控 
→ 异常检测 → 邮件告警 → 定期更新交易对列表
```

## 日志示例

```
[INFO] 配置加载成功：K线间隔=1m, 历史数据=30根
[INFO] QQ邮箱连接测试成功（smtp.qq.com:587）
[INFO] 获取到 215 个USDT永续合约
[INFO] 历史数据初始化完成（50根K线/交易对）
[INFO] WebSocket连接建立成功
[INFO] 开始监控...
[ALERT] BTCUSDT 异常检测 ⭐⭐⭐⭐
  - 价格: $45,231 (+3.2%)
  - ATR Z-Score: 3.1
  - 成交量 Z-Score: 3.8
[INFO] 告警邮件已发送
```

## 注意事项

- 请确保网络能访问币安API
- QQ邮箱需要使用授权码而非密码
- 建议使用稳定的网络环境运行
- 首次启动会加载历史数据，需要一些时间

## 许可证

MIT License

