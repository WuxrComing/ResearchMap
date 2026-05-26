# Markdown Bubble Height Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix chat bubble height estimation by replacing plain-text QFontMetrics measurement with post-render QTextDocument.idealWidth() measurement.

**Architecture:** Single-method fix in `_MessageBubble._make_bubble`. Instead of measuring plain Markdown text to guess bubble width before rendering HTML, render HTML first at max width, then use `doc.idealWidth()` to get the actual content width from the rendered document. This eliminates the plain-text-vs-HTML font metric mismatch.

**Tech Stack:** Python, PyQt6, markdown2

---

### Task 1: Replace width/height estimation logic in `_make_bubble`

**Files:**
- Modify: `app/ui/chat_view.py:110-136`

- [ ] **Step 1: Replace lines 110-136 with post-render measurement approach**

Remove the QFontMetrics-based width estimation (lines 113-136) and the `max_bubble_w`/`doc_pad_w` declarations on lines 110-111, replacing with the new logic.

**Before (lines 110-136):**
```python
        max_bubble_w = 420
        doc_pad_w = 20  # document margin 10 * 2

        # Step 1: determine target width (shrink-wrap narrow content)
        fm = QFontMetrics(font)
        max_content_w = max_bubble_w - doc_pad_w

        lines = content.split("\n") if content else [""]
        max_line_w = max((fm.horizontalAdvance(line) for line in lines), default=0)

        if max_line_w <= max_content_w:
            target_w = int(max_line_w) + doc_pad_w + 6
        else:
            target_w = max_bubble_w

        # Step 2: set width on both widget and document before setHtml
        bubble.setFixedWidth(target_w)
        doc.setTextWidth(target_w)

        # Step 3: set HTML after width is fixed
        bubble.setHtml(html)

        # Step 4: measure height at final width
        doc_h = doc.size().height()
        bubble.setFixedHeight(int(doc_h))
        bubble.setMinimumHeight(34)
        bubble.setMinimumHeight(34)
```

**After:**
```python
        max_bubble_w = 420
        doc_pad_w = 20  # document margin 10 * 2

        # Step 1: render HTML at max width
        doc.setTextWidth(max_bubble_w - doc_pad_w)
        bubble.setHtml(html)

        # Step 2: read actual content width from rendered document
        ideal_w = doc.idealWidth()
        text_w = min(int(ideal_w), max_bubble_w - doc_pad_w)

        # Step 3: re-set to final width (shrink-wraps narrow content)
        doc.setTextWidth(text_w)

        # Step 4: set widget dimensions from actual document size
        bubble.setFixedWidth(text_w + doc_pad_w)
        bubble.setFixedHeight(int(doc.size().height()))
        bubble.setMinimumHeight(34)
```

- [ ] **Step 2: Verify the edit reads correctly**

Run: `sed -n '110,136p' app/ui/chat_view.py`
Expected: The new code block as shown above (lines may shift slightly).

---

### Task 2: Remove unused `QFontMetrics` import

**Files:**
- Modify: `app/ui/chat_view.py:7`

- [ ] **Step 1: Change the import line**

**Before:**
```python
from PyQt6.QtGui import QFont, QFontMetrics
```

**After:**
```python
from PyQt6.QtGui import QFont
```

- [ ] **Step 2: Verify no remaining QFontMetrics references**

Run: `grep -n "QFontMetrics" app/ui/chat_view.py`
Expected: No output (no matches).

---

### Task 3: Verification

- [ ] **Step 1: Check Python syntax**

Run: `cd /Volumes/d/Programming/ResearchMap && python -c "import ast; ast.parse(open('app/ui/chat_view.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 2: Run existing tests**

Run: `cd /Volumes/d/Programming/ResearchMap && python -m pytest tests/ -v --timeout=10 2>&1 | tail -20`
Expected: All tests pass (no regressions).

- [ ] **Step 3: Manual smoke test**

Launch the app and send messages with various Markdown content types (headings, code blocks, lists, bold, long paragraphs). Verify:
- Bubbles are no longer truncated at the bottom
- Short messages still shrink-wrap correctly
- Long messages cap at 420px and wrap properly
