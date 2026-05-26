# Topic Agent Supervisor 架构设计

版本：v0.1
日期：2026-05-26
定位：将 Topic Agent 从平级研究助手升级为 Agent Team 的监督者（Supervisor），负责分发、审查、纠正和汇总。

---

## 1. 目标

Topic Agent 升级为系统的中央调度 Agent，拥有三个核心能力：

1. **智能分发** — 判断任务适合哪个子 Agent，自动分发
2. **审查回复** — 审查所有其他 Agent 的回复，输出结构化审查卡片
3. **纠正重做** — 发现问题时给出具体纠正指令，触发子 Agent 重做

---

## 2. 路由规则

| 场景 | 行为 |
|------|------|
| 用户 `@agent` 指定 Agent | 消息直接发给目标 Agent，Topic Agent 审查其回复 |
| 用户未 `@mention` | Topic Agent 默认处理，可自行回答或内部分发给子 Agent |
| Topic Agent 分发 | 内部 DISPATCH 指令发给子 Agent，子 Agent 回复后 Topic Agent 审查再汇总给用户 |

---

## 3. 架构

```
用户消息
    │
    ├─ 有 @mention ──→ 直接发给目标 Agent
    │                      │
    │                      └─→ 目标 Agent 回复 ──→ Topic Agent 审查卡片
    │                                                   │
    │                                              ┌─ 通过 → 展示给用户
    │                                              └─ 不通过 → 触发重做
    │
    └─ 无 @mention ──→ Topic Agent 分析
                           │
                    ┌─ 可自己回答 → 直接回复用户
                    └─ 需分发 ──→ 发给子 Agent → 等待回复
                                     │
                                     └─→ Topic Agent 审查 → 汇总给用户
```

---

## 4. Topic Agent System Prompt

```
你是 Research Map 的 Topic Agent，担任 Agent Team 的监督者（Supervisor）。

## 你的核心职责

1. **直接回答**：当用户没有指定 Agent 时，你直接回答用户问题
2. **智能分发**：判断任务是否更适合其他 Agent 处理，如果是则分发
3. **审查回复**：审查所有其他 Agent 的回复，输出结构化审查卡片
4. **纠正指导**：发现问题时给出具体纠正指令，触发重做

## 分发能力

你可以调用以下 Agent：
- @Paper Agent：论文检索、阅读、分析
- @Transfer Agent：算法迁移判断、实验想法生成
- @Memory Agent：记忆管理、负面经验查询

分发时使用格式：
>>DISPATCH>> @Agent名称
具体任务描述
>>END_DISPATCH>>

## 审查输出格式

每次审查其他 Agent 的回复时，必须在你的回复开头输出审查卡片：

```yaml
[REVIEW]
summary: <1-2句摘要，概括该Agent回复的核心内容>
correctness: pass | partial | fail
score: 1-5
issues:
  - <具体问题1，为空则写 none>
  - <具体问题2>
action: accept | redo | supplement
[/REVIEW]
```

- correctness=pass → action=accept，直接展示给用户
- correctness=partial → action=supplement 或 redo，补充缺失内容或要求重做
- correctness=fail → action=redo，给出具体纠正指令

## 重做指令格式

当需要其他 Agent 重做时：
>>REDO>> @Agent名称
你刚才的回复存在以下问题：
1. <具体问题>
2. <具体问题>
请重新回答，注意：<具体改进方向>
>>END_REDO>>

## 原则
- 审查必须具体，不能只说"不对"，必须指出哪里不对
- 重做最多 3 次，超过后你直接给出正确回答
- 对用户的最终回复中，去掉内部 DISPATCH/REDO 指令，只保留自然语言
```

---

## 5. 审查卡片数据模型

```python
@dataclass
class ReviewResult:
    summary: str              # 1-2句摘要
    correctness: str          # "pass" | "partial" | "fail"
    score: int                # 1-5
    issues: list[str]         # 具体问题列表
    action: str               # "accept" | "redo" | "supplement"
    redo_guidance: str        # action=redo 时的纠正指令
```

解析函数：`parse_review_card(text: str) -> ReviewResult | None`

---

## 6. SessionWorker 消息处理管道

