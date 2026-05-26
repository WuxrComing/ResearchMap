# Markdown Bubble Rendering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace QLabel with QTextEdit in chat bubbles to support Markdown rendering via markdown2.

**Architecture:** Use `markdown2` to convert Markdown content to HTML, then render via `QTextEdit.setHtml()`. QTextEdit is read-only, borderless, and auto-sizes height to content.

**Tech Stack:** PyQt6, markdown2

---

### Task 1: Add markdown2 dependency

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add markdown2 to dependencies**

```toml
dependencies = [
    "pyqt6>=6.7.0",
    "sqlmodel>=0.0.22",
    "openai>=1.55.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "httpx>=0.27.0",
    "jinja2>=3.1.0",
    "markdown2>=2.5.0",
]
```

- [ ] **Step 2: Install the dependency**

Run: `pip install markdown2`
Expected: Package installs successfully

- [ ] **Step 3: Verify import**

Run: `python -c "import markdown2; print(markdown2.markdown('**bold**'))"`
Expected: Output contains `<strong>bold</strong>`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add markdown2 dependency for bubble rendering"
```

---

### Task 2: Replace QLabel with QTextEdit in _MessageBubble._make_bubble

**Files:**
- Modify: `app/ui/chat_view.py:53-113`

- [ ] **Step 1: Add markdown2 import at top of file**

Add `import markdown2` after the PyQt6 imports block (around line 8).

- [ ] **Step 2: Replace QLabel bubble with QTextEdit**

Replace lines 71-112 (the QLabel bubble block inside `_make_bubble`) with the QTextEdit version:

```python
        # Use QTextEdit for Markdown rendering
        from PyQt6.QtWidgets import QTextEdit
        import markdown2

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

        text_color = "#000000" if is_user else TEXT_PRIMARY
        bubble.setStyleSheet(
            f"padding:10px 14px;border-radius:4px;font-size:13px;color:{text_color};"
            f"background:{BUBBLE_SELF if is_user else BUBBLE_OTHER};"
            + ("border:1px solid #3D4A44;" if not is_user else "")
        )

        font = QFont()
        font.setPixelSize(13)
        bubble.setFont(font)

        # Convert Markdown to HTML and set content
        html = markdown2.markdown(
            content,
            extras=["tables", "fenced-code-blocks", "break-on-newline", "task-lists"]
        )
        bubble.setHtml(html)

        # Auto-size: measure document and fix width/height
        max_bubble_w = 420
        doc_width = int(bubble.document().size().width())
        target_w = min(doc_width + 28 + 6, max_bubble_w)  # padding + buffer
        bubble.setFixedWidth(target_w)

        doc_height = int(bubble.document().size().height())
        bubble.setFixedHeight(doc_height + 20)  # padding
```

- [ ] **Step 3: Remove unused QFontMetrics import check**

Verify `QFontMetrics` is no longer used in the file. If it's only used in the removed bubble code, remove it from the import line.

- [ ] **Step 4: Run the app and verify visually**

Run: `python -m app.main`
Expected: Chat bubbles render Markdown (bold, italic, code, lists, etc.)

- [ ] **Step 5: Commit**

```bash
git add app/ui/chat_view.py
git commit -m "feat: render chat bubbles with Markdown via QTextEdit + markdown2"
```
