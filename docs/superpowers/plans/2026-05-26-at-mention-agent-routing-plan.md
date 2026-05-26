# @Mention Agent 自动联想与消息路由 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在聊天输入框中输入 `@` 时弹出 agent 联想列表，选择后路由消息到对应 agent，支持 agent 间自动协作。

**Architecture:** 保持 QLineEdit + QCompleter 实现 @ 联想（最小 UI 改动）。新增 MessageRouter 服务模块负责解析 @mentions、构建增强 system prompt、agent 分发。重构 ChatWorker 支持按 agent_name 路由。自动协作通过 chat_view 中的循环逻辑实现，每个 agent 回复后检查新 @mentions 并启动新 worker。

**Tech Stack:** PyQt6, SQLModel/SQLite, OpenAI SDK

---

### Task 1: AgentConfig 模型新增 description 字段

**Files:**
- Modify: `app/models/agent_config.py`
- Modify: `app/agents/definitions.py`
- Modify: `app/services/storage.py`

- [ ] **Step 1: Add description field to AgentConfig model**

```python
# app/models/agent_config.py
import uuid
from datetime import datetime
from sqlmodel import Field, SQLModel


class AgentConfig(SQLModel, table=True):
    __tablename__ = "agent_configs"

    id: str = Field(default_factory=lambda: uuid.uuid4().hex, primary_key=True)
    name: str = Field(index=True)
    role: str = Field(default="assistant")
    system_prompt: str = Field(default="")
    description: str = Field(default="")  # 一句话角色描述
    model: str = Field(default="")
    color: str = Field(default="#07C160")
    enabled: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow,
                                  sa_column_kwargs={"onupdate": lambda: datetime.utcnow()})
```

- [ ] **Step 2: Add description to DEFAULT_AGENTS**

```python
# app/agents/definitions.py
DEFAULT_AGENTS = [
    {
        "name": "Topic Agent",
        "role": "assistant",
        "system_prompt": (
            "你是 Research Map Agent 的核心助手 Topic Agent。"
            "你帮助用户理解研究课题的结构、节点关系、前沿动态和可迁移算法想法。"
            "回答简洁、专业，优先结合课题的思维导图结构给出具体建议。"
            "你可以帮助用户扩展节点、分析论文价值、生成实验方向。"
        ),
        "description": "核心研究助手，帮助理解课题结构和节点关系",
        "model": "",
        "color": "#07C160",
        "enabled": True,
    },
    {
        "name": "Paper Agent",
        "role": "paper",
        "system_prompt": (
            "你是 Paper Agent，负责论文检索、阅读和分析。"
            "你帮助用户查找相关论文，提取核心思想、设计哲学和可迁移机制。"
            "你需要评估论文的证据质量、迁移潜力和风险水平。"
        ),
        "description": "论文检索与阅读分析，提取可迁移机制",
        "model": "",
        "color": "#F9A825",
        "enabled": True,
    },
    {
        "name": "Transfer Agent",
        "role": "transfer",
        "system_prompt": (
            "你是 Transfer Agent，专注于算法迁移判断和实验想法生成。"
            "你分析论文思想是否可以迁移到用户的算法中，给出迁移方案、预期收益和风险。"
            "你可以将想法转化为可验证的实验假设。"
        ),
        "description": "算法迁移判断，实验想法生成",
        "model": "",
        "color": "#2196F3",
        "enabled": True,
    },
    {
        "name": "Memory Agent",
        "role": "memory",
        "system_prompt": (
            "你是 Memory Agent，管理课题的长期记忆、负面经验和扫描日志。"
            "你帮助用户回顾历史判断、避免重复失败路线。"
            "当用户提出类似过去失败过的方向时，你会主动提醒。"
        ),
        "description": "长期记忆管理，负面经验提醒",
        "model": "",
        "color": "#9E9E9E",
        "enabled": True,
    },
]
```

- [ ] **Step 3: Update _seed_agents to include description and add DB migration**

```python
# app/services/storage.py — update _seed_agents function
def _seed_agents(engine):
    """Insert default agent configs if table is empty."""
    from sqlmodel import Session, select
    from app.models.agent_config import AgentConfig
    from app.agents.definitions import DEFAULT_AGENTS

    with Session(engine) as db:
        count = db.exec(select(AgentConfig)).first()
        if count is not None:
            return
        for a in DEFAULT_AGENTS:
            db.add(AgentConfig(
                name=a["name"], role=a["role"], system_prompt=a["system_prompt"],
                description=a.get("description", ""),
                model=a["model"], color=a["color"], enabled=a["enabled"],
            ))
        db.commit()
```

