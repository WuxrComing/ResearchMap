# Research Map Agent 第一版开发规格说明（SPEC）

版本：v0.1  
定位：Python 优先的动态科研思维导图与前沿监控 Agent  
建议技术栈：NiceGUI + FastAPI + SQLite + Cytoscape.js + APScheduler + Pydantic + openai/LLM structured output

---

## 1. 产品目标

Research Map Agent 面向科研选题、论文跟踪和算法创新过程。用户输入一个研究课题或论文题目后，系统利用大模型自动扩展为一张动态研究思维导图，并以该导图作为后续所有工作的核心知识结构。

此后，系统通过定时任务持续检索最新论文、代码仓库、研究动态与相关领域进展，提取每项工作的核心理论、设计哲学、方法机制和可迁移思想，并将其挂载到思维导图中的相应节点。用户可以通过界面查看整个课题结构、节点热度、代表论文、可转化实验想法和负面实验记忆，也可以随时通过右侧 LLM 对话区追问、扩展节点、要求解释论文价值或生成实验方案。

核心目标不是“推荐论文”，而是帮助用户形成一个持续演化的课题认知系统。

---

## 2. 第一版核心原则

第一版不追求完整文献管理系统，也不追求复杂前端工程，而是优先跑通以下闭环：

```text
用户输入研究课题
    ↓
LLM 生成初始思维导图
    ↓
系统保存为 Topic Map
    ↓
定时或手动检索最新论文
    ↓
LLM 提取论文核心思想
    ↓
LLM 判断论文应挂载到哪个节点
    ↓
更新思维导图、论文库、想法库和负面记忆
    ↓
用户通过图谱与右侧对话持续交互
```

第一版的交互核心是：

```text
左侧：课题列表与记忆状态
中央 Tab 1：完整思维导图 (Cytoscape.js)
中央 Tab 2：Agent Team 对话 (多 Agent 头像 + 消息流)
底部：最新挂载、实验想法、负面记忆提醒
```

---

## 3. 目标用户

### 3.1 主要用户

- 博士生、硕士生、科研人员；
- 正在做算法改进、论文选题、文献综述或研究计划的人；
- 希望持续跟踪前沿论文，并将其转化为研究假设或实验方案的人。

### 3.2 典型场景

1. 用户输入课题：  
   “小目标检测中的定位监督增强方法研究”。

2. 系统生成初始思维导图：  
   包括核心问题、方法路线、机制思想、相关论文、可迁移方向、待验证问题、失败经验等。

3. 系统每天扫描最新论文：  
   从 arXiv、Semantic Scholar、OpenAlex、GitHub、huggingface 等来源获取最新内容。

4. 系统自动分类：  
   将新论文挂载到“软标签 / 高斯监督”“标签分配优化”“可迁移思想”等节点。

5. 用户点击节点或在右侧对话提问：  
   “为什么 QGLS 对小目标更有效？”  
   “最近哪些论文可以支持这个判断？”  
   “这个节点还能扩展哪些方向？”  
   “把这个想法转化为一个实验方案。”

---

## 4. 第一版界面设计

第一版界面应模仿 Codex 客户端的干净布局：左侧导航、中央工作区、右侧交互面板。避免过度复杂的统计面板，突出完整思维导图和人机协作。

---

### 4.1 整体布局

第一版采用左侧栏 + 中央工作区（Tab 切换）+ 底部卡片的布局。思维导图和 Agent 对话区共享中央区域，通过 Tab 切换，确保各自都能获得完整的展示空间。

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Top Bar: breadcrumb + search + run scan + export + notification + user       │
├───────────────┬──────────────────────────────────────────────────────────────┤
│ Left Sidebar  │ Center Workspace (TabControl)                                │
│               │ ┌──────────────────────────────────────────────────────────┐ │
│ Topic List    │ │ [ 思维导图 ]  [ Agent 对话 ]                              │ │
│ Memory Status │ ├──────────────────────────────────────────────────────────┤ │
│ Settings      │ │                                                          │ │
│               │ │  Tab 1: Complete Mind Map (Cytoscape.js)                 │ │
│               │ │  Tab 2: Agent Team Chat (multi-agent, avatar-based)      │ │
│               │ │                                                          │ │
│               │ │  Bottom Action Cards                                     │ │
│               │ └──────────────────────────────────────────────────────────┘ │
└───────────────┴──────────────────────────────────────────────────────────────┘
```

设计理由：
- 思维导图需要大面积渲染，聊天区需要容纳多 Agent 头像和长对话——两者都需要完整空间
- Tab 切换避免信息过载，用户在"看图"和"对话"两个模式间切换
- 为后续 Agent Team 多角色对话预留扩展空间（每个 Agent 有独立头像和消息样式）

---

## 5. 左侧栏规格

### 5.1 顶部品牌区

显示：

```text
Research Map
动态科研思维导图
```

配一个节点图标或网络图标。

### 5.2 新建课题按钮

按钮文案：

```text
+ 新建课题
```

点击后打开新建课题弹窗。

### 5.3 我的课题列表

每个课题卡片包含：

- 课题名称；
- 简短描述；
- 最近更新时间；
- 当前选中状态。

示例：

```text
小目标检测中的定位监督增强
今日 08:30

