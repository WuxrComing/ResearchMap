# @Mention Agent 自动联想与消息路由

## 概述

在聊天输入框中输入 `@` 符号时，自动弹出 agent 联想列表，支持实时过滤。选择后将 `@AgentName` 插入输入框。新增 MessageRouter 模块负责解析 @mentions 并将消息路由到对应 agent。支持 agent 间自动协作（可配置开关）。

## UI 变更

### 输入框 @ 联想（chat_view.py）

- 保持 `QLineEdit`，使用 `QCompleter` 实现 @ 触发联想
- 输入 `@` 时立即弹出 agent 列表，支持实时过滤（如 `@Pa` → 只显示 Paper Agent）
- 每项显示：agent 名称 + 角色标签 + 颜色标识
- 键盘 ↑↓ 导航，Enter 选择，Esc 关闭，鼠标点击也可选择
- 选择后将 `@AgentName ` 以纯文本插入光标位置
- 支持一条消息中 @ 多个 agent

### 自动协作开关

- 位置：聊天窗口 header 栏（"Agent 对话" 标题旁）
- 默认关闭
- 关闭：@agent 仅标记消息目标，路由到指定 agent 后结束
- 开启：agent 回复中的 @agent 被自动执行，形成协作链

## MessageRouter 模块

新增 `app/services/message_router.py`。

### 解析 @mentions

从文本中提取 `@AgentName` 模式，在 `agent_configs` 表中查找匹配的 agent（按 name 匹配）。

### 消息分发

- 无 @mention：使用默认 agent（Topic Agent, role="assistant"）
- 单个 @mention：路由到该 agent，使用其 system_prompt 和 model
- 多个 @mention：并行调用所有被 @ 的 agent，各自独立回复

### 自动协作循环（开关开启时）

```
max_rounds = 3
已调用 agents = set()

while round < max_rounds:
    调用 agent → 获取回复 → 写入 DB → 刷新 UI
    提取回复中的 @mentions
    过滤已调用过的 agents
    if 有新 @mentions and 开关开启:
        round += 1
        继续循环
    else:
        break
```

- 最大 3 轮，防止无限循环
- 已调用过的 agent 不再重复调用
- 每轮结果实时显示在聊天窗口
- 中间消息全部可见

### 上下文构建

- 被 @ 的 agent 看到当前 session 完整对话历史（最近 20 条）
- 每条消息标注发送者（user / agent name）
- 注入自身 system_prompt + 可用角色摘要

### System Prompt 增强

MessageRouter 为每个 agent 动态追加可用角色列表：

```
[Agent 自身的 system_prompt]

---
可用的 Agent 角色（你可以通过 @Agent名称 调用他们协助你）：
- Topic Agent: 核心研究助手，帮助理解课题结构和节点关系
- Paper Agent: 论文检索与阅读分析，提取可迁移机制
- Transfer Agent: 算法迁移判断，实验想法生成
- Memory Agent: 长期记忆管理，负面经验提醒
---
```

从 `agent_configs` 表中读取所有 `enabled=True` 的 agent 名称和 description 动态生成。

## 数据模型变更

### AgentConfig 新增字段

```python
description: str = Field(default="")  # 一句话角色描述
```

### DEFAULT_AGENTS 种子数据同步更新

每个 agent 增加 `description` 字段。

## 涉及的模块

| 模块 | 变更类型 |
|------|---------|
| `app/models/agent_config.py` | 新增 description 字段 |
| `app/agents/definitions.py` | 新增 description |
| `app/ui/chat_view.py` | 添加 QCompleter、自动协作开关 |
| `app/services/message_router.py` | **新增** 消息路由模块 |
| `app/ui/worker.py` | ChatWorker 重构，支持多 agent 路由 |
| `app/services/storage.py` | 数据库迁移 |

## 错误处理

- @mention 的 agent 名称在 DB 中不存在：忽略该 mention，消息发给默认 agent
- LLM 调用失败：显示错误消息，不阻塞其他并行 agent
- 自动协作达到最大轮次：停止循环，显示提示
