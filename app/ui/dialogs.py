import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QMessageBox, QTextEdit,
    QApplication, QPushButton, QLineEdit, QWidget, QTabWidget, QCheckBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal

ICON_COLORS = ["#07C160", "#2196F3", "#FF9800", "#9C27B0", "#F44336",
               "#00BCD4", "#4CAF50", "#FF5722", "#3F51B5", "#009688"]

DIALOG_STYLE = (
    "QDialog { background:#FFFFFF; }"
    "QLabel { color:#333333; font-size:12px; background:transparent; }"
)
INPUT_STYLE = (
    "QLineEdit { background:#F5F5F5; color:#111111; border:1px solid #D0D0D0;"
    "border-radius:4px; padding:8px; }"
)
TEXTEDIT_STYLE = (
    "QTextEdit { background:#F5F5F5; color:#111111; border:1px solid #D0D0D0;"
    "border-radius:4px; padding:8px; font-size:13px; }"
)
CANCEL_BTN_STYLE = (
    "QPushButton { background:#E8E8E8; color:#333333; border:none;"
    "border-radius:4px; padding:8px 20px; }"
    "QPushButton:hover { background:#D0D0D0; }"
)
GREEN_BTN_STYLE = (
    "QPushButton { background:#07C160; color:#FFFFFF; border:none;"
    "border-radius:4px; padding:8px 20px; }"
    "QPushButton:hover { background:#06AD56; }"
)


class WorkspaceDialog(QDialog):
    """Unified dialog for creating and editing workspaces."""

    def __init__(self, parent=None, edit_mode=False,
                 workspace_title="", workspace_desc="", icon_color=None):
        super().__init__(parent)
        self.setWindowTitle("编辑课题" if edit_mode else "新建课题")
        self.setMinimumWidth(420)
        self._result = None
        self.setStyleSheet(DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 20, 24, 20)

        # Icon color picker
        layout.addWidget(QLabel("图标颜色"))
        color_row = QHBoxLayout()
        self.color_btns = []
        self._selected_color = icon_color or ICON_COLORS[0]
        for i, c in enumerate(ICON_COLORS):
            btn = QPushButton()
            btn.setFixedSize(28, 28)
            btn.clicked.connect(lambda checked, clr=c, bi=i: self._select_color(clr, bi))
            self.color_btns.append(btn)
            color_row.addWidget(btn)
        color_row.addStretch()
        self._refresh_color_btns()
        layout.addLayout(color_row)

        # Title
        layout.addWidget(QLabel("课题名称"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("输入研究课题...")
        self.title_edit.setText(workspace_title)
        self.title_edit.setStyleSheet(INPUT_STYLE)
        layout.addWidget(self.title_edit)

        # Description
        layout.addWidget(QLabel("课题描述（可选）"))
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlaceholderText("课题描述...")
        self.desc_edit.setText(workspace_desc)
        self.desc_edit.setMaximumHeight(120)
        self.desc_edit.setStyleSheet(TEXTEDIT_STYLE)
        layout.addWidget(self.desc_edit)

        # Auto-generate toggle
        self.auto_generate_checkbox = QCheckBox("创建后自动生成思维导图")
        self.auto_generate_checkbox.setChecked(True)
        self.auto_generate_checkbox.setStyleSheet(
            "QCheckBox { color:#333333; font-size:12px; background:transparent; spacing:8px; }"
            "QCheckBox::indicator { width:16px; height:16px; }"
        )
        self.auto_generate_checkbox.setVisible(not edit_mode)
        layout.addWidget(self.auto_generate_checkbox)

        # Buttons
        btn = QHBoxLayout()
        btn.addStretch()
        cancel = QPushButton("取消")
        cancel.setStyleSheet(CANCEL_BTN_STYLE)
        cancel.clicked.connect(self.reject)
        btn.addWidget(cancel)
        confirm = QPushButton("保存" if edit_mode else "创建")
        confirm.setStyleSheet(GREEN_BTN_STYLE)
        confirm.clicked.connect(self._on_confirm)
        btn.addWidget(confirm)
        layout.addLayout(btn)

    def _select_color(self, clr, bi):
        self._selected_color = clr
        self._refresh_color_btns()

    def _refresh_color_btns(self):
        for i, b in enumerate(self.color_btns):
            selected = (ICON_COLORS[i] == self._selected_color)
            b.setStyleSheet(
                f"background:{ICON_COLORS[i]};border:none;border-radius:4px;"
                + ("border:2px solid white;outline:2px solid #07C160;" if selected else "")
            )

    def _on_confirm(self):
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "提示", "课题名称不能为空")
            return
        self._result = (title, self.desc_edit.toPlainText().strip(), self._selected_color,
                        self.auto_generate_checkbox.isChecked())
        self.accept()

    def get_result(self):
        return self._result


class _TestWorker(QThread):
    result_ready = pyqtSignal(bool, str)

    def __init__(self, api_key, base_url, model, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._base_url = base_url
        self._model = model

    def run(self):
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self._api_key, base_url=self._base_url)
            response = client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": "Reply with just: OK"}],
                max_tokens=10,
            )
            reply = response.choices[0].message.content
            self.result_ready.emit(True, f"连接成功！模型回复: {reply}")
        except Exception as e:
            self.result_ready.emit(False, f"连接失败: {e}")


class LLMSettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("大模型配置")
        self.setMinimumWidth(600)
        self.setMinimumHeight(550)
        self.setStyleSheet(DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 20, 24, 20)

        # --- Global settings ---
        layout.addWidget(QLabel("API Key"))
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-...")
        self.key_edit.setStyleSheet(INPUT_STYLE)
        layout.addWidget(self.key_edit)

        row = QHBoxLayout()
        row.setSpacing(8)
        col1 = QVBoxLayout()
        col1.addWidget(QLabel("Base URL"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://api.deepseek.com")
        self.url_edit.setStyleSheet(INPUT_STYLE)
        col1.addWidget(self.url_edit)
        row.addLayout(col1, 1)

        col2 = QVBoxLayout()
        col2.addWidget(QLabel("默认 Model"))
        self.model_edit = QLineEdit()
        self.model_edit.setPlaceholderText("deepseek-v4-flash")
        self.model_edit.setStyleSheet(INPUT_STYLE)
        col2.addWidget(self.model_edit)
        row.addLayout(col2, 1)
        layout.addLayout(row)

        # --- Agent tabs ---
        layout.addWidget(QLabel("Agent 角色配置"))
        self.agent_tabs = QTabWidget()
        self.agent_tabs.setStyleSheet(
            "QTabWidget::pane { border:1px solid #D0D0D0; background:#FFFFFF; }"
            "QTabBar::tab { background:#F0F0F0; color:#666666; padding:6px 14px;"
            "  border:none; border-top-left-radius:6px; border-top-right-radius:6px;"
            "  margin-right:2px; font-size:12px; }"
            "QTabBar::tab:selected { background:#FFFFFF; color:#111111; }"
            "QTabBar::tab:hover { background:#E8E8E8; color:#333333; }"
        )
        self._build_agent_tabs()
        layout.addWidget(self.agent_tabs, 1)

        # Status + buttons
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "color:#333333;font-size:12px;background:transparent;padding:4px 0;"
        )
        layout.addWidget(self.status_label)

        btn = QHBoxLayout()
        test_btn = QPushButton("测试连接")
        test_btn.setStyleSheet(CANCEL_BTN_STYLE)
        test_btn.clicked.connect(self._on_test)
        btn.addWidget(test_btn)
        btn.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(CANCEL_BTN_STYLE)
        cancel_btn.clicked.connect(self.reject)
        btn.addWidget(cancel_btn)
        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(GREEN_BTN_STYLE)
        save_btn.clicked.connect(self._on_save)
        btn.addWidget(save_btn)
        layout.addLayout(btn)

        self._load_settings()
        self._worker = None

    def _build_agent_tabs(self):
        from sqlmodel import Session, select
        from app.services.storage import get_engine
        from app.models.agent_config import AgentConfig as AgentCfg
        from PyQt6.QtWidgets import QTabWidget

        self.agent_tabs.clear()
        self._agent_tab_data = {}
        self._tab_index_to_id = {}

        with Session(get_engine()) as db:
            agents = db.exec(select(AgentCfg).order_by(AgentCfg.role)).all()

        for a in agents:
            self._add_agent_tab(a.id, a.name, a.model or "", a.system_prompt, a.color,
                                a.description or "")

        # "+" tab for adding new agent
        add_tab_btn = QPushButton("+")
        add_tab_btn.setFixedSize(28, 28)
        add_tab_btn.setStyleSheet(
            "QPushButton { background:#E8E8E8; color:#666666; border:none;"
            "border-radius:4px; font-size:16px; font-weight:bold; }"
            "QPushButton:hover { background:#07C160; color:#FFFFFF; }"
        )
        add_tab_btn.clicked.connect(self._on_add_agent_tab)
        self.agent_tabs.setCornerWidget(add_tab_btn, Qt.Corner.TopRightCorner)

    def _add_agent_tab(self, agent_id, name, model, prompt, color, desc=""):
        from PyQt6.QtWidgets import QWidget
        tab = QWidget()
        tab.setStyleSheet("background:#FFFFFF;")
        layout = QVBoxLayout(tab)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        # Name + Model row
        nr = QHBoxLayout()
        name_edit = QLineEdit(name)
        name_edit.setStyleSheet(INPUT_STYLE)
        name_edit.setPlaceholderText("Agent 名称")
        nr.addWidget(name_edit, 1)

        model_edit = QLineEdit(model)
        model_edit.setStyleSheet(INPUT_STYLE)
        model_edit.setPlaceholderText("模型名称（空=使用默认）")
        nr.addWidget(model_edit, 1)
        layout.addLayout(nr)

        # Description (one-line)
        layout.addWidget(QLabel("一句话描述"))
        desc_edit = QLineEdit(desc)
        desc_edit.setStyleSheet(INPUT_STYLE)
        desc_edit.setPlaceholderText("一句话描述 Agent 的作用")
        layout.addWidget(desc_edit)

        # System prompt
        layout.addWidget(QLabel("System Prompt"))
        prompt_edit = QTextEdit()
        prompt_edit.setPlainText(prompt)
        prompt_edit.setStyleSheet(TEXTEDIT_STYLE)
        prompt_edit.setMinimumHeight(120)
        layout.addWidget(prompt_edit, 1)

        # Delete button
        del_btn = QPushButton("删除此 Agent")
        del_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#E57373; border:1px solid #5A3030;"
            "border-radius:4px; padding:6px; }"
            "QPushButton:hover { background:#5A3030; }"
        )
        del_btn.clicked.connect(lambda: self._on_delete_agent_tab(agent_id))
        layout.addWidget(del_btn)

        idx = self.agent_tabs.count()
        self._agent_tab_data[agent_id] = (name_edit, model_edit, prompt_edit, desc_edit)
        self._tab_index_to_id[idx] = agent_id
        self.agent_tabs.addTab(tab, name[:12] or "Agent")

    def _on_add_agent_tab(self):
        import uuid as _uuid
        agent_id = _uuid.uuid4().hex
        self._add_agent_tab(agent_id, "新 Agent", "", "你是一个科研助手。", "#607D8B", "")
        self.agent_tabs.setCurrentIndex(self.agent_tabs.count() - 1)

    def _on_delete_agent_tab(self, agent_id):
        # Find tab index for this agent
        for i in range(self.agent_tabs.count()):
            if self._tab_index_to_id.get(i) == agent_id:
                self.agent_tabs.removeTab(i)
                # Rebuild index map
                self._rebuild_tab_index()
                break
        if agent_id in self._agent_tab_data:
            self._agent_tab_data[agent_id] = None  # mark deleted

    def _rebuild_tab_index(self):
        self._tab_index_to_id = {}
        # We can't easily map tab index→agent_id without tracking it.
        # Just rebuild from _agent_tab_data keys that aren't None.
        active_ids = [aid for aid, d in self._agent_tab_data.items() if d is not None]
        for i, aid in enumerate(active_ids):
            self._tab_index_to_id[i] = aid

    def _save_agents(self):
        from sqlmodel import Session
        from app.services.storage import get_engine
        from app.models.agent_config import AgentConfig as AgentCfg
        import uuid as _uuid

        with Session(get_engine()) as db:
            for agent_id, data in self._agent_tab_data.items():
                if data is None:  # mark deleted
                    agent = db.get(AgentCfg, agent_id)
                    if agent:
                        db.delete(agent)
                    continue

                name_edit, model_edit, prompt_edit, desc_edit = data
                new_name = name_edit.text().strip()
                new_model = model_edit.text().strip()
                new_prompt = prompt_edit.toPlainText().strip()
                new_desc = desc_edit.text().strip()

                agent = db.get(AgentCfg, agent_id)
                if agent:
                    agent.name = new_name or agent.name
                    agent.model = new_model
                    agent.system_prompt = new_prompt
                    agent.description = new_desc
                else:
                    db.add(AgentCfg(
                        id=agent_id, name=new_name or "Agent",
                        role=new_name or "agent",
                        model=new_model, system_prompt=new_prompt,
                        description=new_desc, color="#607D8B",
                    ))
            db.commit()

    def _load_settings(self):
        from app.config import settings
        self.key_edit.setText(settings.DEEPSEEK_API_KEY)
        self.url_edit.setText(settings.DEEPSEEK_BASE_URL)
        self.model_edit.setText(settings.LLM_MODEL)

    def _on_test(self):
        key = self.key_edit.text().strip()
        url = self.url_edit.text().strip()
        model = self.model_edit.text().strip()

        if not key:
            self.status_label.setText("请先填写 API Key")
            self.status_label.setStyleSheet("color:#FA5151;background:transparent;padding:4px 0;")
            return
        if not url:
            self.status_label.setText("请先填写 Base URL")
            self.status_label.setStyleSheet("color:#FA5151;background:transparent;padding:4px 0;")
            return
        if not model:
            self.status_label.setText("请先填写 Model")
            self.status_label.setStyleSheet("color:#FA5151;background:transparent;padding:4px 0;")
            return

        self.status_label.setText("正在测试连接...")
        self.status_label.setStyleSheet("color:#888888;background:transparent;padding:4px 0;")
        self._worker = _TestWorker(key, url, model)
        self._worker.result_ready.connect(self._on_test_result)
        self._worker.start()

    def _on_test_result(self, success, message):
        color = "#07C160" if success else "#FA5151"
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color:{color};background:transparent;padding:4px 0;")

    def _on_save(self):
        key = self.key_edit.text().strip()
        url = self.url_edit.text().strip()
        model = self.model_edit.text().strip()

        env_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"
        )
        lines = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()

        updated = {"DEEPSEEK_API_KEY": key, "DEEPSEEK_BASE_URL": url, "LLM_MODEL": model}
        found = set()
        new_lines = []
        for line in lines:
            wrote = False
            for k, v in updated.items():
                if line.startswith(f"{k}="):
                    new_lines.append(f"{k}={v}\n")
                    found.add(k)
                    wrote = True
                    break
            if not wrote:
                new_lines.append(line)
        for k, v in updated.items():
            if k not in found:
                new_lines.append(f"{k}={v}\n")

        with open(env_path, "w") as f:
            f.writelines(new_lines)

        from app.config import settings as app_settings
        app_settings.DEEPSEEK_API_KEY = key
        app_settings.DEEPSEEK_BASE_URL = url
        app_settings.LLM_MODEL = model

        self._save_agents()
        self.accept()
