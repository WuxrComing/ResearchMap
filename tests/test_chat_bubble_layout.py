import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QLabel, QScrollArea, QTextEdit, QVBoxLayout, QWidget

from app.ui.chat_view import _MessageBubble


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_agent_bubble_keeps_calculated_height_fixed(qapp):
    content = (
        "这是一段较长的 Agent 回复，用来触发多行自动换行和高度计算。" * 20
        + "\n\n"
        + "\n".join(f"列表项 {i}: 内容内容内容内容内容" for i in range(1, 16))
    )

    window = QWidget()
    layout = QVBoxLayout(window)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    container = QWidget()
    container_layout = QVBoxLayout(container)
    bubble = _MessageBubble("assistant", content, "Topic Agent")
    container_layout.addWidget(bubble)
    container_layout.addStretch()
    scroll.setWidget(container)
    layout.addWidget(scroll)
    window.resize(520, 600)
    window.show()
    qapp.processEvents()

    text_edit = bubble.findChild(QTextEdit)

    assert text_edit is not None
    assert text_edit.minimumHeight() == text_edit.maximumHeight()
    assert text_edit.height() == text_edit.maximumHeight()
    assert text_edit.verticalScrollBar().maximum() == 0


def test_short_user_bubble_does_not_wrap_each_character(qapp):
    bubble = _MessageBubble("user", "你好")
    text_edit = bubble.findChild(QTextEdit)

    assert text_edit is not None
    assert text_edit.document().firstBlock().layout().lineCount() == 1
    assert text_edit.height() <= 32


def test_short_user_name_label_uses_content_height(qapp):
    bubble = _MessageBubble("user", "你好")
    bubble.resize(520, 120)
    bubble.show()
    qapp.processEvents()

    text_edit = bubble.findChild(QTextEdit)
    name_label = next(
        label for label in bubble.findChildren(QLabel)
        if label.text() == "我" and label.width() != 34
    )
    avatar = next(
        label for label in bubble.findChildren(QLabel)
        if label.text() == "我" and label.width() == 34 and label.height() == 34
    )

    assert text_edit is not None
    assert name_label.height() <= 20
    assert name_label.y() == avatar.y()
    assert text_edit.y() <= name_label.geometry().bottom() + 4


def test_agent_bubble_renders_html_and_keeps_measured_height(qapp):
    content = (
        "<p><strong>结论</strong>：HTML 内容应按富文本渲染。</p>"
        "<ul><li>第一项包含较长文本，用来触发自动换行和高度计算。</li>"
        "<li>第二项</li></ul>"
    )

    window = QWidget()
    layout = QVBoxLayout(window)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    container = QWidget()
    container_layout = QVBoxLayout(container)
    bubble = _MessageBubble("assistant", content, "Topic Agent")
    container_layout.addWidget(bubble)
    container_layout.addStretch()
    scroll.setWidget(container)
    layout.addWidget(scroll)
    window.resize(520, 600)
    window.show()
    qapp.processEvents()

    text_edit = bubble.findChild(QTextEdit)

    assert text_edit is not None
    assert "<strong>" not in text_edit.toPlainText()
    assert text_edit.verticalScrollBar().maximum() == 0
    assert text_edit.minimumHeight() == text_edit.maximumHeight()


def test_agent_bubble_renders_markdown_tables_and_emphasis(qapp):
    content = (
        "**结论**：支持 *Markdown* 渲染。\n\n"
        "| 方向 | 状态 |\n"
        "| --- | --- |\n"
        "| 加粗 | 已支持 |\n"
        "| 表格 | 已支持 |"
    )

    window = QWidget()
    layout = QVBoxLayout(window)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    container = QWidget()
    container_layout = QVBoxLayout(container)
    bubble = _MessageBubble("assistant", content, "Topic Agent")
    container_layout.addWidget(bubble)
    container_layout.addStretch()
    scroll.setWidget(container)
    layout.addWidget(scroll)
    window.resize(520, 600)
    window.show()
    qapp.processEvents()

    text_edit = bubble.findChild(QTextEdit)
    html = text_edit.toHtml()

    assert text_edit is not None
    assert "**结论**" not in text_edit.toPlainText()
    assert "*Markdown*" not in text_edit.toPlainText()
    assert "<table" in html
    assert "font-weight" in html or "<strong" in html
    assert "font-style" in html or "<em" in html
    assert text_edit.verticalScrollBar().maximum() == 0
