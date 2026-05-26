"""Replacement for qfluentwidgets InfoBar - simple toast notification."""
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout, QApplication
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QPoint
from PyQt6.QtGui import QColor


class Toast(QFrame):
    """A small auto-hiding notification popup positioned at top-right of parent."""

    def __init__(self, parent, title: str, content: str, is_error: bool = False):
        super().__init__(parent)
        self.setObjectName("toast")
        self.setMinimumWidth(280)
        self.setMaximumWidth(400)

        color = "#FA5151" if is_error else "#07C160"
        self.setStyleSheet(
            f"QFrame#toast {{ background: white; border-left: 4px solid {color};"
            f"border-radius: 6px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        text_col = QVBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"color:#1F1F1F;font-weight:bold;font-size:13px;")
        text_col.addWidget(title_lbl)

        content_lbl = QLabel(content)
        content_lbl.setWordWrap(True)
        content_lbl.setStyleSheet("color:#666;font-size:12px;")
        text_col.addWidget(content_lbl)

        layout.addLayout(text_col, 1)

        self.adjustSize()

        if parent:
            px = parent.width() - self.width() - 20
            py = 50
            self.move(px, py)
        self.raise_()

        QTimer.singleShot(3000, self._fade_out)

    def _fade_out(self):
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(300)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.finished.connect(self.deleteLater)
        self.animation.start()
