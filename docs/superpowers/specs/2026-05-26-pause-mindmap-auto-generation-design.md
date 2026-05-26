# 暂停思维导图自动生成 — 设计文档

## 目标

在新建课题对话框中增加选项，让用户控制是否在创建课题后自动调用 LLM 生成思维导图。

## 当前行为

创建课题后**无条件**自动触发生成。链路：
`WorkspaceDialog` → `WorkspaceList._create_workspace()` → emit `build_map_requested` → `MainWindow._on_build_requested()` → `TopicBuildWorker` → `TopicBuilder.build()` → LLM 生成节点和边。

## 设计方案

在 `WorkspaceDialog` 中增加一个勾选框"创建后自动生成思维导图"，默认勾选，用户可取消。

### 涉及文件

1. **`app/ui/dialogs.py`** — `WorkspaceDialog`
   - 在描述框和按钮之间加入 `QCheckBox`，label 为"创建后自动生成思维导图"
   - 默认 checked（向后兼容）
   - `get_result()` 返回值从 3 元组扩展为 4 元组：`(title, desc, color, auto_generate)`

2. **`app/ui/workspace_list.py`** — `WorkspaceList`
   - `open_new_workspace_dialog()` 读取 `auto_generate` 字段并传给 `_create_workspace()`
   - `_create_workspace(title, desc, auto_generate=True)` 新增参数，仅在 `auto_generate=True` 时 emit `build_map_requested`

3. **不变** — `main_window.py`, `worker.py`, `topic_builder.py` 等无需修改

### 数据流

```
WorkspaceDialog
  → get_result() → (title, desc, color, auto_generate)
  → open_new_workspace_dialog()
  → _create_workspace(title, desc, auto_generate)
  → if auto_generate: emit build_map_requested
  → MainWindow._on_build_requested() → TopicBuildWorker
```

### 边界情况

- 用户取消勾选后创建课题 → 只创建空白工作区，不触发 LLM 调用。用户可后续通过手动按钮触发生成。
- 现有编辑课题对话框不受影响（`edit_mode=True` 时不显示此选项）。
- 向后兼容：默认勾选，老用户行为不变。
