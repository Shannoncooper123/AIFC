## 调整后的结论
- `workflow_trace_middleware.py` 保留，并扩展实现 `wrap_model_call` / `awrap_model_call` 以记录 LLM 输出与元信息。
- 抽象 `create_traced_agent()` 工具函数，集中注入 trace 中间件与模型初始化逻辑，新增 tool/node 时只需调用一次。

## 实施计划
### 1) 扩展 WorkflowTraceMiddleware
- 实现 `wrap_model_call`/`awrap_model_call`：记录模型输入摘要（messages、system_prompt、tool_choice）与输出摘要（AIMessage 内容、tool_calls、token/metadata）。
- 对输出做裁剪与脱敏（避免过长或包含 base64）。

### 2) 新增 create_traced_agent 工具
- 新建 `modules/agent/utils/agent_factory.py` 或 `workflow_trace_injector.py`：
  - `create_traced_agent(node_name, model_config, tools, system_prompt, extra_middlewares=[])`
  - 内部构建 ChatOpenAI + 中间件（VisionMiddleware、WorkflowTraceMiddleware）
  - 输出标准化 agent，统一 trace 规则。

### 3) 迁移现有节点
- `single_symbol_analysis_node` / `position_management_node` / `reporting_node` 改为使用 `create_traced_agent()`
- 移除节点内重复的模型初始化和 middleware 拼接。

### 4) 验证
- 触发一次 workflow，确认 trace 中包含：
  - 节点输入/输出事件
  - 工具调用事件
  - LLM 输出事件（含 tool_calls 摘要）

如果确认，我会按此方案实现。