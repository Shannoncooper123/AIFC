# Workflow Trace UI 深度优化计划

我们将参照 LangSmith 的极简风格，对 Workflow Trace 界面进行全面重构。

## 1. 核心改进点

- **移除顶部概览**：删除顶部的统计信息栏，让界面更专注。
- **合并模型调用**：将分散的 `Model Input` 和 `Model Output` 合并为一个 `Model Call` 节点。点击该节点后，在右侧面板同时展示 Input 和 Output。
- **视觉风格升级**：
  - **配色**：弃用蓝紫色调，采用 Zinc/Slate 黑白灰极简配色（`bg-zinc-950`, `text-zinc-200`）。
  - **图标**：移除所有 Emoji，全面使用 `lucide-react` 专业图标（如 `Bot`, `Wrench`, `Workflow`）。
  - **层级结构**：优化树形结构的缩进和连接线，使其层级关系更清晰。

## 2. 修改详情

### `TimelineView.tsx`
- **移除**：删除顶部的 `总耗时`、`节点数` 等概览区域。
- **样式**：背景色调整为深色（`bg-zinc-950`），边框调整为 `border-zinc-800`。
- **布局**：保持左右双面板布局，优化面板间的分隔线样式。

### `SpanItem.tsx` (树节点渲染)
- **逻辑优化**：
  - 在渲染子节点前，**预处理** `children` 列表，将相邻的 `model_call (phase=before)` 和 `model_call (phase=after)` 合并为一个逻辑节点。
- **UI 升级**：
  - 图标：使用 `Workflow` 或 `CircleDot` 代表 LangGraph 节点。
  - 展开/收起：使用 `ChevronRight` / `ChevronDown`。
  - 状态：使用小圆点或 `CheckCircle2` / `XCircle` / `Loader2`。
  - **树形线**：增强左侧边框线（`border-l`），使层级视觉引导更明显。

### `ChildItem.tsx` (叶子节点渲染)
- **支持新类型**：增加对 "合并后的模型调用" 的渲染支持。
- **UI 升级**：
  - **Model Call**：图标 `Bot`，显示 "Model Call #N"，点击右侧展示完整对话。
  - **Tool Call**：图标 `Wrench`，显示工具名称。
  - 移除原来复杂的内联 Payload 显示，所有详情统一移至右侧面板。

### `DetailPanel.tsx` (右侧详情)
- **Model Call 详情**：
  - **Input Tab**：展示 `recent_messages`（对话历史）。
  - **Output Tab**：展示 `response_content` 和 `tool_calls`。
- **配色调整**：统一使用黑白灰配色，代码块使用深色背景。

## 3. 执行步骤

1.  **清理与重构**：修改 `TimelineView`，移除概览，确立新的配色基调。
2.  **节点合并逻辑**：在 `SpanItem` 中实现模型调用的合并逻辑。
3.  **组件样式升级**：依次更新 `SpanItem` 和 `ChildItem`，替换图标和配色。
4.  **详情面板适配**：更新 `DetailPanel` 以支持合并后的数据结构。
5.  **验证**：运行构建并检查 UI 效果。