红外小目标多帧时序融合
昨日 22:10

国家发展规划经济学知识体系
5月24日
```

### 5.4 记忆状态

简化展示，不要做复杂仪表盘。

显示：

```text
记忆状态
4,253 条记忆
同步中
23% 已用
```

后续可扩展：

- 项目长期记忆；
- 负面实验记忆；
- 信念图谱节点数；
- 论文库数量。

---

## 6. 顶部栏规格

顶部栏包含：

### 6.1 面包屑

```text
课题地图 / 小目标检测中的定位监督增强
```

### 6.2 搜索框

占据顶部中间区域。

placeholder：

```text
搜索课题、论文、节点或对话…
```

搜索范围：

- 课题；
- 思维导图节点；
- 论文；
- 想法；
- 负面记忆；
- 聊天记录。

### 6.3 右侧操作按钮

包含：

```text
运行扫描
导出 (PNG / JSON)
通知铃铛
用户头像
```

第一版中，”运行扫描”触发当前课题的即时论文扫描任务。
导出功能第一版仅支持：思维导图导出为 PNG（Cytoscape.js 内置截图），以及节点+边数据导出为 JSON（可移植备份）。不做 Markdown 报告或 LaTeX 文献综述导出。

---

## 7. 中央完整思维导图区域

中央区域是产品最重要的部分。第一版用一张完整思维导图展示整个课题，不再强调”问题层 / 方法层 / 机制层”的切换。

渲染引擎第一版直接使用 **Cytoscape.js**（不经过 PyVis 过渡）。通过 NiceGUI 的 `ui.html()` 嵌入自定义 HTML/JS，确保完整的节点点击回调、动态更新和自定义样式能力。Cytoscape.js 自带的布局算法、事件系统和插件生态比 PyVis 更适合本产品的长期演进。

### 7.1 思维导图卡片标题

```text
完整思维导图
自动更新中
最新扫描已同步
```

### 7.2 右上角控件

包含：

- 适配视图；
- 缩小；
- 放大；
- 布局切换 (分层布局 ↔ 力导向布局)；
- 导出 PNG。

### 7.3 布局算法

随着论文入图，节点数量会持续增长（可能 200-500+）。手动布局不可行，第一版内置两种自动布局：

- **分层布局 (Breadthfirst / Hierarchical)**：从 root 向外层级展开，适合初始思维导图和结构清晰的课题；
- **力导向布局 (CoLa / Cose)**：节点根据连接权重自然聚类，适合论文挂载后呈现研究热点的自然聚集。

用户可以在右上角控件切换布局。Cytoscape.js 自带这两种布局实现，无需额外开发。

### 7.4 信念强度可视化

第一版引入简化的"信念图谱"概念。每个节点的 `evidence_strength` 根据如下规则动态计算：

- **strong**：挂载 5+ 篇高质量论文，且无挑战性论文；
- **medium**：挂载 1-4 篇论文，或有少量争论；
- **weak**：仅有推测性连接，或存在多篇挑战论文。

信念强度在节点颜色深浅和边框样式上可视化：
- strong：实心、深色、粗边框；
- medium：实心、正常色；
- weak：虚线边框、浅色。

论文与节点的关系不仅限于 `belongs_to`，还可以标记为 `supports`（支持）或 `challenges`（挑战），直接参与信念计算。

### 7.5 中心节点

中心节点为当前课题核心。

示例：

```text
小目标定位监督增强
```

### 7.6 一级节点

第一版建议内置以下节点类型：

```text
核心问题
方法路线
核心机制
软标签 / 高斯监督
标签分配优化
有效定位梯度稀疏
正样本支持区域窄
可迁移思想
实验想法
相关论文
失败经验
待验证问题
```

### 7.7 节点内容

每个节点至少包含：

- 节点名称；
- 节点类型；
- 简短子描述；
- 热度；
- 成熟度；
- 论文数量；
- 证据强度；
- 更新时间。

示例：

```yaml
node_id: n_soft_gaussian
name: 软标签 / 高斯监督
type: method
summary: 通过连续标签或高斯分布扩大有效监督区域。
heat: high
maturity: developing
paper_count: 36
evidence_strength: medium
last_updated: 2026-05-26
```

### 7.8 节点类型与颜色建议

```text
root: 深蓝 / 深灰
problem: 蓝色
method: 紫色
mechanism: 橙色
paper: 黄色
idea: 绿色
experiment: 紫色
risk: 红色
open_question: 浅蓝
```

### 7.9 点击节点行为

用户点击任一节点后：

1. 中央底部显示该节点的简短摘要；
2. 系统自动将该节点设为对话上下文（切换到 Agent 对话 Tab 后自动带入）；
3. 底部卡片刷新为该节点相关内容；
4. 用户可以在 Agent 对话 Tab 中继续提问。

示例交互：

```text
用户点击”软标签 / 高斯监督”
系统在 Agent 对话 Tab 中提示：
“已选中节点：软标签 / 高斯监督。你可以询问该节点的理论依据、代表论文、可迁移实验或风险。”
```

---

## 8. Agent Team 对话面板

对话面板位于中央工作区的第二个 Tab，与思维导图共享中央区域。第一版引入简化的 **Agent Team** 概念：系统包含多个角色 Agent，每个 Agent 有独立头像和职责，以消息流形式呈现对话。

### 8.1 第一版内置 Agent 角色

| Agent | 头像标识 | 职责 |
|-------|---------|------|
| **Topic Agent** | 🧠 深蓝圆形 | 回答课题结构、节点关系、思维导图导航 |
| **Paper Agent** | 📄 黄色圆形 | 查找、解释、比较论文，报告最新检索结果 |
| **Transfer Agent** | 💡 绿色圆形 | 分析算法迁移潜力，生成实验方案草稿 |
| **Memory Agent** | 🗂 灰色圆形 | 管理长期记忆、负面记忆、扫描日志 |

后续版本允许用户自定义 Agent 角色。

### 8.2 面板标题

```text
Agent Team
Topic Agent / Paper Agent / Transfer Agent / Memory Agent 已在线
```

### 8.3 消息流格式

每条消息显示：Agent 头像 + Agent 名称 + 消息内容。

示例对话：

```text
┌─────────────────────────────────────────────────────────┐
│ 🧠 Topic Agent                                          │
│ 当前课题：小目标定位监督增强。思维导图共有 47 个节点，  │
│ 其中 12 个节点在过去一周有更新。                         │
│                                                         │
│ 👤 用户                                                 │
│ 请解释为什么 QGLS 对小目标更有效？                       │
│                                                         │
│ 📄 Paper Agent                                          │
│ 因为它通过高斯式软标签扩大了有效定位监督区域，使原本     │
│ 稀疏的定位梯度更加连续，能更充分地提供边界与位置信息，   │
│ 缓解小目标训练中的梯度稀疏与正样本不足问题。             │
│ 相关论文：Scale-adaptive Dense Supervision (arXiv 2024)  │
│                                                         │
│ 👤 用户                                                 │
│ 那最近有哪些论文可以支持这个判断？                       │
│                                                         │
│ 📄 Paper Agent                                          │
│ 最近可重点关注尺度自适应监督、不确定性感知分配，以及     │
│ 查询引导定位蒸馏等方向。                                 │
│ 我已将这 3 篇新论文挂载到”可迁移思想”与”软标签”节点。   │
│                                                         │
│ 💡 Transfer Agent                                       │
│ 检测到可迁移模式。基于 QGLS 思想，我可以草拟一个         │
│ Adaptive-QGLS 实验方案，是否需要？                       │
└─────────────────────────────────────────────────────────┘
```

### 8.4 输入框

placeholder：

```text
向 Agent Team 提问，或使用斜杠命令…（/expand-node /find-papers /create-experiment /write-memory /add-negative-memory /rebuild-map）
```

支持动作：

- 普通问答（自动路由到最相关的 Agent）；
- `@Topic Agent` 扩展当前节点；
- `@Paper Agent` 查找支持/挑战论文；
- `@Transfer Agent` 生成实验方案；
- `@Memory Agent` 写入长期记忆 / 负面记忆 / 查询历史。

### 8.5 内置斜杠命令

```text
/expand-node        扩展当前选中节点
/find-papers        查找相关论文
/create-experiment  生成实验方案
/write-memory       写入长期记忆
/add-negative-memory 写入负面记忆
/rebuild-map        重构当前思维导图
@agent-name         指定 Agent 回答
```

### 8.6 用户纠错反馈机制

用户可以对 Agent 的输出进行纠正，这是系统持续进化的关键：

- **论文分类纠错**：用户在思维导图中将论文拖拽到正确节点，或通过 `@Topic Agent 将论文 X 移动到节点 Y` 纠正；
- **错误分类作为反例**：被纠正的分类记录存入 `NegativeMemory`，作为后续 Map Classifier 的 few-shot 反例参考；
- **节点审核队列**：用户可以在左侧栏查看”待审核”的论文挂载，批量确认或修正。

---

## 9. 底部工作区

底部工作区保持轻量，不能抢占中央思维导图的视觉中心。

第一版保留三个卡片：

### 9.1 最新挂载

展示最近被加入思维导图的论文。

字段：

- 论文标题；
- 来源；
- 日期；
- 挂载节点。

示例：

```text
Scale-adaptive Dense Supervision
arXiv 2024.05.12