Also add migration function to `init_db`:

```python
# app/services/storage.py — add to end of file
import sqlalchemy

def _migrate_agent_config_description(engine):
    """Add description column to agent_configs if it doesn't exist."""
    with engine.connect() as conn:
        result = conn.execute(sqlalchemy.text(
            "PRAGMA table_info('agent_configs')"
        ))
        columns = [row[1] for row in result.fetchall()]
        if "description" not in columns:
            conn.execute(sqlalchemy.text(
                "ALTER TABLE agent_configs ADD COLUMN description TEXT DEFAULT ''"
            ))
            conn.commit()
```

Call migration in `init_db` before `_seed_agents`:

```python
# app/services/storage.py — update init_db
def init_db():
    import app.models  # noqa: F401
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    _init_fts5(engine)
    _migrate_agent_config_description(engine)  # new
    _seed_agents(engine)
```

- [ ] **Step 4: Verify migration works**

Run:
```bash
cd /Volumes/d/Programming/ResearchMap && python -c "
from app.services.storage import init_db
init_db()
print('DB initialized successfully')
"
```

Check schema:
```bash
cd /Volumes/d/Programming/ResearchMap && python -c "
import sqlalchemy
from app.services.storage import get_engine
engine = get_engine()
with engine.connect() as conn:
    result = conn.execute(sqlalchemy.text(\"PRAGMA table_info('agent_configs')\"))
    for row in result.fetchall():
        print(row)
"
```

- [ ] **Step 5: Commit**

```bash
git add app/models/agent_config.py app/agents/definitions.py app/services/storage.py
git commit -m "feat: add description field to AgentConfig model"
```

---

### Task 2: MessageRouter 模块

**Files:**
- Create: `app/services/message_router.py`
- Create: `tests/test_message_router.py`

- [ ] **Step 1: Write failing tests for MessageRouter**

```python
# tests/test_message_router.py
import pytest
from sqlmodel import Session, SQLModel, create_engine
from app.models.agent_config import AgentConfig
from app.services.message_router import MessageRouter, RoutedAgent


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(AgentConfig(
            name="Topic Agent", role="assistant", system_prompt="Topic prompt",
            description="核心助手", model="", color="#07C160", enabled=True,
        ))
        session.add(AgentConfig(
            name="Paper Agent", role="paper", system_prompt="Paper prompt",
            description="论文检索", model="gpt-4", color="#F9A825", enabled=True,
        ))
        session.add(AgentConfig(
            name="Memory Agent", role="memory", system_prompt="Memory prompt",
            description="记忆管理", model="", color="#9E9E9E", enabled=False,
        ))
        session.commit()
        yield session


class TestParseMentions:
    def test_single_mention(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("@Topic Agent 帮我分析这个课题")
        assert mentions == ["Topic Agent"]

    def test_multiple_mentions(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("@Topic Agent 和 @Paper Agent 一起分析")
        assert mentions == ["Topic Agent", "Paper Agent"]

    def test_no_mention(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("帮我分析这个课题")
        assert mentions == []

    def test_mention_not_matching(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("@Unknown Agent 帮我分析")
        assert mentions == []

    def test_mention_disabled_agent(self, db_session):
        router = MessageRouter(db_session)
        mentions = router.parse_mentions("@Memory Agent 帮我回忆")
        assert mentions == []


class TestResolveAgents:
    def test_resolve_known_mentions(self, db_session):
        router = MessageRouter(db_session)
        agents = router.resolve_agents(["Topic Agent", "Paper Agent"])
        assert len(agents) == 2
        assert agents[0].name == "Topic Agent"
        assert agents[1].name == "Paper Agent"
        assert agents[1].model == "gpt-4"

    def test_resolve_empty_falls_back_to_default(self, db_session):
        router = MessageRouter(db_session)
        agents = router.resolve_agents([])
        assert len(agents) == 1
        assert agents[0].name == "Topic Agent"


class TestBuildSystemPrompt:
    def test_includes_available_agents(self, db_session):
        router = MessageRouter(db_session)
        agent = RoutedAgent(
            name="Paper Agent", role="paper",
            system_prompt="Paper prompt", model="",
        )
        prompt = router.build_system_prompt(agent)
        assert "Paper prompt" in prompt
        assert "可用的 Agent 角色" in prompt
        assert "Topic Agent: 核心助手" in prompt
        assert "Paper Agent: 论文检索" in prompt
        assert "Memory Agent" not in prompt  # disabled agent
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
cd /Volumes/d/Programming/ResearchMap && python -m pytest tests/test_message_router.py -v
```
Expected: FAIL with "No module named 'app.services.message_router'"

