from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem,
    QLabel, QComboBox, QTextEdit, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QTabWidget,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor
from sqlmodel import Session, select
from app.services.storage import get_engine
from app.models.map_node import MapNode
from app.models.map_edge import MapEdge
from app.models.agent_config import AgentConfig

PANEL_BG = "#FFFFFF"
HEADER_BG = "#F5F5F5"
TEXT_PRIMARY = "#111111"
TEXT_SECONDARY = "#666666"
DIVIDER = "#E0E0E0"
INPUT_BG = "#F0F0F0"

NODE_COLORS = {
    "root": "#FFFFFF", "problem": "#64B5F6", "method": "#CE93D8",
    "mechanism": "#FFB74D", "paper": "#FFF176", "idea": "#81C784",
    "experiment": "#BA68C8", "risk": "#E57373", "open_question": "#4DD0E1",
}

NODE_LABELS = {
    "root": "核心", "problem": "问题", "method": "方法",
    "mechanism": "机制", "paper": "论文", "idea": "想法",
    "experiment": "实验", "risk": "风险", "open_question": "开放问题",
}

TAB_STYLE = f"""
    QTabWidget::pane {{ border: none; background:{PANEL_BG}; }}
    QTabBar::tab {{
        background:{HEADER_BG}; color:{TEXT_SECONDARY};
        padding:8px 16px; border:none; border-bottom:2px solid transparent;
        font-size:12px;
    }}
    QTabBar::tab:selected {{
        color:{TEXT_PRIMARY}; border-bottom:2px solid #07C160;
    }}
    QTabBar::tab:hover {{ color:{TEXT_PRIMARY}; }}
"""


