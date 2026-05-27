import math
import re
import uuid
import html as _html
import markdown2
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QFrame,
    QLineEdit, QPushButton, QCompleter, QTextEdit, QSizePolicy,
)
from PyQt6.QtGui import QFont
from PyQt6.QtCore import pyqtSignal, Qt, QTimer, QStringListModel
from sqlmodel import Session, select
from app.services.storage import get_engine
from app.models.chat_message import ChatMessage
from app.models.session import Session as SessionModel
from app.services.agent_runtime import SessionRuntimeManager
from app.models.agent_config import AgentConfig

CHAT_BG = "#FFFFFF"
BUBBLE_SELF = "#07C160"
BUBBLE_OTHER = "#F0F0F0"
TEXT_PRIMARY = "#111111"
TEXT_SECONDARY = "#666666"
DIVIDER = "#E0E0E0"
HEADER_BG = "#F5F5F5"

AVATAR_COLORS = {
    "user": "#2196F3", "Topic Agent": "#07C160", "Paper Agent": "#F9A825",
    "Transfer Agent": "#2196F3", "Memory Agent": "#9E9E9E", "system": "#888888",
}

HTML_TAG_RE = re.compile(
    r"</?(?:p|br|strong|b|em|i|ul|ol|li|pre|code|blockquote|h[1-6]|table|thead|tbody|tr|th|td)(?:\s|/?>)",
    re.IGNORECASE,
)

BUBBLE_HTML_TEMPLATE = """
<html>
<head>
<style>
body {{
    margin: 0;
    padding: 0;
    font-size: 13px;
}}
p {{
    margin: 0 0 6px 0;
}}
ul, ol {{
    margin: 0 0 6px 0;
    padding-left: 18px;
}}
li {{
    margin: 0 0 2px 0;
}}
pre {{
    margin: 4px 0;
    white-space: pre-wrap;
}}
code {{
    font-family: monospace;
}}
blockquote {{
    margin: 4px 0 4px 10px;
    padding-left: 8px;
}}
table {{
    border-collapse: collapse;
    margin: 4px 0;
}}
td, th {{
    padding: 2px 4px;
}}
</style>
</head>
<body>{body}</body>
</html>
"""


def _get_avatar_color(name):
    return AVATAR_COLORS.get(name, "#757575")


def _bubble_html(content: str, allow_html: bool) -> str:
    if allow_html:
        if HTML_TAG_RE.search(content):
            body = content
        else:
            body = markdown2.markdown(
                content,
                extras=["tables", "fenced-code-blocks", "break-on-newline", "task_list"],
            )
    else:
        body = _html.escape(content).replace("\n", "<br>")
    return BUBBLE_HTML_TEMPLATE.format(body=body)