Query-guided Localization Distillation
CVPR 2024

Uncertainty-aware Assignment
arXiv 2024.03.08
```

### 9.2 可转化实验想法

展示可进入算法实验的想法。

示例：

```text
Adaptive-QGLS
结合自适应高斯半径与查询引导，动态调整监督强度。

DETR-to-CNN定位蒸馏
将 DETR 的查询定位能力蒸馏到 CNN 检测器。
```

### 9.3 负面记忆提醒

展示历史失败路线和风险提醒。

示例：

```text
避免重复进入 CA-QGLS 路线

历史实验表明：多阶段级联训练导致收益趋缓，模型对超参敏感，且训练不稳定、收敛波动大。
```

---

## 10. 核心功能模块

第一版建议实现以下 8 个模块。

---

### 10.1 Topic Builder：课题初始化模块

输入：

```text
用户输入研究课题或题目
```

输出：

```text
初始 Topic Map
节点列表
边列表
初始检索关键词
初始研究问题
```

LLM 任务：

1. 理解用户课题；
2. 扩展核心问题；
3. 扩展方法路线；
4. 扩展相关领域；
5. 扩展可迁移思想；
6. 生成初始思维导图；
7. 生成检索关键词。

输出格式必须结构化，建议使用 Pydantic schema。

---

### 10.2 Topic Map Manager：思维导图管理模块

负责：

- 创建节点；
- 更新节点；
- 删除节点；
- 合并节点；
- 创建边；
- 更新边；
- 根据新论文调整节点热度；
- 根据用户反馈重构图谱。

支持四种核心更新动作：

```text
Attach：将论文挂载到已有节点
Expand：在已有节点下新增子节点
Merge：合并重复节点
Promote：将重要子节点提升为主节点
```

---

### 10.3 Paper Retriever：论文检索模块

第一版支持：

- arXiv API（通过 feedparser 解析 RSS/Atom）；
- Semantic Scholar API；
- GitHub repository 搜索；
- 手动导入论文标题 / PDF / URL。

OpenAlex 可后置。arXiv 和 Semantic Scholar 均有 rate limit，第一版需实现简单的速率控制（请求间隔不低于 3s）和 HTTP 缓存（etag/last-modified）。

检索输入来自：

```text
Topic Map 中的重要节点
+
节点关键词
+
用户自定义关键词
```

不是只用用户原始 topic 检索。

**预过滤层**：在送入 Paper Reader（LLM）之前，先用轻量方法过滤低相关性论文以降低 LLM 成本：

1. 用 sentence-transformers 计算论文摘要与各节点的 embedding 余弦相似度；
2. 所有节点相似度均低于阈值的论文直接丢弃；
3. 只有至少命中一个节点的论文进入 Paper Reader 深度处理。

预期预过滤可减少 60-80% 的 LLM 调用量。embedding 模型建议使用 `all-MiniLM-L6-v2`（轻量、本地运行）。

---

### 10.4 Paper Reader：论文理解模块

对每篇论文提取：

```yaml
title:
authors:
year:
source:
abstract:
problem:
method:
core_idea:
design_philosophy:
mechanism:
experiment_evidence:
limitations:
related_nodes:
transfer_potential:
risk:
summary_for_user:
```

注意：第一版可以先只基于 title + abstract + metadata 做初筛，只有高分论文再抓取 PDF 或全文。

---

### 10.5 Map Classifier：论文入图模块

对每篇论文判断：

```text
应挂载到哪个节点？
挂载关系类型：belongs_to / supports / challenges？
是否需要新增节点？
是否强化已有节点？
是否降低某个节点优先级？
是否进入可转化实验想法？
是否进入负面记忆？
```

`supports` 和 `challenges` 关系直接影响节点的 `evidence_strength` 计算（见 7.4 节）。

输出示例：

```yaml
paper_id: p001
main_action: attach
relation_type: supports
target_nodes:
  - n_soft_gaussian
  - n_transfer_idea
