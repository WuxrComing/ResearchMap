import uuid
from datetime import datetime
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel, QFrame,
    QMenu, QInputDialog, QMessageBox, QPushButton, QTextEdit,
)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import pyqtSignal, Qt
from sqlmodel import Session, select, delete as sm_delete
from app.services.storage import get_engine
from app.models.topic import Topic
from app.models.session import Session as SessionModel
from app.models.chat_message import ChatMessage
from app.models.map_node import MapNode
from app.models.map_edge import MapEdge
from app.ui.dialogs import WorkspaceDialog
from app.ui.worker import TopicBuildWorker

# WeChat palette
SIDEBAR_BG = "#F5F5F5"
SIDEBAR_TEXT = "#666666"
SIDEBAR_TEXT_ACTIVE = "#111111"
SIDEBAR_ITEM_HOVER = "#E8E8E8"
SIDEBAR_ITEM_SELECTED = "#E2E2E2"
SIDEBAR_SESSION_HOVER = "#D4D4D4"
SIDEBAR_SEPARATOR = "#C6C6C6"
GREEN = "#07C160"
ICON_COLORS = ["#07C160", "#2196F3", "#FF9800", "#9C27B0", "#F44336",
               "#00BCD4", "#4CAF50", "#FF5722", "#3F51B5", "#009688"]

MENU_STYLESHEET = """
    QMenu {
        background: #FFFFFF;
        border: 1px solid #D0D0D0;
        border-radius: 6px;
        padding: 4px 0;
        color: #333333;
    }
    QMenu::item {
        padding: 8px 32px 8px 16px;
        color: #333333;
        background: transparent;
    }
    QMenu::item:selected {
        background: #E8E8E8;
        color: #111111;
    }
    QMenu::separator {
        height: 1px;
        background: #E0E0E0;
        margin: 4px 8px;
    }
"""