- [ ] **Step 3: Implement MessageRouter**

```python
# app/services/message_router.py
import re
from dataclasses import dataclass
from sqlmodel import Session, select
from app.models.agent_config import AgentConfig


@dataclass
class RoutedAgent:
    name: str
    role: str
    system_prompt: str
    model: str


class MessageRouter:
    def __init__(self, db: Session):
        self._db = db
        self._agents: list[AgentConfig] = self._load_enabled_agents()

    def _load_enabled_agents(self) -> list[AgentConfig]:
        return list(
            self._db.exec(
                select(AgentConfig).where(AgentConfig.enabled == True)
            ).all()
        )

    def get_all_agent_names(self) -> list[str]:
        return [a.name for a in self._agents]

    def parse_mentions(self, text: str) -> list[str]:
        """Extract @AgentName mentions from text. Only returns enabled agents."""
        mentioned = []
        for agent in self._agents:
            if f"@{agent.name}" in text:
                mentioned.append(agent.name)
        return mentioned

    def resolve_agents(self, mentions: list[str]) -> list[RoutedAgent]:
        """Resolve mention names to RoutedAgent objects. Falls back to default if empty."""
        name_map = {a.name: a for a in self._agents}
        result = []
        for name in mentions:
            agent = name_map.get(name)
            if agent:
                result.append(RoutedAgent(
                    name=agent.name, role=agent.role,
                    system_prompt=agent.system_prompt,
                    model=agent.model or "",
                ))
        if not result:
            default = next(
                (a for a in self._agents if a.role == "assistant"),
                self._agents[0] if self._agents else None,
            )
            if default:
                result.append(RoutedAgent(
                    name=default.name, role=default.role,
                    system_prompt=default.system_prompt,
                    model=default.model or "",
                ))
        return result

    def build_system_prompt(self, agent: RoutedAgent) -> str:
        """Build enhanced system prompt with available agents summary."""
        base = agent.system_prompt
        available = [
            f"- {a.name}: {a.description or 'No description'}"
            for a in self._agents
        ]
        if available:
            base += (
                "\n\n---\n"
                "可用的 Agent 角色（你可以通过 @Agent名称 调用他们协助你）：\n"
                + "\n".join(available)
                + "\n---"
            )
        return base
```

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
cd /Volumes/d/Programming/ResearchMap && python -m pytest tests/test_message_router.py -v
```
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/message_router.py tests/test_message_router.py
git commit -m "feat: add MessageRouter for @mention parsing and agent routing"
```

---

### Task 3: ChatWorker 重构

**Files:**
- Modify: `app/ui/worker.py`

- [ ] **Step 1: Refactor ChatWorker to accept agent_name and use MessageRouter**