reason: 论文提出尺度自适应密集监督，与软标签和QGLS思想高度相关。
new_node: null
transfer_potential: high
risk_level: medium
```

**用户反馈闭环**：Map Classifier 的分类结果并非最终。用户可通过以下方式纠正：
- 在思维导图中拖拽论文到正确节点；
- 在 Agent 对话中通过 `@Topic Agent 将论文 X 移动到节点 Y` 纠正；
- 被纠正的分类记录存入 NegativeMemory，作为后续 Map Classifier 的 few-shot 反例；
- 左侧栏提供"待审核挂载"列表，用户可批量确认或修正。

---

### 10.6 Transfer Agent：算法迁移判断模块

第一版 Transfer Agent 定位为"实验想法生成器"，不做定量预测。对论文或节点输出：

```text
是否可以迁移到当前算法？（yes / maybe / unlikely）
应该迁移到哪个模块？
核心思路是什么？
预期的定性收益是什么？
主要风险是什么？
```

示例输出：

```yaml
idea_name: Adaptive-QGLS
transferability: maybe
target_module: label_generation
core_idea: 将固定高斯半径替换为基于目标尺度的自适应半径
qualitative_gain:
  - 多尺度小目标定位梯度更均衡
  - 减少背景噪声干扰
risk:
  - 高斯半径过大可能引入背景噪声
  - 尺度估计误差可能传递到标签生成
