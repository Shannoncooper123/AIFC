## 结论
- 可以移除 `session_management_middleware.py` 与 `tool_call_tracing_middleware.py`，前提是确认已无其它地方依赖 `decision_trace_path` 的旧 session 追踪文件与中间件。
- “上下文快照分层展示”可以在前端 Workflow 页面加入 Tab（节点输入 / 节点输出 / 工具调用 / 上下文快照 / 图像），并在后端 trace 事件中补齐可分层的结构字段。

## 实施计划
### 1) 依赖检查并移除旧 Session 追踪
- 全仓搜索 `SessionManagementMiddleware` 与 `ToolCallTracingMiddleware` 的引用点。
- 从所有 agent 节点/构建逻辑中移除旧中间件；删除对应文件。
- 删除 `decision_trace_storage.py`（如无其它用途）与 config 里 `decision_trace_path` 的依赖（保留字段可选）。

### 2) 细化 Workflow Trace 事件结构
- 为每个节点补充更清晰的 `input_snapshot` / `output_snapshot` 字段。
- 工具调用事件增加 `node`, `phase`, `kind=tool_call`，并在 payload 中保留字段分层。

### 3) 前端分层展示（Tab UI）
- Workflow 详情页按节点分组后，再提供 Tab：
  - 节点输入
  - 节点输出
  - 工具调用
  - 上下文快照
  - 图像
- 每个 Tab 只渲染对应事件，提高可读性。

### 4) API 与字段适配
- 保持 `/api/workflow/runs/{id}` 返回事件流；前端按 type/phase 归类。
- 若需要，在后端加入节点维度的聚合接口（可选）。

### 5) 验证
- 触发一次 workflow，确保：
  - 旧 session 追踪不再产出
  - 新 trace 中节点输入/输出/工具调用/快照事件完整
  - 前端 Tab 展示清晰

如果确认，我将按此计划执行。