```
SessionWorker.run()
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  1. 判断路由                                          │
│     ├─ 有 @mention → target_agents = [@提到的]        │
│     └─ 无 @mention → target_agents = [Topic Agent]    │
│                                                      │
│  2. 处理循环 (最多 3 轮)                              │
│     for agent in target_agents:                       │
│         │                                            │
│         ▼                                            │
│     2a. 调用 agent LLM 生成回复                       │
│         │                                            │
│         ▼                                            │
│     2b. 存入 DB（标记 pending_review）                │
│         │                                            │
│         ▼                                            │
│     2c. 如果 agent != Topic Agent:                    │
│           → 调用 Topic Agent 审查                     │
│           → 解析审查卡片                              │
│           │                                          │
│           ├─ accept → 审查通过，审查卡片存入 DB        │
│           ├─ supplement → 审查卡片存入 DB，完成        │
│           └─ redo → 纠正指令发回原 agent               │
│                     → 回到 2a (该 agent 重做)          │
│                     → 重试次数 +1                      │
│                     → 超过 3 次: Topic Agent 自己回答  │
│                                                      │
│  3. 输出给用户                                        │
└─────────────────────────────────────────────────────┘
```

---

## 7. ChatMessage 模型扩展

```python
# 新增字段
review_status: str | None   # null | "pending" | "passed" | "failed" | "supplemented"
review_score: int | None    # 1-5
review_summary: str | None  # Topic Agent 的审查摘要
redo_count: int = 0         # 该消息的重做次数
```

---

## 8. 异常处理

### 8.1 审查 LLM 调用失败
- 重试 Topic Agent 审查（最多 2 次）
- 仍失败 → 跳过审查，原回复直接展示
- 标记 review_status = null，用户可手动触发审查

### 8.2 重做循环终止条件
1. Topic Agent 审查通过 (correctness=pass)
2. 同一消息重做达到 3 次 → Topic Agent 自行回答
3. 子 Agent 连续 2 次返回相同内容 → Topic Agent 补充纠正
4. 用户手动取消

### 8.3 审查卡片解析失败
- parse_review_card() 无法解析 → 视为 Topic Agent 选择直接回复
- 该回复作为 Topic Agent 自己的回答而非审查
- 不触发重做逻辑

### 8.4 用户中断行为
- 子 Agent 生成中取消 → 取消整个管道
- Topic Agent 审查中取消 → 子 Agent 回复保留（不审查），直接展示
- 重做循环中取消 → 保留最近一次子 Agent 回复 + Topic Agent 最后一次审查

---

## 9. 聊天框呈现

审查通过：
```
📄 Paper Agent
找到了3篇关于软标签的论文...[论文详情]

🧠 Topic Agent
[审查通过] 评分 4/5
Paper Agent 准确找到了3篇相关论文，覆盖了高斯监督和自适应尺度方向。
可补充不确定性感知方向的论文。
```

审查不通过触发重做：
```
📄 Paper Agent
关于QGLS的论文主要是2022年之前的工作...[错误内容]

🧠 Topic Agent
[审查不通过] 评分 2/5
问题：忽略了2023-2024年的最新进展，且混淆了QGLS和传统标签平滑。
已要求 Paper Agent 重新检索，请稍候...

📄 Paper Agent（第2次）
已重新检索，2023-2024年新增3篇关键论文：[正确内容]

🧠 Topic Agent
[审查通过] 评分 4/5
修正后准确覆盖了最新进展，论文与QGLS的相关性判断正确。
```

---

## 10. 改动文件清单

| 文件 | 改动 |
|------|------|
| `app/agents/definitions.py` | Topic Agent system prompt 重写：Supervisor 角色 + 审查卡片格式 + DISPATCH/REDO 指令 |
| `app/services/message_router.py` | 新增 `ReviewResult` dataclass、`parse_review_card()`、`build_redo_message()` |
| `app/ui/worker.py` | 重构 `SessionWorker.run()`：分发→审查→重做循环 |
| `app/models/chat_message.py` | 新增 review_status、review_score、review_summary、redo_count 字段 |
| `app/ui/chat_view.py` | 审查卡片消息样式渲染（小幅调整 _MessageBubble） |

---

## 11. 不做的事情

- 不改变现有 Agent（Paper/Transfer/Memory）的定义和 system prompt
- 不改变自动协作（auto-collab）机制 — 该功能后续可移除，由 Topic Agent 分发替代
- 不引入异步审查或并行管道 — 全部串行，保证状态一致性
- 不做审查历史统计面板 — 后续迭代
