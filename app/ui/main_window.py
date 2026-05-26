import uuid
from PyQt6.QtWidgets import QMainWindow, QSplitter, QFrame, QVBoxLayout, QWidget
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt
from sqlmodel import Session
from app.services.storage import get_engine
from app.models.session import Session as SessionModel
from app.ui.workspace_list import WorkspaceList
from app.ui.chat_view import ChatView
from app.ui.mind_map_tree import MindMapTree
from app.ui.dialogs import LLMSettingsDialog
from app.ui.toast import Toast


APP_BG = "#EDEFF2"


def _wrap_in_panel(widget, bg_color):
    frame = QFrame()
    frame.setObjectName("panelFrame")
    frame.setFrameShape(QFrame.Shape.NoFrame)
    frame.setStyleSheet(
        "QFrame#panelFrame {"
        f" background: {bg_color};"
        " border: none;"
        " border-radius: 12px;"
        "}"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(1, 1, 1, 1)
    layout.setSpacing(0)
    layout.addWidget(widget)
    return frame


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Research Map Agent")

        central = QWidget()
        central.setStyleSheet(f"background:{APP_BG};")
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(10, 10, 10, 10)
        central_layout.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setHandleWidth(10)
        self._splitter.setStyleSheet(
            "QSplitter { background: transparent; }"
            "QSplitter::handle { background: transparent; border: none; }"
        )
        central_layout.addWidget(self._splitter)
        self.setCentralWidget(central)

        self.workspace_list = WorkspaceList()
        left_frame = _wrap_in_panel(self.workspace_list, "#F5F5F5")
        self._splitter.addWidget(left_frame)

        self.chat_view = ChatView()
        self._chat_frame = _wrap_in_panel(self.chat_view, "#FFFFFF")
        self._splitter.addWidget(self._chat_frame)

        self.mind_map_tree = MindMapTree()
        self._right_frame = _wrap_in_panel(self.mind_map_tree, "#FAFAFA")
        self._splitter.addWidget(self._right_frame)

        self._splitter.setStretchFactor(0, 2)
        self._splitter.setStretchFactor(1, 5)
        self._splitter.setStretchFactor(2, 3)
        self._splitter.setSizes([220, 560, 440])
        self._saved_left = 220
        self._saved_right = 440
        self._build_workers: list = []  # prevent GC of running QThreads

        self._setup_menu()
        self._wire_signals()

    def _setup_menu(self):
        menubar = self.menuBar()
        menubar.setNativeMenuBar(False)
        menubar.setStyleSheet(
            "QMenuBar { background:#F0F0F0; border-bottom:1px solid #D0D0D0;"
            "  color:#333333; padding:1px 0; }"
            "QMenuBar::item { padding:4px 12px; }"
            "QMenuBar::item:selected { background:#E0E0E0; }"
            "QMenu { background:#FFFFFF; border:1px solid #D0D0D0;"
            "  border-radius:4px; padding:4px 0; color:#333333; }"
            "QMenu::item { padding:6px 24px; color:#333333; }"
            "QMenu::item:selected { background:#E8E8E8; color:#111111; }"
            "QMenu::separator { height:1px; background:#E0E0E0; margin:2px 8px; }"
        )
        file_menu = menubar.addMenu("文件")
        file_menu.addAction("新建课题 (Ctrl+N)", self.workspace_list.open_new_workspace_dialog)
        file_menu.addSeparator()
        file_menu.addAction("退出 (Ctrl+Q)", self.close)
        settings_action = QAction("大模型配置...", self)
        settings_action.triggered.connect(self._open_llm_settings)
        menubar.addAction(settings_action)

    def _open_llm_settings(self):
        LLMSettingsDialog(self).exec()

    def _wire_signals(self):
        ws = self.workspace_list
        chat = self.chat_view
        tree = self.mind_map_tree

        ws.workspace_selected.connect(self._on_workspace_selected)
        ws.session_selected.connect(chat.load_session)
        ws.session_created.connect(self._on_session_created)
        ws.build_map_requested.connect(self._on_build_requested)
        tree.node_selected.connect(self._on_node_selected)

        chat.collapse_toggled.connect(self._toggle_mind_map)
        chat.session_create_requested.connect(self._create_session)

    def _on_workspace_selected(self, workspace_id, title):
        self.setWindowTitle(f"Research Map Agent - {title}")
        self.mind_map_tree.load_workspace(workspace_id)
        self.chat_view.set_workspace(workspace_id)
        self.chat_view.load_session_by_workspace(workspace_id)

    def _on_session_created(self, session_id, title):
        self.chat_view.load_session(session_id, title)

    def _on_build_requested(self, workspace_id, workspace_title, session_id):
        Toast(self, "正在生成", f"正在为「{workspace_title}」生成思维导图...")

        worker = self.workspace_list.get_build_worker(workspace_id, workspace_title, session_id)
        if worker:
            self._build_workers.append(worker)

            def on_finished(wid, wtitle, nc, ec, errs):
                if worker in self._build_workers:
                    self._build_workers.remove(worker)
                if errs:
                    Toast(self, "生成失败", "; ".join(errs), is_error=True)
                else:
                    Toast(self, "生成完成", f"{nc} 个节点, {ec} 条连接")
                self.mind_map_tree.load_workspace(workspace_id)
                self.chat_view.load_session_by_workspace(workspace_id)

            worker.finished.connect(on_finished)
            worker.start()

    def _on_node_selected(self, node_id, name):
        Toast(self, "节点", f"已选中: {name}")

    def _toggle_mind_map(self):
        visible = self._right_frame.isVisible()
        if visible:
            # Hiding: preserve left panel width
            sizes = self._splitter.sizes()
            self._saved_left = sizes[0]
            self._saved_right = sizes[2]
            self._right_frame.setVisible(False)
            new_sizes = self._splitter.sizes()
            total = sum(new_sizes)
            self._splitter.setSizes([self._saved_left, total - self._saved_left])
        else:
            # Showing: keep current left width, restore right width
            left_w = self._splitter.sizes()[0]
            self._right_frame.setVisible(True)
            total = sum(self._splitter.sizes())
            self._splitter.setSizes([left_w, total - left_w - self._saved_right, self._saved_right])
        btn = self.chat_view.collapse_btn
        btn.setText("▶" if visible else "◀")

    def _create_session(self, workspace_id):
        sid = uuid.uuid4().hex
        engine = get_engine()
        with Session(engine) as db:
            s = SessionModel(id=sid, workspace_id=workspace_id, title="新会话")
            db.add(s)
            db.commit()
        self.workspace_list._current_session_id = sid
        self.workspace_list.refresh()
        self.chat_view.load_session(sid, "新会话")

    def closeEvent(self, event):
        self.chat_view.shutdown_workers()
        for w in list(self._build_workers):
            if w.isRunning():
                w.terminate()
                w.wait()
        self._build_workers.clear()
        event.accept()