class MindMapTree(QWidget):
    node_selected = pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{PANEL_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(TAB_STYLE)

        # Tab 1: 思维导图
        self.map_tree = self._create_map_tab()
        self.tabs.addTab(self.map_tree, "思维导图")

        # Tab 2: TODO
        self.todo_tab = self._create_todo_tab()
        self.tabs.addTab(self.todo_tab, "TODO")

        # Tab 3: Agent 思维
        self.thinking_tab = self._create_thinking_tab()
        self.tabs.addTab(self.thinking_tab, "Agent 思维")

        layout.addWidget(self.tabs)

    # ---- Mind Map Tab ----
    def _create_map_tab(self):
        w = QWidget()
        w.setStyleSheet(f"background:{PANEL_BG};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(20)
        self.tree.setStyleSheet(f"""
            QTreeWidget {{ border:none; background:{PANEL_BG}; padding:8px; font-size:13px; }}
            QTreeWidget::item {{ padding:5px 4px; border-radius:4px; color:{TEXT_PRIMARY}; }}
            QTreeWidget::item:hover {{ background:#F0F0F0; }}
            QTreeWidget::item:selected {{ background:#E8E8E8; }}
        """)
        self.tree.itemClicked.connect(self._on_click)
        layout.addWidget(self.tree)
        self._show_hint()
        return w

    def _show_hint(self):
        self.tree.clear()
        hint = QTreeWidgetItem(self.tree)
        hint.setText(0, "选择课题后显示思维导图")
        hint.setFlags(Qt.ItemFlag.NoItemFlags)
        hint.setForeground(0, QColor(TEXT_SECONDARY))

    def load_workspace(self, workspace_id):
        self.tree.clear()
        if not workspace_id:
            self._show_hint()
            return

        engine = get_engine()
        with Session(engine) as db:
            nodes = db.query(MapNode).where(
                MapNode.topic_id == workspace_id, MapNode.status == "active"
            ).all()
            edges = db.query(MapEdge).where(MapEdge.topic_id == workspace_id).all()

        if not nodes:
            hint = QTreeWidgetItem(self.tree)
            hint.setText(0, "正在生成思维导图...")
            hint.setFlags(Qt.ItemFlag.NoItemFlags)
            hint.setForeground(0, QColor(TEXT_SECONDARY))
            return

        node_map = {n.id: n for n in nodes}
        children = {}
        for e in edges:
            if e.relation in ("parent_of",):
                children.setdefault(e.source_node_id, []).append(e.target_node_id)

        all_kids = set()
        for cl in children.values():
            all_kids.update(cl)
        roots = [n.id for n in nodes if n.id not in all_kids]
        if not roots:
            roots = [nodes[0].id]

        self._build(None, roots, node_map, children)
        self.tree.expandAll()

    def _build(self, parent, node_ids, node_map, children):
        for nid in node_ids:
            node = node_map.get(nid)
            if not node:
                continue
            item = QTreeWidgetItem(parent or self.tree)
            label = NODE_LABELS.get(node.node_type, "")
            prefix = f"[{label}] " if label else ""
            item.setText(0, f"{prefix}{node.name}")
            item.setData(0, Qt.ItemDataRole.UserRole, node.id)
            item.setToolTip(0, node.summary or node.name)
            color = NODE_COLORS.get(node.node_type, "#546e7a")
            item.setForeground(0, QColor(color))
            self._build(item, children.get(nid, []), node_map, children)

    def _on_click(self, item, col):
        nid = item.data(0, Qt.ItemDataRole.UserRole)
        if nid:
            self.node_selected.emit(nid, item.text(0))

    # ---- TODO Tab ----
    def _create_todo_tab(self):
        w = QWidget()
        w.setStyleSheet(f"background:{PANEL_BG};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Input row
        row = QHBoxLayout()
        self.todo_input = QLineEdit()
        self.todo_input.setPlaceholderText("添加待办事项...")
        self.todo_input.setStyleSheet(
            f"background:{INPUT_BG};color:{TEXT_PRIMARY};border:1px solid #D0D0D0;"
            "border-radius:4px;padding:8px;font-size:12px;"
        )
        self.todo_input.returnPressed.connect(self._add_todo)
        row.addWidget(self.todo_input, 1)

        add_btn = QPushButton("+")
        add_btn.setFixedWidth(32)
        add_btn.setStyleSheet(
            "QPushButton { background:#07C160;color:white;border:none;border-radius:4px;"
            "font-size:16px;font-weight:bold; }"
            "QPushButton:hover { background:#06AD56; }"
        )
        add_btn.clicked.connect(self._add_todo)
        row.addWidget(add_btn)
        layout.addLayout(row)

        self.todo_list = QListWidget()
        self.todo_list.setStyleSheet(f"""
            QListWidget {{ border:none; background:{PANEL_BG}; }}
            QListWidget::item {{
                padding:8px; border-radius:4px; color:{TEXT_PRIMARY}; font-size:12px;
            }}
            QListWidget::item:hover {{ background:#F0F0F0; }}
        """)
        # Checkable items
        layout.addWidget(self.todo_list)
        return w

    def _add_todo(self):
        text = self.todo_input.text().strip()
        if not text:
            return
        item = QListWidgetItem(text)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Unchecked)
        self.todo_list.addItem(item)
        self.todo_input.clear()

    # ---- Agent Thinking Tab ----
    def _create_thinking_tab(self):
        w = QWidget()
        w.setStyleSheet(f"background:{PANEL_BG};")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Agent selector
        self.agent_combo = QComboBox()
        self.agent_combo.setStyleSheet(
            f"QComboBox {{ background:{INPUT_BG};color:{TEXT_PRIMARY};border:1px solid #D0D0D0;"
            "border-radius:4px;padding:8px;font-size:12px; }"
            "QComboBox::drop-down { border:none; }"
            "QComboBox QAbstractItemView {"
            f"  background:{INPUT_BG};color:{TEXT_PRIMARY}; }}"
        )
        self._load_agents()
        self.agent_combo.currentTextChanged.connect(self._on_agent_changed)
        layout.addWidget(self.agent_combo)

        # Thinking display
        self.thinking_display = QTextEdit()
        self.thinking_display.setReadOnly(True)
        self.thinking_display.setStyleSheet(
            f"background:{INPUT_BG};color:{TEXT_PRIMARY};border:1px solid #D0D0D0;"
            "border-radius:4px;padding:8px;font-size:12px;"
        )
        layout.addWidget(self.thinking_display, 1)

        self._on_agent_changed(self.agent_combo.currentText())
        return w

    def _load_agents(self):
        engine = get_engine()
        with Session(engine) as db:
            agents = db.exec(select(AgentConfig).where(AgentConfig.enabled)).all()
            for a in agents:
                self.agent_combo.addItem(f"{a.name}", a.id)

    def _on_agent_changed(self, name):
        agent_id = self.agent_combo.currentData()
        if not agent_id:
            return
        engine = get_engine()
        with Session(engine) as db:
            agent = db.get(AgentConfig, agent_id)
            if agent:
                self.thinking_display.setPlaceholderText(
                    f"{agent.name} 的思维链将在此显示...\n\n"
                    f"System Prompt:\n{agent.system_prompt}"
                )