class _MessageBubble(QFrame):
    def __init__(self, role, content, agent_name="", review_status=None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        if role == "system":
            self._make_system(content)
        elif review_status and agent_name == "Topic Agent":
            self._make_review_card(content, agent_name, review_status)
        else:
            self._make_bubble(role, content, agent_name)

    def _make_system(self, content):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        label = QLabel(content)
        label.setWordWrap(True)
        label.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:12px;padding:4px 0;")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label, 1)

    def _make_review_card(self, content, agent_name, review_status):
        from app.services.message_router import parse_review_card

        review = parse_review_card(content)
        status_color = "#07C160" if review_status == "passed" else "#FF5252"
        status_text = "审查通过" if review_status == "passed" else "审查不通过"
        status_icon = "✓" if review_status == "passed" else "✗"

        # Outer layout: avatar + bubble, same structure as _make_bubble
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 5, 12, 5)

        # Avatar (left side, small "T" badge)
        avatar = QLabel("T")
        avatar.setFixedSize(34, 34)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background:{status_color};color:white;"
            f"border-radius:17px;font-size:13px;font-weight:bold;"
        )
        layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)

        # Name label above bubble
        name_label = QLabel(agent_name)
        name_label.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:0 2px;")

        # Bubble frame wrapping review content
        bubble = QFrame()
        bubble.setFrameShape(QFrame.Shape.NoFrame)
        bubble.setStyleSheet(
            f"background:{BUBBLE_OTHER};border-radius:4px;"
            f"border:1px solid #D0D0D0;"
        )
        bubble_inner = QVBoxLayout(bubble)
        bubble_inner.setContentsMargins(10, 8, 10, 8)
        bubble_inner.setSpacing(3)

        # Header inside bubble: status badge
        header = QLabel(f"<span style='color:{status_color};font-weight:bold;'>{status_icon} {status_text}</span>")
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setStyleSheet("color:transparent;font-size:12px;background:transparent;")
        bubble_inner.addWidget(header)

        if review:
            # Score row
            score_label = QLabel(f"评分：{'★' * review.score}{'☆' * (5 - review.score)}  {review.score}/5")
            score_label.setStyleSheet("color:#FFD700;font-size:12px;background:transparent;")
            bubble_inner.addWidget(score_label)

            # Summary
            summary_label = QLabel(review.summary)
            summary_label.setWordWrap(True)
            summary_label.setStyleSheet(
                f"color:{TEXT_PRIMARY};font-size:13px;font-weight:bold;"
                "padding:2px 0;background:transparent;"
            )
            bubble_inner.addWidget(summary_label)

            # Issues
            if review.issues and review.issues != ["none"]:
                issues_text = "\n".join(f"• {issue}" for issue in review.issues)
                issues_label = QLabel(issues_text)
                issues_label.setWordWrap(True)
                issues_color = "#FF5252" if review.correctness == "fail" else "#F9A825"
                issues_label.setStyleSheet(
                    f"color:{issues_color};font-size:12px;padding:2px 0;background:transparent;"
                )
                bubble_inner.addWidget(issues_label)

            # Action indicator
            action_map = {"accept": "已通过", "redo": "已要求重做", "supplement": "已补充"}
            action_text = action_map.get(review.action, review.action)
            action_label = QLabel(f"→ {action_text}")
            action_label.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;background:transparent;")
            bubble_inner.addWidget(action_label)
        else:
            # Fallback: show raw text
            body = QLabel(content)
            body.setWordWrap(True)
            body.setStyleSheet(f"color:{TEXT_PRIMARY};font-size:12px;background:transparent;")
            bubble_inner.addWidget(body)

        # Assemble: name label above bubble
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(name_label, alignment=Qt.AlignmentFlag.AlignLeft)
        col.addWidget(bubble)

        layout.addLayout(col)
        layout.addStretch()

    def _make_bubble(self, role, content, agent_name):
        is_user = (role == "user")
        display_name = "我" if is_user else (agent_name or "Agent")
        color = _get_avatar_color(display_name)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 5, 12, 5)

        avatar = QLabel(display_name[0])
        avatar.setFixedSize(34, 34)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background:{color};color:white;border-radius:17px;font-size:13px;font-weight:bold;"
        )

        name_label = QLabel(display_name)
        name_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        name_label.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:11px;padding:0 2px;")

        # Use QTextEdit for plain text display
        bubble = QTextEdit()
        bubble.setReadOnly(True)
        bubble.setFrameShape(QFrame.Shape.NoFrame)
        bubble.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bubble.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        bubble.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        bubble.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        bubble.setSizePolicy(
            bubble.sizePolicy().horizontalPolicy(),
            bubble.sizePolicy().verticalPolicy(),
        )

        text_color = "#000000" if is_user else TEXT_PRIMARY
        bubble.setStyleSheet(
            f"color:{text_color};border-radius:4px;font-size:13px;"
            f"background:{BUBBLE_SELF if is_user else BUBBLE_OTHER};"
            + ("border:1px solid #D0D0D0;" if not is_user else "")
        )

        font = QFont()
        font.setPixelSize(13)
        bubble.setFont(font)

        doc = bubble.document()
        doc.setDocumentMargin(0)

        max_bubble_w = 420
        h_pad_w = 20
        v_pad_h = 8
        border_w = 0 if is_user else 2
        bubble.setViewportMargins(10, 4, 10, 4)

        # Render at a known width first, then measure the rendered document.
        html = _bubble_html(content, allow_html=not is_user)
        doc.setTextWidth(max_bubble_w - border_w - h_pad_w)
        bubble.setHtml(html)

        # Measure actual content width from rendered document
        ideal_w = doc.idealWidth()
        doc_w = min(math.ceil(ideal_w), max_bubble_w - border_w - h_pad_w)

        # Apply final width (shrink-wraps narrow content)
        doc.setTextWidth(doc_w)

        # Set widget dimensions from actual document size
        bubble.setFixedWidth(doc_w + h_pad_w + border_w)
        bubble.setFixedHeight(math.ceil(doc.size().height()) + v_pad_h + border_w)

        col = QVBoxLayout()
        col.setAlignment(Qt.AlignmentFlag.AlignTop)
        col.setSpacing(2)
        col.addWidget(name_label, alignment=Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft)
        col.addWidget(bubble, alignment=Qt.AlignmentFlag.AlignRight if is_user else Qt.AlignmentFlag.AlignLeft)

        if is_user:
            layout.addStretch()
            layout.addLayout(col)
            layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
            layout.setAlignment(col, Qt.AlignmentFlag.AlignTop)
        else:
            layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
            layout.addLayout(col)
            layout.setAlignment(col, Qt.AlignmentFlag.AlignTop)
            layout.addStretch()