```

注意第一版不自动输出定量指标预期（APs +X% 等）和完整消融实验计划。这些属于高幻觉场景，应留给用户在 Agent 对话中按需追问（例如 `@Transfer Agent 帮我制定这个想法的消融实验计划`）。

---

### 10.7 Memory Manager：记忆管理模块

第一版记忆分为五类：

```text
Project Memory：课题长期记忆
Daily Memory：每日扫描日志
Paper Memory：论文结构化记忆
Idea Memory：可转化想法记忆
Negative Memory：负面经验记忆
```

存储方式：

```text
结构化数据：SQLite（Topic/Node/Edge/Paper/Idea/NegativeMemory 主存储）
全文搜索：SQLite FTS5（搜索论文标题、节点名、聊天记录等短文本）
用户可读记忆：storage/app_memory/ 目录下的 Markdown 日志
向量检索：Chroma / Qdrant，后续加入
```

**重要**：`storage/app_memory/` 与 Claude Code 的 `~/.claude/projects/.../memory/` 系统完全分离。前者是应用数据（科研记忆），后者是 Claude 的会话持久化机制。两个目录不应混淆。

---

### 10.8 Chat Agent：右侧研究助手

负责：

- 回答用户关于当前课题的问题；
- 解释当前节点；
- 查找相关论文；
- 总结思维导图；
- 扩展节点；
- 生成实验方案；
- 将对话结论写入记忆；
- 调用 Map Manager 更新图谱。

Chat Agent 必须始终带入上下文：

```text
当前课题
当前选中节点
Topic Map 结构
相关论文
历史记忆
负面记忆
用户当前问题
```

---

## 11. 数据模型设计

第一版建议使用 SQLite + SQLAlchemy / SQLModel。

---

### 11.1 Topic

```python
class Topic:
    id: str
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    status: str
```

---

### 11.2 MapNode

```python
class MapNode:
    id: str
    topic_id: str
    name: str
    type: str  # root/problem/method/mechanism/paper/idea/experiment/risk/open_question
    summary: str
    heat: str  # low/medium/high/rising
    maturity: str  # emerging/developing/mature/declining
    evidence_strength: str  # weak/medium/strong
    paper_count: int
    position_x: float
    position_y: float
    created_at: datetime
    updated_at: datetime
```

---

### 11.3 MapEdge

```python
class MapEdge:
    id: str
    topic_id: str
    source_node_id: str
    target_node_id: str
    relation: str  # supports/addresses/extends/contradicts/transfers_to
    weight: float
    created_at: datetime
```

---

### 11.4 Paper

```python
class Paper:
    id: str
    title: str
    authors: list[str]
    year: int
    source: str
    url: str
    abstract: str
    summary: str
    core_idea: str
    design_philosophy: str
    mechanism: str
    evidence_quality: str
    transfer_potential: str
    risk_level: str
    created_at: datetime
```

---

### 11.5 PaperNodeLink

```python
class PaperNodeLink:
    id: str
    paper_id: str
    node_id: str
    relation: str  # belongs_to/supports/extends/challenges
    confidence: float
    reason: str
```

---

### 11.6 Idea

```python
class Idea:
    id: str
    topic_id: str
    node_id: str
    name: str
    description: str
    origin_paper_ids: list[str]
    target_module: str
    expected_gain: list[str]
    implementation_cost: str
    risk: str
    priority: str
    status: str  # candidate/planned/testing/failed/accepted
```

---

### 11.7 NegativeMemory

```python
class NegativeMemory:
    id: str
    topic_id: str
    title: str
    description: str
    failed_reason: str
    avoid_rule: str
    related_nodes: list[str]
    created_at: datetime
