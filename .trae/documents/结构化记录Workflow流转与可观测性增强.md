## 当前现状与问题
- 当前记录主要集中在 session 级别的 tool_calls 追踪（SessionManagementMiddleware + ToolCallTracingMiddleware），输出为 agent_decision_trace.json，缺少“工作流级”结构（节点开始/结束、节点输入输出、上下文快照）。
- VisionMiddleware 会把 K 线图 base64 从 ToolMessage 中剥离，但没有落盘或关联到 trace，前端无法查看图像。
- context_injection 生成的上下文内容（market_context、symbol_contexts、positions/pending/history）未被结构化记录。
- workflow_main 以“每条告警触发一次 app.invoke”执行，但没有统一的 run_id / trace_id 贯穿全流程。

## 优化方向（你要的“清晰、结构化、可前端观测”）
- **引入 WorkflowRun 级别的追踪记录**：一个告警 = 一个 run_id，包含节点级事件、工具调用、上下文快照、K线图文件引用。
- **节点级事件记录**：每个节点开始/结束、输入摘要、输出摘要、耗时。
- **上下文快照**：context_injection_node 产出的 market_context / symbol_contexts / 账户&持仓摘要等以结构化形式记录（并支持裁剪/哈希以避免过大）。
- **K线图落盘与索引**：get_kline_image_tool 生成的 image_data 写入磁盘（或对象存储），trace 里记录 image_id / file_path / symbol / intervals / kline_count。
- **前端可读 API**：新增 /api/workflow/runs /api/workflow/runs/{id} /api/workflow/runs/{id}/artifacts，直接展示每轮运行细节。

## 实施计划
### 1) 设计统一的 Workflow Trace 数据结构
- 新增 WorkflowRun 结构：run_id、alert_id、symbols、start/end、status、node_events、tool_calls、artifacts。
- 采用 JSONL 追加写入，避免并发覆盖，提升可观测性。

### 2) 全流程注入 run_id
- 在 workflow_main.py 生成 run_id（每个告警一次），通过 RunnableConfig 的 configurable/metadata 传递到所有节点与中间件。

### 3) 节点级结构化记录
- 在 context_injection_node / single_symbol_analysis_node / position_management_node / reporting_node 前后写入 node_events（start/end + payload 摘要）。
- 将上下文快照（market_context、symbol_contexts、账户/持仓/挂单摘要）以结构化形式存入 trace（支持摘要裁剪）。

### 4) 工具调用与 K线图增强
- 扩展 ToolCallTracingMiddleware 记录 run_id、node_name（从 state 或 runtime 中取）、输入输出摘要。
- get_kline_image_tool 在生成图像时落盘，输出 image_id 与路径；VisionMiddleware 记录该 artifact 到 trace。

### 5) 后端 API 与前端展示
- 新增 API 读取 workflow runs/详情/图像。
- 前端新增“Workflow Runs”视图：按轮次展示节点流转、工具调用、上下文摘要、K线图。

### 6) 验证
- 触发一次告警，检查 trace 文件结构、图像落盘与 API 输出；前端页面能完整展示。

如果你确认，我会按以上步骤落地实现。