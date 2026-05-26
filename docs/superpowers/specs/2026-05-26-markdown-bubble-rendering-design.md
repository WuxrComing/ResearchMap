# Markdown Bubble Rendering — Height Estimation Fix

## Problem

`_MessageBubble._make_bubble` estimates bubble dimensions using `QFontMetrics` on **plain Markdown text**, but the actual content is **rendered HTML**. The mismatch causes bubbles to be too short (content truncated).

Root causes:
1. **Width estimated from plain text, not HTML** — `QFontMetrics(13px)` doesn't account for `<h1>` larger fonts, `<code>` monospace, `<li>` indentation, etc.
2. **`setTextWidth` / widget width / document margin mismatch** — the three values don't align, causing the document to wrap at the wrong width.
3. **Height read at wrong text width** — `doc.size().height()` after `setHtml()` reflects layout at the miscalculated width.

## Fix

Replace the plain-text width estimation with a **post-render measurement** approach. Single file: `app/ui/chat_view.py`, `_MessageBubble._make_bubble` method.

### Algorithm (replaces lines 114-135)

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
```

### Key insight

`QTextDocument.idealWidth()` returns the actual width needed for the rendered HTML — it accounts for headings, code blocks, lists, tables, and all other HTML elements. Measuring *after* rendering eliminates the plain-text-vs-HTML mismatch.

### Cleanup

Remove `QFontMetrics` from the import on line 7. (`QFont` is still used to set the base font on the QTextEdit.)

## Not modified

- `_make_system` — stays QLabel
- Avatar, name label, layout structure
- All sending, auto-collaboration, status widget logic