```

---

### 11.8 ChatMessage

```python
class ChatMessage:
    id: str
    topic_id: str
    node_id: str | None
    role: str  # user/assistant/system
    content: str
    created_at: datetime
```

---

## 12. Agent 工作流

---

### 12.1 新建课题流程

```text
用户点击“新建课题”
    ↓
输入课题名称与简单描述
    ↓
Topic Builder 调用 LLM
    ↓
生成初始 Topic Map JSON
    ↓
保存 Topic / Nodes / Edges
    ↓
在中央思维导图展示
    ↓
右侧 Chat Agent 给出初始化说明
```

LLM 输出必须包含：

```yaml
topic:
  title:
  description:
nodes:
  - id:
    name:
    type:
    summary:
edges:
  - source:
    target:
    relation:
search_queries:
  - query:
open_questions:
  - question:
```

---

### 12.2 手动扫描流程

```text
用户点击“运行扫描”
    ↓
Paper Retriever 根据 Topic Map 生成检索 query
    ↓
检索论文元数据
    ↓
去重
    ↓
Paper Reader 粗读摘要
    ↓
Map Classifier 判断入图方式
    ↓
更新 Topic Map
    ↓
生成扫描摘要
    ↓
右侧 Chat Agent 汇报结果
```

---

### 12.3 定时扫描流程

第一版使用 APScheduler。

默认计划：

```text
每日 08:00：轻量扫描
每周日 20:00：深度汇总
每月最后一天：图谱重构建议
```

第一版只需实现每日扫描和手动扫描。

---

### 12.4 用户追问流程

```text
用户在右侧聊天输入问题
    ↓
Chat Agent 获取当前 topic_id 和 selected_node_id
    ↓
查询 Topic Map、相关论文、记忆
    ↓
调用 LLM 生成回答
    ↓
若用户要求更新图谱，则调用 Map Manager
    ↓
保存聊天记录
```

---

## 13. LLM 调用可靠性机制

### 13.0 结构化输出与重试策略

所有关键 LLM 调用（Topic Builder、Paper Reader、Map Classifier、Transfer Agent）必须使用结构化输出 API（OpenAI `response_format={"type": "json_schema"}` 或等效的 function calling），不允许自由格式 prompt + 手工解析。

每条 LLM 调用必须包含：

```text
1. Pydantic schema 定义目标输出结构
2. 最多 3 次重试 + exponential backoff (1s / 2s / 4s)
3. Schema 校验失败 → 自动重试（将校验错误信息作为下一条消息反馈给 LLM）
4. 3 次均失败 → 该论文/操作进入人工审核队列，不静默丢弃
```

失败队列存储位置：

```text
storage/pending_review/
  failed_classifications.jsonl
  failed_paper_reads.jsonl
```

用户可在左侧栏"待审核"入口查看并手动处理。

### 13.1 LLM 成本控制

第一版 LLM 调用量预估（以中等课题、每天 30 篇新论文为例）：

| 步骤 | 模型 | 每篇 token 估算 |
|------|------|----------------|
| 预过滤 (embedding) | all-MiniLM-L6-v2 (本地) | 免费 |
| Paper Reader | GPT-4o-mini / DeepSeek | ~800 input + ~300 output |
| Map Classifier | GPT-4o-mini / DeepSeek | ~500 input + ~150 output |
| Transfer Agent | GPT-4o / DeepSeek-R1 | ~1000 input + ~400 output（仅高分论文触发） |

预过滤后预计每天 6-12 篇进入 LLM 处理，日均 LLM 成本 $0.10-$0.50。

---

## 14. LLM Prompt 设计

---

### 14.1 Topic Builder Prompt

目标：把用户输入课题扩展为初始思维导图。

输入：

```text
用户课题：
{topic_title}

用户补充说明：
{topic_description}
```

输出要求：

```text
请生成一个研究思维导图 JSON，包含核心问题、方法路线、核心机制、相关领域、代表论文类型、可迁移思想、实验想法、失败风险、待验证问题。
```

---

### 14.2 Paper Reader Prompt

目标：提取论文核心思想。

输入：

```text
论文标题：
{title}

摘要：
{abstract}

当前课题：
{topic_title}

当前思维导图节点：
{nodes}
```

输出：

```yaml
problem:
method:
core_idea:
design_philosophy:
mechanism:
limitations:
transfer_potential:
risk:
suggested_nodes:
reason:
```

---

### 14.3 Map Classifier Prompt

目标：决定论文如何入图。

输出动作限定为：

```text
attach
expand
merge
promote
ignore
negative
```

示例：

```yaml
action: attach
target_nodes:
  - n_soft_gaussian
  - n_transfer_idea
