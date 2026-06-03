# Research: PyQt5 Minimal UI for Settings Tab with Prompt Editing

- **Query**: PyQt5 elegant minimal UI implementations for a settings tab that displays and edits text prompts
- **Scope**: Mixed (internal codebase + external references)
- **Date**: 2026-06-03

## Findings

### 1. Tab Widget Best Practices for Settings Pages

#### Pattern: QTabWidget inside QDialog

The standard pattern for settings in PyQt5 is a `QDialog` subclass containing a `QTabWidget` that organizes settings into categorized tabs. Each tab is a `QWidget` with its own layout, wrapped in a `QScrollArea` for overflow handling.

Key API:
- `QTabWidget.addTab(widget, label)` -- add a tab page
- `QTabWidget.setTabPosition()` -- North/South/East/West
- `QTabBar::tab:selected` -- style the active tab differently
- `QTabWidget::pane` -- style the content area border

**Best practices from sources:**
- Use a `QWidget` for each tab page, with its own `QVBoxLayout` or `QGridLayout`
- Wrap each tab content in `QScrollArea` with `setWidgetResizable(True)` for overflow
- Use `QGroupBox` to cluster related settings with a labeled border
- Use `QSettings` for persisting settings across sessions
- For immediate-apply behavior, connect widget signals directly to update logic

**This project already implements this pattern** in `src/ui/main_window.py:27-278` (`SettingsDialog` class) with two tabs ("基础设置" and "AI 高级设置").

#### Minimalist Tab Styling (QSS)

For a clean, thin-border look, the existing project style in `src/ui/styles.py:376-486` (`SETTINGS_DIALOG_STYLE`) already defines:

```css
QTabWidget::pane {
    border: 1px solid #E5E7EB;    /* thin border */
    border-radius: 6px;
    background-color: #FFFFFF;
}

QTabBar::tab {
    background-color: #F3F4F6;     /* light gray inactive */
    color: #6B7280;                /* secondary text */
    padding: 10px 20px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}

QTabBar::tab:selected {
    background-color: #FFFFFF;     /* white active */
    color: #1F2937;                /* primary text */
    font-weight: bold;
}
```

**For an even more minimal aesthetic** (no tab frame, underline indicator only):
```css
QTabWidget::pane { border: none; border-top: 1px solid #E5E7EB; }
QTabBar::tab {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 8px 16px;
}
QTabBar::tab:selected {
    border-bottom: 2px solid #3B82F6;  /* accent underline */
    color: #1F2937;
}
QTabBar::tab:hover:!selected {
    color: #3B82F6;
    border-bottom: 2px solid #E5E7EB;  /* subtle hover indicator */
}
```

### 2. Text Editor for Long Content (Prompt Editing)

#### QPlainTextEdit vs QTextEdit

| Aspect | QPlainTextEdit | QTextEdit |
|--------|---------------|-----------|
| Optimized for | Plain text, large documents | Rich text (HTML, formatting) |
| Document layout | QPlainTextDocumentLayout (line-by-line) | QTextDocumentLayout (pixel-exact) |
| Performance with large text | Better (paragraph-based scrolling) | Slower (pixel-precise height calc) |
| Rich text / tables | Not supported | Supported |
| Line wrap resize | Fast | Slower |
| Monospace support | Same as QTextEdit | Same as QPlainTextEdit |
| Key methods | `setPlainText()`, `toPlainText()`, `appendPlainText()` | `setHtml()`, `toHtml()`, `setPlainText()` |

**Recommendation for prompt editing: QPlainTextEdit**

Rationale:
- Prompts are plain text (no HTML needed)
- Can be long (hundreds of lines) -- QPlainTextEdit handles large documents better
- Simpler API surface reduces bugs
- Same signal: `textChanged()` available on both

**Setting monospace font on QPlainTextEdit** (cross-platform):
```python
from PyQt5.QtGui import QFont, QFontDatabase

# Method 1: System fixed font (recommended)
fixedfont = QFontDatabase.systemFont(QFontDatabase.FixedFont)
fixedfont.setPointSize(12)
editor.setFont(fixedfont)

# Method 2: Generic monospace family
font = QFont("Monospace")
font.setStyleHint(QFont.TypeWriter)
editor.setFont(font)

# Method 3: Specific font
font = QFont("Courier New")  # Windows default mono
editor.setFont(font)
```

**QPlainTextEdit configuration for prompt editing:**
```python
editor = QPlainTextEdit()
editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)  # wrap at widget edge
editor.setPlaceholderText("Enter prompt text...")
editor.setTabChangesFocus(False)  # allow tab in text
editor.setUndoRedoEnabled(True)
# Optional: limit block count for log-like behavior
# editor.setMaximumBlockCount(1000)
```