class _StatusWidget(QFrame):
    """Shows agent thinking/queued status below a user message."""
    cancel_clicked = pyqtSignal()

    def __init__(self, agent_names: list[str], status: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._agent_names = agent_names
        self._status = status

        layout = QHBoxLayout(self)
        layout.setContentsMargins(56, 2, 12, 4)
        layout.setSpacing(8)

        if status == "thinking":
            text = "  ".join(f"⏳ {name} 思考中..." for name in agent_names)
        elif status == "queued":
            text = f"⏱ 排队中（{agent_names[0]}）"
        else:
            text = ""

        self._label = QLabel(text)
        self._label.setStyleSheet("color:#666666; font-style:italic; font-size:12px; background:transparent;")
        layout.addWidget(self._label)

        if status == "thinking":
            self._cancel_btn = QPushButton("✕ 取消")
            self._cancel_btn.setFixedHeight(20)
            self._cancel_btn.setStyleSheet(
                "QPushButton { color:#666666; background:transparent; border:none; "
                "font-size:11px; padding:0 4px; }"
                "QPushButton:hover { color:#FF5252; }"
            )
            self._cancel_btn.clicked.connect(self.cancel_clicked.emit)
            layout.addWidget(self._cancel_btn)
        else:
            self._cancel_btn = None

        layout.addStretch()

    def update_status(self, status: str, agent_names: list[str] = None):
        if agent_names:
            self._agent_names = agent_names
        self._status = status
        if status == "thinking":
            self._label.setText("  ".join(f"⏳ {name} 思考中..." for name in self._agent_names))
            # Add cancel button if not already present (e.g. transitioning from queued)
            if self._cancel_btn is None:
                layout = self.layout()
                self._cancel_btn = QPushButton("✕ 取消")
                self._cancel_btn.setFixedHeight(20)
                self._cancel_btn.setStyleSheet(
                    "QPushButton { color:#666666; background:transparent; border:none; "
                    "font-size:11px; padding:0 4px; }"
                    "QPushButton:hover { color:#FF5252; }"
                )
                self._cancel_btn.clicked.connect(self.cancel_clicked.emit)
                # Insert before the stretch (which is the last item)
                layout.insertWidget(layout.count() - 1, self._cancel_btn)
        elif status == "queued":
            self._label.setText(f"⏱ {agent_names[0] if agent_names else '排队中...'}")
        elif status == "done":
            self._label.setText("✓ 已完成")


class ChatView(QWidget):
    collapse_toggled = pyqtSignal()
    session_create_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background:{CHAT_BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(f"background:{HEADER_BG};border-bottom:1px solid {DIVIDER};")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(16, 8, 8, 8)
        title = QLabel("Agent 对话")
        title.setStyleSheet(f"font-weight:bold;font-size:14px;color:{TEXT_PRIMARY};")
        hl.addWidget(title)

        hl.addStretch()
        self.collapse_btn = QPushButton("◀")
        self.collapse_btn.setFixedSize(28, 28)
        self.collapse_btn.setStyleSheet(
            "QPushButton { border:none; border-radius:4px; color:#666666; font-size:12px; }"
            "QPushButton:hover { background:#E8E8E8; }"
        )
        self.collapse_btn.clicked.connect(self.collapse_toggled.emit)
        hl.addWidget(self.collapse_btn)
        layout.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"""
            QScrollArea {{ border:none; background:{CHAT_BG}; }}
            QScrollBar:vertical {{
                width:6px; background:transparent; margin:0;
            }}
            QScrollBar::handle:vertical {{
                background:#C0C0C0; border-radius:3px; min-height:30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background:#A0A0A0;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height:0; border:none; background:none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background:none;
            }}
        """)
        self.msg_container = QWidget()
        self.msg_container.setStyleSheet(f"background:{CHAT_BG};")
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.msg_layout.addStretch()
        self.scroll.setWidget(self.msg_container)
        layout.addWidget(self.scroll, 1)

        input_bar = QWidget()
        input_bar.setStyleSheet(f"background:{HEADER_BG};border-top:1px solid {DIVIDER};")
        row = QHBoxLayout(input_bar)
        row.setContentsMargins(16, 10, 16, 10)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("输入消息...")
        self.input_edit.setStyleSheet(
            f"QLineEdit {{ background:#F0F0F0; color:{TEXT_PRIMARY}; "
            f"border:1px solid #D0D0D0; border-radius:4px; padding:8px; font-size:13px; }}"
            "QLineEdit:focus { border-color:#07C160; }"
        )
        self.input_edit.returnPressed.connect(self._send_message)
        # ---- @mention completer setup ----
        self._setup_mention_completer()
        row.addWidget(self.input_edit, 1)
        send = QPushButton("发送")
        send.setStyleSheet(
            "QPushButton { background:#07C160; color:white; border:none; border-radius:4px; "
            "padding:8px 18px; font-size:13px; }"
            "QPushButton:hover { background:#06AD56; }"
        )
        send.clicked.connect(self._send_message)
        row.addWidget(send)
        layout.addWidget(input_bar)

        self._session_id = None
        self._workspace_id = None
        self._status_widgets: dict = {}        # db_msg_id -> _StatusWidget

        # Session agent runtime replaces old serial pipeline
        engine = get_engine()
        self._runtime_manager = SessionRuntimeManager(engine=engine)
        self._runtime_manager.message_saved.connect(self._on_runtime_message_saved)
        self._runtime_manager.status_changed.connect(self._on_runtime_status_changed)

        self._show_empty()

    def _show_empty(self):
        while self.msg_layout.count():
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._workspace_id:
            hint = QLabel("此课题暂无会话")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:14px;padding:40px 0 0 0;")
            self.msg_layout.addWidget(hint)

            create_btn = QPushButton("+ 新建会话")
            create_btn.setStyleSheet(
                "QPushButton { background:#07C160; color:white; border:none; border-radius:4px; "
                "padding:10px 24px; font-size:14px; }"
                "QPushButton:hover { background:#06AD56; }"
            )
            create_btn.clicked.connect(lambda: self.session_create_requested.emit(self._workspace_id))
            self.msg_layout.addWidget(create_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            hint = QLabel("选择一个课题开始对话")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet(f"color:{TEXT_SECONDARY};font-size:14px;padding:60px;")
            self.msg_layout.addWidget(hint)

    def set_workspace(self, workspace_id: str):
        self._workspace_id = workspace_id

    def load_session(self, session_id, _title=""):
        self._session_id = session_id
        self._refresh()

    def load_session_by_workspace(self, workspace_id):
        self._workspace_id = workspace_id
        engine = get_engine()
        with Session(engine) as db:
            s = db.exec(
                select(SessionModel).where(SessionModel.workspace_id == workspace_id)
                .order_by(SessionModel.created_at.desc()).limit(1)
            ).first()
            if s:
                self._session_id = s.id
                self._refresh()
            else:
                self._session_id = None
                self._show_empty()

    def _refresh(self):
        while self.msg_layout.count():
            item = self.msg_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self._session_id:
            self._show_empty()
            self.msg_layout.addStretch()
            return
        engine = get_engine()
        with Session(engine) as db:
            msgs = db.exec(
                select(ChatMessage).where(ChatMessage.session_id == self._session_id)
                .order_by(ChatMessage.created_at.asc())
            ).all()
            for msg in msgs:
                self.msg_layout.addWidget(
                    _MessageBubble(msg.role, msg.content, msg.agent_name,
                                   review_status=msg.review_status)
                )
        self.msg_layout.addStretch()
        QTimer.singleShot(100, self._scroll_bottom)

    def _scroll_bottom(self):
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _setup_mention_completer(self):
        engine = get_engine()
        with Session(engine) as db:
            agents = db.exec(
                select(AgentConfig).where(AgentConfig.enabled == True)
            ).all()
        self._all_agent_names = [a.name for a in agents]
        agent_items = [f"@{a.name}" for a in agents]
        self._mention_model = QStringListModel(agent_items)
        self._mention_completer = QCompleter(self._mention_model, self)
        self._mention_completer.setCompletionMode(
            QCompleter.CompletionMode.PopupCompletion
        )
        self._mention_completer.setCaseSensitivity(
            Qt.CaseSensitivity.CaseInsensitive
        )
        self.input_edit.setCompleter(self._mention_completer)

    def _send_message(self):
        content = self.input_edit.text().strip()
        if not content or not self._session_id:
            return

        sid = self._session_id
        engine = get_engine()

        # Write user message to DB immediately
        db_msg_id = uuid.uuid4().hex
        with Session(engine) as db:
            db.add(ChatMessage(
                id=db_msg_id,
                session_id=sid,
                role="user",
                content=content,
                root_user_message_id=db_msg_id,
            ))
            db.commit()

        self.input_edit.clear()
        self._refresh()

        # Submit to runtime — dispatcher owns mention parsing and task routing
        self._runtime_manager.submit_message(sid, db_msg_id)
        self._runtime_manager.start_draining(sid)

    def shutdown_workers(self):
        """Shut down the runtime manager. Call on app exit."""
        self._runtime_manager.shutdown()

    def _on_runtime_message_saved(self, session_id: str, message_id: str):
        """Refresh when the runtime saves a new agent message."""
        if session_id == self._session_id:
            self._refresh()

    def _on_runtime_status_changed(self, session_id: str, entries: list):
        """Update status display from runtime status entries."""
        if session_id != self._session_id:
            return
        # First version: simple status — full widget integration is a follow-up
        if not entries:
            return
        # Update existing status widget or show runtime activity
        active_entries = [e for e in entries if e.state in ("running", "queued")]
        if active_entries:
            names = [e.agent_name for e in active_entries]
            self._last_status_names = names
        elif hasattr(self, "_last_status_names"):
            del self._last_status_names