reason: 该论文提出尺度自适应密集监督，与软标签高斯监督节点高度相关。
confidence: 0.87
```

---

### 14.4 Chat Agent Prompt

系统提示应包括：

```text
你是 Research Map Agent 的研究助手。你需要基于当前课题思维导图、节点信息、论文记忆、负面记忆和用户问题回答。你的目标不是泛泛解释，而是帮助用户理解课题结构、前沿动态和可迁移算法想法。
```

回答时应优先：

1. 解释当前节点；
2. 结合已有论文；
3. 说明与课题的关系；
4. 判断是否能转化为实验；
5. 必要时建议更新思维导图。

---

## 15. 技术选型

---

### 15.1 第一版推荐组合

```text
Python 3.11+
NiceGUI
FastAPI
SQLite + SQLAlchemy / SQLModel + FTS5
Pydantic
Cytoscape.js (通过 NiceGUI ui.html() 嵌入)
sentence-transformers (all-MiniLM-L6-v2, 论文预过滤)
APScheduler (AsyncIOScheduler)
httpx
feedparser
openai / deepseek / anthropic SDK (带 structured output / function calling)
```

### 15.2 第二版升级

```text
SQLite → PostgreSQL
Chroma → Qdrant (向量记忆)
普通页面 → PySide6 + QWebEngineView 桌面壳
内置 Agent Team → LangGraph 多 Agent 可编排工作流
静态信念 → 动态 Research Belief Graph（信念随时间衰减/强化）
```

---

## 16. 推荐项目结构

```text
research-map-agent/
  README.md
  SPEC.md
  pyproject.toml
  .env.example

  app/
    main.py                  # NiceGUI 应用入口
    api.py                   # FastAPI 路由
    config.py

  ui/
    layout.py                # 主布局（含 TabControl）
    sidebar.py               # 左侧栏
    topbar.py                # 顶部栏
    map_view.py              # 思维导图组件（Cytoscape.js 嵌入）
    chat_panel.py            # Agent Team 对话面板
    bottom_cards.py          # 底部卡片
    cytoscape/
      graph.html             # Cytoscape.js HTML 模板
      graph.js               # 图谱渲染、事件、布局逻辑
      style.css              # 节点颜色、信念强度样式

  agents/
    topic_builder.py         # 课题扩展
    paper_retriever.py       # 论文检索 + 预过滤
    paper_reader.py          # 论文理解
    map_classifier.py        # 入图分类 + supports/challenges
    transfer_agent.py        # 迁移判断（实验想法生成）
    memory_manager.py        # 记忆管理
    chat_agent.py            # Agent Team 对话路由

  models/
    topic.py
    map_node.py
    map_edge.py
    paper.py
    paper_node_link.py
    idea.py
    negative_memory.py
    chat_message.py

  services/
    llm.py                   # LLM 调用封装（结构化输出 + 重试）
    llm_schemas.py           # Pydantic output schemas
    scheduler.py             # APScheduler (AsyncIOScheduler)
    paper_sources.py         # arXiv / Semantic Scholar
    prefilter.py             # embedding 预过滤
    storage.py               # DB 初始化 + FTS5 索引
    search.py                # 全局搜索

  storage/
    research_map.db
    app_memory/              # 应用科研记忆（与 Claude memory 分离）
      research_notes/
      negative_logs/
      daily_scans/
    pending_review/           # LLM 失败队列
      failed_classifications.jsonl
      failed_paper_reads.jsonl

  desktop/
    shell.py                 # 后续 PySide6 桌面封装

  tests/
    test_topic_builder.py
    test_map_classifier.py
    test_paper_reader.py
    test_prefilter.py