class _SessionItem(QFrame):
    """Session: indented 64px left, 12px right (aligned with workspace)."""
    clicked = pyqtSignal(str, str)

    def __init__(self, session, is_active, icon_idx, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.session_id = session.id
        self.session_title = session.title
        self._is_active = is_active

        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # Indented: 64px left (aligned with workspace text), 12px right (aligned with workspace)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(64, 4, 12, 4)
        layout.setSpacing(10)

        color = ICON_COLORS[(icon_idx + 3) % len(ICON_COLORS)]
        initial = self.session_title[0] if self.session_title else "S"
        icon = QLabel(initial)
        icon.setFixedSize(24, 24)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            f"background:{color};color:white;border-radius:3px;"
            "font-size:11px;font-weight:bold;"
        )
        layout.addWidget(icon)

        self.title_label = QLabel(self.session_title)
        self.title_label.setStyleSheet(
            f"color:{SIDEBAR_TEXT_ACTIVE if is_active else SIDEBAR_TEXT};"
            "font-size:12px;background:transparent;border:none;"
        )
        layout.addWidget(self.title_label, 1)

        self._update_bg()

    def _update_bg(self):
        if self._is_active:
            self.setStyleSheet(f"background:{SIDEBAR_SESSION_HOVER};")
        else:
            self.setStyleSheet("background:transparent;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.session_id, self.session_title)
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if not self._is_active:
            self.setStyleSheet(f"background:{SIDEBAR_SESSION_HOVER};")
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._is_active:
            self.setStyleSheet("background:transparent;")
        super().leaveEvent(event)


class _WorkspaceItem(QFrame):
    clicked = pyqtSignal(str, str)
    session_clicked = pyqtSignal(str, str)

    def __init__(self, topic, sessions, is_selected, current_session_id, icon_idx, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.topic_id = topic.id
        self.topic_title = topic.title
        self.topic_desc = topic.description or ""
        self._sessions = sessions
        self._is_selected = is_selected
        self._current_session_id = current_session_id
        self._session_items = []
        self._separator = None

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        self._setup_ui(icon_idx)
        self._update_style()

    def _setup_ui(self, icon_idx):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)

        # --- Workspace row: icon + title/desc ---
        top_row = QHBoxLayout()
        top_row.setContentsMargins(12, 10, 12, 6)
        top_row.setSpacing(12)

        color = ICON_COLORS[icon_idx % len(ICON_COLORS)]
        initial = self.topic_title[0] if self.topic_title else "?"
        self.icon_label = QLabel(initial)
        self.icon_label.setFixedSize(40, 40)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet(
            f"background:{color};color:white;border-radius:4px;"
            "font-size:18px;font-weight:bold;"
        )
        top_row.addWidget(self.icon_label)

        right_col = QVBoxLayout()
        right_col.setSpacing(2)

        self.title_label = QLabel(self.topic_title)
        self.title_label.setStyleSheet(
            f"color:{SIDEBAR_TEXT_ACTIVE};font-size:14px;font-weight:bold;"
            "background:transparent;border:none;"
        )
        right_col.addWidget(self.title_label)

        self.desc_label = QLabel(self.topic_desc or "暂无描述")
        self.desc_label.setStyleSheet(
            f"color:{SIDEBAR_TEXT};font-size:11px;background:transparent;border:none;"
        )
        self.desc_label.setWordWrap(True)
        self.desc_label.setMaximumHeight(28)
        right_col.addWidget(self.desc_label)

        top_row.addLayout(right_col, 1)
        main.addLayout(top_row)

        # --- Session items (visible, indented children) ---
        for i, s in enumerate(self._sessions):
            is_active = (s.id == self._current_session_id)
            si = _SessionItem(s, is_active, icon_idx + i)
            si.clicked.connect(self._on_session_click)
            self._session_items.append(si)
            main.addWidget(si)

        # --- Bottom separator ---
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{SIDEBAR_SEPARATOR};border:none;margin:2px 12px;")
        self._separator = sep
        main.addWidget(sep)

    def _update_style(self):
        if self._is_selected:
            self.setStyleSheet(f"background:{SIDEBAR_ITEM_SELECTED};border-radius:8px;")
        else:
            self.setStyleSheet("background:transparent;border-radius:8px;")

    def set_selected(self, selected):
        self._is_selected = selected
        self._update_style()

    def set_separator_visible(self, visible: bool):
        if self._separator:
            self._separator.setVisible(visible)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.topic_id, self.topic_title)
        super().mousePressEvent(event)

    def _on_session_click(self, session_id, title):
        self.session_clicked.emit(session_id, title)

    def _on_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLESHEET)

        edit_action = menu.addAction("编辑")
        edit_action.triggered.connect(self._edit_workspace)
        menu.addSeparator()
        delete_action = menu.addAction("删除")
        delete_action.triggered.connect(self._delete_workspace)

        menu.exec(self.mapToGlobal(pos))

    def _edit_workspace(self):
        from PyQt6.QtWidgets import QDialog
        dlg = WorkspaceDialog(
            self.window(), edit_mode=True,
            workspace_title=self.topic_title,
            workspace_desc=self.topic_desc,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        result = dlg.get_result()
        if not result:
            return
        new_title, new_desc, new_color = result
        if not new_title.strip():
            return

        engine = get_engine()
        with Session(engine) as db:
            t = db.get(Topic, self.topic_id)
            if t:
                t.title = new_title
                t.description = new_desc
                t.updated_at = datetime.utcnow()
                db.commit()

        self.topic_title = new_title
        self.topic_desc = new_desc
        self.title_label.setText(new_title)
        self.desc_label.setText(new_desc or "暂无描述")
        self.icon_label.setStyleSheet(
            f"background:{new_color};color:white;border-radius:4px;"
            "font-size:18px;font-weight:bold;"
        )
        self.clicked.emit(self.topic_id, new_title)

    def _delete_workspace(self):
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除课题「{self.topic_title}」吗？\n所有节点、会话和聊天记录将被永久删除。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        engine = get_engine()
        with Session(engine) as db:
            session_ids = db.exec(
                select(SessionModel.id).where(SessionModel.workspace_id == self.topic_id)
            ).all()
            for sid in session_ids:
                db.exec(sm_delete(ChatMessage).where(ChatMessage.session_id == sid))
            db.exec(sm_delete(SessionModel).where(SessionModel.workspace_id == self.topic_id))
            db.exec(sm_delete(MapEdge).where(MapEdge.topic_id == self.topic_id))
            db.exec(sm_delete(MapNode).where(MapNode.topic_id == self.topic_id))
            db.delete(db.get(Topic, self.topic_id))
            db.commit()

        self.deleteLater()


class WorkspaceList(QWidget):
    workspace_selected = pyqtSignal(str, str)
    session_selected = pyqtSignal(str, str)
    session_created = pyqtSignal(str, str)
    build_map_requested = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background: {SIDEBAR_BG};"
            "QLabel { background:transparent; border:none; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        brand = QLabel("Research Map")
        brand.setAlignment(Qt.AlignmentFlag.AlignLeft)
        brand.setContentsMargins(0, 0, 0, 0)
        brand.setStyleSheet(
            f"color:{SIDEBAR_TEXT_ACTIVE};font-size:15px;font-weight:bold;"
            f"padding:16px 12px 4px 12px;"
        )
        layout.addWidget(brand)

        sub = QLabel("科研思维导图 Agent")
        sub.setAlignment(Qt.AlignmentFlag.AlignLeft)
        sub.setStyleSheet(f"color:{SIDEBAR_TEXT};font-size:11px;padding:0 12px 12px 12px;")
        layout.addWidget(sub)

        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea { border:none; background:transparent; }"
            "QScrollBar:vertical { width:0px; background:transparent; }"
            "QScrollBar::handle:vertical { background:transparent; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }"
        )

        self.item_container = QWidget()
        self.item_container.setStyleSheet("background:transparent;")
        self.item_layout = QVBoxLayout(self.item_container)
        self.item_layout.setContentsMargins(0, 0, 0, 0)
        self.item_layout.setSpacing(0)
        self.item_layout.addStretch()
        self.scroll.setWidget(self.item_container)
        layout.addWidget(self.scroll, 1)

        btn_area = QWidget()
        btn_area.setStyleSheet(f"background:{SIDEBAR_BG};")
        bl = QVBoxLayout(btn_area)
        bl.setContentsMargins(12, 8, 12, 12)

        new_btn = QPushButton("+ 新建课题")
        new_btn.setStyleSheet(
            f"QPushButton {{ background:{GREEN}; color:white; border:none; "
            f"border-radius:4px; padding:10px; font-size:13px; }}"
            f"QPushButton:hover {{ background:#06AD56; }}"
        )
        new_btn.clicked.connect(self.open_new_workspace_dialog)
        bl.addWidget(new_btn)
        layout.addWidget(btn_area)

        self._current_workspace_id = None
        self._current_session_id = None
        self._items = []

        self.refresh()

    def refresh(self):
        for item in self._items:
            try:
                item.deleteLater()
            except RuntimeError:
                pass
        self._items.clear()

        while self.item_layout.count():
            child = self.item_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        engine = get_engine()
        with Session(engine) as db:
            topics = db.exec(select(Topic).order_by(Topic.updated_at.desc())).all()

        if not topics:
            hint = QLabel("还没有课题，点击下方按钮创建")
            hint.setStyleSheet(f"color:{SIDEBAR_TEXT};font-size:12px;padding:20px;")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.item_layout.insertWidget(0, hint)
            self.item_layout.addStretch()
            return

        for idx, t in enumerate(topics):
            with Session(get_engine()) as db:
                sessions = db.exec(
                    select(SessionModel)
                    .where(SessionModel.workspace_id == t.id)
                    .order_by(SessionModel.updated_at.desc())
                ).all()

            is_selected = (t.id == self._current_workspace_id)
            item = _WorkspaceItem(
                t, sessions, is_selected, self._current_session_id, idx,
            )
            item.clicked.connect(self._on_workspace_clicked)
            item.session_clicked.connect(self._on_session_clicked)
            self._items.append(item)
            self.item_layout.insertWidget(self.item_layout.count() - 1, item)

        self._update_item_separators()
        self.item_layout.addStretch()

    def _update_item_separators(self):
        selected_idx = next(
            (idx for idx, item in enumerate(self._items) if item._is_selected),
            None,
        )
        for idx, item in enumerate(self._items):
            hide_for_selected = idx == selected_idx
            hide_above_selected = selected_idx is not None and idx == selected_idx - 1
            item.set_separator_visible(not (hide_for_selected or hide_above_selected))

    def open_new_workspace_dialog(self):
        from PyQt6.QtWidgets import QDialog
        dlg = WorkspaceDialog(self.window(), edit_mode=False)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            result = dlg.get_result()
            if result:
                title, desc, color, auto_generate = result
                self._create_workspace(title, desc, auto_generate)

    def _create_workspace(self, title, desc, auto_generate=True):
        topic_id, session_id = TopicBuildWorker.create_empty_workspace(title, desc)
        self._current_workspace_id = topic_id
        self._current_session_id = session_id
        self.refresh()
        self.workspace_selected.emit(topic_id, title)
        self.session_created.emit(session_id, "默认会话")
        if auto_generate:
            self.build_map_requested.emit(topic_id, title, session_id)

    def get_build_worker(self, workspace_id, title, session_id):
        with Session(get_engine()) as db:
            t = db.get(Topic, workspace_id)
            desc = t.description if t else ""
        return TopicBuildWorker(title, desc, topic_id=workspace_id, session_id=session_id)

    def _on_workspace_clicked(self, workspace_id, title):
        self._current_workspace_id = workspace_id
        self.refresh()
        self.workspace_selected.emit(workspace_id, title)

    def _on_session_clicked(self, session_id, title):
        self._current_session_id = session_id
        with Session(get_engine()) as db:
            session = db.get(SessionModel, session_id)
            if session:
                self._current_workspace_id = session.workspace_id
        self.refresh()
        self.session_selected.emit(session_id, title)