### 3. Minimalist/Elegant UI Patterns

#### Color Palette (matching existing project style)

The project already uses a clean, light theme defined in `src/ui/styles.py:8-37`:

| Token | Hex | Usage |
|-------|-----|-------|
| background | #FFFFFF | Main background |
| card | #FFFFFF | Card / editor background |
| sidebar | #FAFBFC | Secondary surfaces |
| sidebar_hover | #F3F4F6 | Hover states |
| sidebar_active | #EBF5FF | Active / selected |
| border | #E5E7EB | Primary borders (thin 1px) |
| border_light | #F3F4F6 | Subtle dividers |
| text_primary | #1F2937 | Main text |
| text_secondary | #6B7280 | Labels, descriptions |
| text_light | #9CA3AF | Disabled / placeholder |
| primary | #3B82F6 | Accent, focus borders |

This palette is already well-suited for a minimalist aesthetic. Key principles:

1. **Thin borders**: Use `1px solid #E5E7EB` -- the existing pattern
2. **Subtle hover**: Background shift to `#F3F4F6`, no border change
3. **Focus indicator**: Border color shift to `#3B82F6` (primary blue)
4. **Clear hierarchy**: Title 15px bold, label 13px secondary, description 11px light
5. **Spacing**: 16-24px margins between sections, 12px between items

#### External Reference: qt-modern-style (PyPI package)

`qt-modern-style` v2.0.1 provides a similar palette with 500+ SVG icons. Its color tokens:
- BG: `#FFFFFF`, BG-Soft: `#F3F6FA`, Border: `#C9D3DF`
- Text: `#2B3442`, Muted: `#98A6B8`, Accent: `#2F6FED`

This closely matches the existing project palette, confirming the design direction is standard.

#### External Reference: qt-for-python-qss (GitHub)

Chinese-language QSS collection (`shenxingchao/qt-for-python-qss`) with Ant Design-inspired tokens:
- Primary: `#1890ff`, Border: `#d9d9d9`, Background: `#ffffff`
- Tab styling: `padding: 10px 20px`, border-radius: 0 for flat look

#### QPlainTextEdit Minimalist Styling

```css
QPlainTextEdit {
    background-color: #FFFFFF;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    padding: 12px 16px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 13px;
    color: #1F2937;
    selection-background-color: #EBF5FF;
}

QPlainTextEdit:focus {
    border-color: #3B82F6;
}
```

### 4. Live Preview / Real-Time Update Patterns

#### Core Signal-Slot Pattern

Both `QPlainTextEdit` and `QTextEdit` emit `textChanged()` signal on every edit. Connect to a slot for real-time updates:

```python
editor.textChanged.connect(self._on_prompt_changed)
```

**Caveat: `textChanged()` fires very frequently** (on every keystroke). For expensive operations (e.g., API calls), use debouncing:

```python
from PyQt5.QtCore import QTimer

class DebouncedEditor(QPlainTextEdit):
    def __init__(self, delay_ms=500, parent=None):
        super().__init__(parent)
        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._debounced_text_changed)
        self.textChanged.connect(self._schedule_update)

    def _schedule_update(self):
        self._timer.start()  # restart timer on each keystroke

    def _debounced_text_changed(self):
        # This fires only after user stops typing for delay_ms
        self.debound_text_available.emit(self.toPlainText())
```

#### Preventing Infinite Signal Loops

When programmatically updating text (e.g., loading saved prompt), use `blockSignals(True)`:

```python
def load_prompt(self, text: str):
    self.editor.blockSignals(True)
    self.editor.setPlainText(text)
    self.editor.blockSignals(False)
```

#### Pattern: Dual-Pane Edit + Preview

For live preview of prompt effects (if needed), use a horizontal splitter:

```python
from PyQt5.QtWidgets import QSplitter

splitter = QSplitter(Qt.Horizontal)
editor = QPlainTextEdit()     # left: edit pane
preview = QTextEdit()         # right: preview (read-only)
preview.setReadOnly(True)

editor.textChanged.connect(lambda: preview.setHtml(format_preview(editor.toPlainText())))

splitter.addWidget(editor)
splitter.addWidget(preview)
splitter.setSizes([500, 500])
```

**Note**: Live markdown preview within the SAME QTextEdit widget is unreliable. `setHtml()` resets cursor position and can cause infinite `textChanged` loops. Use separate widgets.

### Files Found