```

---

## 17. MVP 开发顺序

建议按照以下顺序实现。

### 第一步：本地 UI 骨架

目标：

```text
左侧课题栏
中央思维导图占位
右侧聊天面板
底部三张卡片
```

先用假数据。

### 第二步：SQLite 数据模型

实现：

```text
Topic
MapNode
MapEdge
Paper
PaperNodeLink
Idea
NegativeMemory
ChatMessage
```

### 第三步：Topic Builder

实现用户输入课题后生成初始思维导图。

第一版可以不追求完美布局，只要能生成节点和边。

### 第四步：思维导图渲染

使用 Cytoscape.js 嵌入 NiceGUI（`ui.html()`）：

```text
节点显示 + 边显示 + 颜色区分（节点类型）
信念强度可视化（边框/透明度）
节点点击 → 选中态 + 上下文传递
分层布局 + 力导向布局切换
适配视图 / 缩放
导出 PNG
```

### 第五步：Agent Team 对话

实现：

```text
多 Agent 角色（Topic / Paper / Transfer / Memory）
Agent 头像 + 消息流 UI
用户输入自动路由到合适 Agent
斜杠命令支持
聊天记录持久化
在当前选中节点上下文中对话
```

### 第六步：论文检索

先实现 arXiv 检索。

输入：

```text
topic search queries
```

输出：

```text
title
abstract
authors
url
published
```

### 第七步：论文入图

实现：

```text
Paper Reader
Map Classifier
PaperNodeLink
底部最新挂载更新
```

### 第八步：手动扫描

点击“运行扫描”，完成一次：

```text
检索 → 阅读 → 分类 → 入图 → 汇报
```

### 第九步：定时扫描

加入 APScheduler。

---

## 18. 第一版验收标准

第一版完成后，应满足以下标准：

### 18.1 界面标准

- 有左侧课题栏；
- 有中央 TabControl（思维导图 Tab + Agent Team 对话 Tab）；
- 思维导图使用 Cytoscape.js，支持节点点击、缩放、布局切换和信念强度可视化；
- Agent 对话支持多 Agent 头像和消息流；
- 有底部最新挂载、实验想法、负面记忆；
- 整体风格接近 Codex 客户端，简洁、留白充足。

### 18.2 功能标准

- 用户可以创建新课题；
- 系统可以生成初始思维导图；
- 用户可以点击节点；
- 用户可以与右侧 LLM 对话；
- 系统可以执行一次手动论文扫描；
- 系统可以将新论文挂载到思维导图节点；
- 系统可以保存论文、节点、聊天和想法；
- 系统可以显示负面记忆提醒。

### 18.3 数据标准

至少保存：

```text
1 个 topic
10 个以上节点
10 条以上边
若干论文记录
论文与节点的挂载关系
聊天记录
可转化实验想法
负面记忆
```

### 18.4 Agent 标准

LLM 输出必须结构化，使用 `response_format` / function calling，不允许纯自然语言直接写入数据库。所有关键动作必须通过 Pydantic schema 校验。校验失败自动重试（最多 3 次），3 次均失败进入人工审核队列，不静默丢弃。

---

## 19. 后续迭代方向

### 19.1 更强图谱能力

- 节点折叠/展开；
- 节点拖拽保存位置；
- 节点热度随时间变化；
- 节点合并建议；
- 图谱版本回滚；
- 图谱导出为 PNG / Markdown / JSON。

### 19.2 更强论文能力

- PDF 全文解析；
- 论文图表理解；
- 引用网络；
- 代码仓库分析；
- benchmark 趋势跟踪；
- 自动生成 related work 草稿。

### 19.3 更强记忆能力

- 动态 Research Belief Graph（信念随时间衰减/强化，自动更新置信度）；
- 负面实验自动提醒（类似代码 lint，触发相似实验提案时自动警告）；
- 历史判断置信度更新（当新论文挑战旧结论时，信念自动降低）；
- 论文对已有信念的持续支持或反驳追踪。

### 19.4 更强实验辅助

- 自动生成实验计划；
- 自动生成 ablation table；
- 自动生成训练配置；
- 与 GitHub / 本地代码库连接；
- 将论文想法转化为 issue / TODO。

---

## 20. 第一版不做的事情

为了避免 MVP 过重，第一版暂不做：

```text
复杂 PDF 图表解析
自动修改代码 / 自动运行实验
多用户协作 / 在线部署权限系统
复杂 citation graph
完整桌面封装（PySide6 + QWebEngineView）
大规模向量数据库（Chroma / Qdrant）
基于 PDF 全文的深度论文解析（仅基于 title + abstract + metadata）
Markdown / LaTeX 文献综述报告导出
定量实验指标预测（AP +X% 等）和完整消融计划自动生成
```

这些可以作为第二版或第三版功能。

---

## 21. 总结

第一版的核心不是做一个”论文推荐器”，而是做一个以动态思维导图为中心的科研 Agent 客户端。

它的最小闭环是：

```text
课题 → 思维导图 → 文献扫描 → 预过滤 → LLM 阅读 → 节点挂载（支持/挑战）→ Agent Team 对话 → 信念更新 → 记忆更新
```

界面上必须突出：

```text
中央 TabControl（思维导图 / Agent Team 对话切换）
左侧课题与记忆
底部科研行动卡片
```

技术上建议坚持：

```text
Python 主体
NiceGUI 快速构建界面
FastAPI 提供接口
SQLite + FTS5 保存结构化数据并支持全文搜索
Cytoscape.js 实现交互式思维导图（信念强度可视化）
Pydantic + structured output 约束 LLM 输出
sentence-transformers 本地预过滤论文
APScheduler (AsyncIOScheduler) 执行定时任务
```

这样可以最快验证产品价值，同时为后续升级桌面客户端、动态 Research Belief Graph、向量记忆和自动实验规划留下空间。