```python
# app/ui/worker.py — replace the ChatWorker class

class ChatWorker(QThread):
    """Background thread for LLM chat responses. Routes to specific agent by name."""
    finished = pyqtSignal(str, str)  # session_id, agent_name

    def __init__(self, session_id: str, agent_name: str = "", parent=None):
        super().__init__(parent)
        self._session_id = session_id
        self._agent_name = agent_name

    def run(self):
        import uuid as _uuid
        engine = get_engine()

        with Session(engine) as db:
            from app.services.message_router import MessageRouter, RoutedAgent
            router = MessageRouter(db)

            # Resolve agent by name, or fall back to default
            if self._agent_name:
                agents = router.resolve_agents([self._agent_name])
            else:
                agents = router.resolve_agents([])

            routed = agents[0]
            agent_name = routed.name
            system_prompt = router.build_system_prompt(routed)
            agent_model = routed.model

        # Load chat history
        with Session(engine) as db:
            from app.models.chat_message import ChatMessage
            history = db.exec(
                select(ChatMessage)
                .where(ChatMessage.session_id == self._session_id)
                .order_by(ChatMessage.created_at.asc())
            ).all()

        messages = [{"role": "system", "content": system_prompt}]
        for msg in history[-20:]:
            role = "assistant" if msg.role == "assistant" else "user"
            label = f"{msg.agent_name}: " if msg.agent_name and msg.role == "assistant" else ""
            messages.append({"role": role, "content": f"{label}{msg.content}"})

        try:
            from app.services.llm import LLMService
            llm = LLMService()
            if agent_model:
                llm.model = agent_model
            reply = llm.call_simple(
                system_prompt=messages[0]["content"],
                user_prompt="\n".join(
                    f"{'Assistant' if m['role'] == 'assistant' else 'User'}: {m['content']}"
                    for m in messages[1:]
                ),
            )
            if reply.startswith("LLM Error:"):
                reply = f"抱歉，大模型调用失败：{reply}"
        except Exception as e:
            reply = f"抱歉，调用大模型时出错：{e}"

        with Session(engine) as db:
            msg = ChatMessage(
                id=_uuid.uuid4().hex,
                session_id=self._session_id,
                role="assistant",
                content=reply,
                agent_name=agent_name,
            )
            db.add(msg)
            db.commit()

        self.finished.emit(self._session_id, agent_name)
```

- [ ] **Step 2: Run existing tests to check for regressions**

Run:
```bash
cd /Volumes/d/Programming/ResearchMap && python -m pytest tests/ -v
```

- [ ] **Step 3: Commit**

```bash
git add app/ui/worker.py
git commit -m "refactor: ChatWorker uses MessageRouter and agent_name routing"
```

---

### Task 4: ChatView — @ 联想 (QCompleter)

**Files:**
- Modify: `app/ui/chat_view.py`

- [ ] **Step 1: Add QCompleter to chat input for @agent autocomplete**

Add the following to `ChatView.__init__`, after creating `self.input_edit` (after line 199):

```python
        # ---- @mention completer setup ----
        self._mention_completer = None
        self._setup_mention_completer()

    def _setup_mention_completer(self):
        from PyQt6.QtCore import QStringListModel
        engine = get_engine()
        with Session(engine) as db:
            agents = db.exec(
                select(AgentConfig).where(AgentConfig.enabled == True)
            ).all()
        agent_items = [f"@{a.name}" for a in agents]
        model = QStringListModel(agent_items)
        self._mention_completer = QCompleter(model, self)
        self._mention_completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self._mention_completer.setCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        self._mention_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.input_edit.setCompleter(self._mention_completer)
        self.input_edit.textChanged.connect(self._on_mention_text_changed)

    def _on_mention_text_changed(self, text: str):
        """Update completer prefix when user types @."""
        at_idx = text.rfind('@')
        if at_idx >= 0:
            if at_idx == 0 or text[at_idx - 1] == ' ':
                prefix = text[at_idx:]
                self._mention_completer.setCompletionPrefix(prefix)
                self._mention_completer.complete()
```

Add the imports at the top of the file (merge with existing imports):
```python
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QFrame,
    QLineEdit, QPushButton, QCompleter,
)
```

Add this import after the existing ones:
```python
from app.models.agent_config import AgentConfig
```

- [ ] **Step 2: Verify the app launches and @mention works**

Run:
```bash
cd /Volumes/d/Programming/ResearchMap && python -m app.main
```

Manual test:
1. Type `@` in the input box → agent list popup should appear
2. Type `@Pa` → only Paper Agent should show
3. Press Enter on a selection → `@Paper Agent ` inserted
4. Press Esc → popup closes

- [ ] **Step 3: Commit**

```bash
git add app/ui/chat_view.py
git commit -m "feat: add @agent mention autocomplete with QCompleter"
```

---

### Task 5: ChatView — 消息路由集成

**Files:**
- Modify: `app/ui/chat_view.py`

- [ ] **Step 1: Update _send_message to parse @mentions and route to agents**

Replace the `_send_message` method:

```python
    def _send_message(self):
        content = self.input_edit.text().strip()
        if not content or not self._session_id:
            return
        sid = self._session_id
        engine = get_engine()

        # Parse @mentions to determine target agents
        with Session(engine) as db:
            from app.services.message_router import MessageRouter
            router = MessageRouter(db)
            mentioned = router.parse_mentions(content)

        with Session(engine) as db:
            db.add(ChatMessage(id=uuid.uuid4().hex, session_id=sid,
                               role="user", content=content))
            db.commit()

        self.input_edit.clear()
        self.input_edit.setEnabled(False)
        self._refresh()

        # Track pending worker count for multi-agent
        self._pending_workers = 0
        self._auto_collab_round = 0
        self._called_agents = set()

        self._dispatch_workers(sid, mentioned)

    def _dispatch_workers(self, session_id: str, agent_names: list[str]):
        """Start ChatWorkers for each agent. If no mentions, use default."""
        engine = get_engine()
        with Session(engine) as db:
            from app.services.message_router import MessageRouter
            router = MessageRouter(db)
            agents = router.resolve_agents(agent_names)

        for agent in agents:
            self._called_agents.add(agent.name)
            worker = ChatWorker(session_id, agent_name=agent.name)
            worker.finished.connect(
                lambda sid, name, w=worker: self._on_agent_done(sid, name)
            )
            self._pending_workers += 1
            worker.start()

    def _on_agent_done(self, session_id: str, agent_name: str):
        self._pending_workers -= 1
        if session_id == self._session_id:
            self._refresh()

        # Auto-collaboration: check reply for @mentions
        if self._auto_collab_enabled and self._auto_collab_round < 3:
            self._check_auto_collab(session_id, agent_name)

        if self._pending_workers <= 0:
            self.input_edit.setEnabled(True)
            self._auto_collab_round = 0
            self._called_agents.clear()

    def _check_auto_collab(self, session_id: str, agent_name: str):
        """Check the latest reply from agent_name for @mentions to other agents."""
        engine = get_engine()
        with Session(engine) as db:
            from app.services.message_router import MessageRouter
            msg = db.exec(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.agent_name == agent_name,
                )
                .order_by(ChatMessage.created_at.desc())
            ).first()
            if not msg:
                return

            router = MessageRouter(db)
            mentions = router.parse_mentions(msg.content)
            new_mentions = [m for m in mentions if m not in self._called_agents]

            if new_mentions:
                self._auto_collab_round += 1
                # Add a system note
                import uuid as _uuid
                db.add(ChatMessage(
                    id=_uuid.uuid4().hex,
                    session_id=session_id,
                    role="system",
                    content=f"[自动协作 第{self._auto_collab_round}轮] {agent_name} 调用了 {', '.join(f'@{n}' for n in new_mentions)}",
                ))
                db.commit()
                self._dispatch_workers(session_id, new_mentions)
```

- [ ] **Step 2: Add auto_collab_enabled flag to ChatView**

Add in `__init__`:
```python
        self._auto_collab_enabled = False
```

- [ ] **Step 3: Commit**

```bash
git add app/ui/chat_view.py
git commit -m "feat: integrate MessageRouter into chat send flow with multi-agent support"
```

---

### Task 6: ChatView — 自动协作开关 UI

**Files:**
- Modify: `app/ui/chat_view.py`

- [ ] **Step 1: Add toggle button to chat header**

Replace the header section in `__init__` (lines 140-156):

```python
        header = QWidget()
        header.setStyleSheet(f"background:{HEADER_BG};border-bottom:1px solid {DIVIDER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 8, 8, 8)
        title = QLabel("Agent 对话")
        title.setStyleSheet(f"font-weight:bold;font-size:14px;color:{TEXT_PRIMARY};")
        hl.addWidget(title)

        # Auto-collaboration toggle
        self._collab_toggle = QPushButton("协作: 关")
        self._collab_toggle.setCheckable(True)
        self._collab_toggle.setFixedHeight(24)
        self._collab_toggle.setStyleSheet(
            "QPushButton { background:#2E3D36; color:#8A9890; border:1px solid #3D4A44; "
            "border-radius:4px; padding:2px 10px; font-size:11px; }"
            "QPushButton:checked { background:#07C160; color:#000000; border-color:#07C160; }"
            "QPushButton:hover { border-color:#4A5D54; }"
        )
        self._collab_toggle.clicked.connect(self._on_collab_toggled)
        hl.addWidget(self._collab_toggle)

        hl.addStretch()
        self.collapse_btn = QPushButton("◀")
        self.collapse_btn.setFixedSize(28, 28)
        self.collapse_btn.setStyleSheet(
            "QPushButton { border:none; border-radius:4px; color:#8A9890; font-size:12px; }"
            "QPushButton:hover { background:#2E3D36; }"
        )
        self.collapse_btn.clicked.connect(self.collapse_toggled.emit)
        hl.addWidget(self.collapse_btn)
        layout.addWidget(header)
```