| File Path | Description |
|---|---|
| `src/ui/styles.py` | Existing style definitions (COLORS dict, MAIN_STYLE, SETTINGS_DIALOG_STYLE) |
| `src/ui/main_window.py` | Existing SettingsDialog with QTabWidget pattern (lines 27-278) |
| `src/ui/widgets/progress_card.py` | Uses QTextEdit for log output (line 72) |
| `src/ui/pages/report_page.py` | Uses QTextEdit for summary display (line 87) |
| `src/llm/audit_agent.py` | Contains REPORT_SYSTEM_PROMPT and QA_SYSTEM_PROMPT (lines 21-51) |
| `src/llm/data_normalizer.py` | Contains SYSTEM_PROMPT_DATA_NORMALIZER (line 15) |
| `src/llm/flow_table_classifier.py` | Contains SYSTEM_PROMPT_FLOW_TABLE_CLASSIFIER (line 17) |
| `src/config.py` | Config class with YAML persistence, dot-notation get/set (lines 17-264) |

### Existing Prompts in Codebase (to be editable via the new tab)

| Prompt Constant | File | Line | Description |
|---|---|---|---|
| `REPORT_SYSTEM_PROMPT` | `src/llm/audit_agent.py` | 21 | Audit report writing assistant |
| `QA_SYSTEM_PROMPT` | `src/llm/audit_agent.py` | 41 | Audit QA assistant |
| `SYSTEM_PROMPT_DATA_NORMALIZER` | `src/llm/data_normalizer.py` | 15 | Flow data normalization expert |
| `SYSTEM_PROMPT_FLOW_TABLE_CLASSIFIER` | `src/llm/flow_table_classifier.py` | 17 | Flow table identification expert |

### External References

- [PythonGUIs: How to Create a Settings Window](https://www.pythonguis.com/faq/create-a-settings-window/) -- QTabWidget + QSettings pattern
- [StackOverflow: QTextEdit vs QPlainTextEdit](https://stackoverflow.com/questions/17466046/qtextedit-vs-qplaintextedit) -- Performance comparison, QPlainTextEdit optimized for large plain text
- [PyQt5 QPlainTextEdit API](https://www.riverbankcomputing.com/static/Docs/PyQt5/api/qtwidgets/qplaintextedit.html) -- setPlainText, toPlainText, placeholderText, lineWrapMode
- [PyQt5 QTextEdit API](https://www.riverbankcomputing.com/static/Docs/PyQt5/api/qtwidgets/qtextedit.html) -- textChanged signal, setHtml, setPlainText
- [Qt Forum: Setting monospace font on QPlainTextEdit](https://forum.qt.io/topic/35999/) -- Cross-platform monospace via `QFont("Monospace"); font.setStyleHint(QFont.TypeWriter)`
- [PythonGUIs: PyQt5 Signals and Slots](https://www.pythonguis.com/tutorials/pyqt-signals-slots-events/) -- textChanged signal, connecting to slots
- [StackOverflow: QTextEdit textChanged fires too frequently](https://www.qtcentre.org/threads/49516/) -- Use blockSignals or boolean lock flag to prevent loops
- [StackOverflow: PyQt5 Live markdown preview](https://stackoverflow.com/questions/78254473/) -- Single-widget live preview unreliable; use separate edit + preview widgets
- [qt-modern-style (PyPI)](https://pypi.org/project/qt-modern-style/) -- Modern Qt stylesheet package, similar color palette
- [qt-for-python-qss (GitHub)](https://github.com/shenxingchao/qt-for-python-qss) -- Ant Design-inspired QSS tokens
- [QDarkStyleSheet (GitHub)](https://github.com/ColinDuquesnoy/QDarkStyleSheet) -- Most complete dark/light Qt stylesheet
- [PythonGUIs: Build a Notepad with PyQt5](https://www.pythonguis.com/examples/python-notepad-clone/) -- QPlainTextEdit with QFontDatabase.FixedFont at 12pt

### Related Specs

- `.trellis/spec/backend/directory-structure.md` -- Project directory layout
- `.trellis/spec/backend/quality-guidelines.md` -- Quality guidelines

## Caveats / Not Found

- **No existing "prompt editing" UI**: The current SettingsDialog has no prompt/text editing tab. All prompts are hardcoded as Python string constants. A new tab is needed.
- **Config does not store prompts**: `src/config.py` has no `prompts` section. Prompts will need either (a) new config keys in `config.yaml`, or (b) a separate prompts storage mechanism.
- **QPlainTextEdit is not in the current import list**: `src/ui/main_window.py` imports `QTextEdit` but not `QPlainTextEdit`. Will need to add the import.
- **Debounce utility not in codebase**: No existing debounce/timer pattern. Will need to implement if live-update is required.
- **No QSplitter usage currently**: The project does not use `QSplitter` anywhere. Will need to import if dual-pane edit+preview is needed.