Add the toggle handler:
```python
    def _on_collab_toggled(self, checked: bool):
        self._auto_collab_enabled = checked
        self._collab_toggle.setText("协作: 开" if checked else "协作: 关")
```

- [ ] **Step 2: Verify in the app**

Run:
```bash
cd /Volumes/d/Programming/ResearchMap && python -m app.main
```

Manual test:
1. Check the "协作: 关" button is visible in header
2. Click to toggle → should show "协作: 开" in green
3. Click again → back to "协作: 关"

- [ ] **Step 3: Commit**

```bash
git add app/ui/chat_view.py
git commit -m "feat: add auto-collaboration toggle to chat header"
```

---

### Task 7: 集成测试与收尾

**Files:**
- Create: `tests/test_chat_routing.py`

- [ ] **Step 1: Write integration test for the full routing flow**

```python
# tests/test_chat_routing.py
import pytest
from sqlmodel import Session, SQLModel, create_engine
from app.models.agent_config import AgentConfig
from app.services.message_router import MessageRouter


@pytest.fixture
def populated_db():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        for a in [
            AgentConfig(name="Topic Agent", role="assistant",
                        system_prompt="Topic prompt", description="核心助手",
                        model="", color="#07C160", enabled=True),
            AgentConfig(name="Paper Agent", role="paper",
                        system_prompt="Paper prompt", description="论文检索",
                        model="gpt-4", color="#F9A825", enabled=True),
            AgentConfig(name="Transfer Agent", role="transfer",
                        system_prompt="Transfer prompt", description="迁移判断",
                        model="", color="#2196F3", enabled=True),
        ]:
            session.add(a)
        session.commit()
        yield session


class TestMessageRouting:
    def test_parse_all_mentions(self, populated_db):
        router = MessageRouter(populated_db)
        text = "@Topic Agent 分析后，@Paper Agent 找论文，@Transfer Agent 判断"
        assert router.parse_mentions(text) == [
            "Topic Agent", "Paper Agent", "Transfer Agent"
        ]

    def test_resolve_returns_correct_order(self, populated_db):
        router = MessageRouter(populated_db)
        agents = router.resolve_agents(["Paper Agent", "Transfer Agent"])
        assert [a.name for a in agents] == ["Paper Agent", "Transfer Agent"]

    def test_ignore_unknown_mention(self, populated_db):
        router = MessageRouter(populated_db)
        agents = router.resolve_agents(["Unknown Agent"])
        assert len(agents) == 1
        assert agents[0].name == "Topic Agent"

    def test_auto_collab_dedup(self, populated_db):
        """Already-called agents are not re-called."""
        router = MessageRouter(populated_db)
        mentions = router.parse_mentions("@Topic Agent @Paper Agent")
        called = {"Topic Agent"}
        new = [m for m in mentions if m not in called]
        assert new == ["Paper Agent"]
```

- [ ] **Step 2: Run all tests**

```bash
cd /Volumes/d/Programming/ResearchMap && python -m pytest tests/ -v
```
Expected: ALL PASS (both test_message_router.py and test_chat_routing.py)

- [ ] **Step 3: Full manual smoke test**

Run:
```bash
cd /Volumes/d/Programming/ResearchMap && python -m app.main
```

Test checklist:
1. Create a workspace → type `@` in chat input → agent list popup appears
2. Type `@Pa` → filter works, only Paper Agent shown
3. Select Paper Agent → `@Paper Agent ` inserted into input
4. Type message: `@Topic Agent 帮我分析这个课题的核心方法` → send
5. Topic Agent replies with proper response
6. Toggle "协作: 开" → send `@Topic Agent 你分析完后请 @Paper Agent 搜索相关论文`
7. Topic Agent replies → Paper Agent is auto-called → reply appears
8. Toggle "协作: 关" → agent replies no longer auto-route

- [ ] **Step 4: Final commit**

```bash
git add tests/test_chat_routing.py
git commit -m "test: add integration tests for chat routing"
```
