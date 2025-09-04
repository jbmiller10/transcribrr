import sys
import os
import logging
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QTextEdit,
    QToolBar,
    QColorDialog,
    QWidget,
    QWidgetAction,
    QFontComboBox,
    QComboBox,
    QSizePolicy,
    QLabel,
    QToolButton,
    QMenu,
    QFileDialog,
    QMessageBox,
    QPushButton,
    QStatusBar,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QCheckBox,
    QLineEdit,
)
from PyQt6.QtGui import (
    QIcon,
    QFont,
    QColor,
    QTextListFormat,
    QActionGroup,
    QTextCursor,
    QAction,
    QTextCharFormat,
    QKeySequence,
    QTextDocument,
    QShortcut,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QTimer
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog

from app.path_utils import resource_path
from app.ui_utils.icon_utils import load_icon

from app.ui_utils import SpinnerManager, show_error_message, show_info_message

logger = logging.getLogger("transcribrr")


class FindReplaceDialog(QDialog):

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Find and Replace")
        self.setModal(False)
        self.setMinimumWidth(450)

        self.search_wrapped = False

        self.search_start_position = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        find_layout = QHBoxLayout()
        find_label = QLabel("Find:")
        self.find_text = QLineEdit()
        self.find_text.setPlaceholderText("Enter text to find")
        self.find_text.returnPressed.connect(self.find_next)
        find_layout.addWidget(find_label)
        find_layout.addWidget(self.find_text)
        layout.addLayout(find_layout)

        replace_layout = QHBoxLayout()
        replace_label = QLabel("Replace:")
        self.replace_text = QLineEdit()
        self.replace_text.setPlaceholderText("Enter replacement text")
        self.replace_text.returnPressed.connect(self.replace)
        replace_layout.addWidget(replace_label)
        replace_layout.addWidget(self.replace_text)
        layout.addLayout(replace_layout)

        options_layout = QVBoxLayout()

        basic_options_layout = QHBoxLayout()
        self.case_sensitive = QCheckBox("Case sensitive")
        self.whole_words = QCheckBox("Whole words only")
        self.search_backwards = QCheckBox("Search backwards")
        basic_options_layout.addWidget(self.case_sensitive)
        basic_options_layout.addWidget(self.whole_words)
        basic_options_layout.addWidget(self.search_backwards)
        options_layout.addLayout(basic_options_layout)

        adv_options_layout = QHBoxLayout()
        self.highlight_all = QCheckBox("Highlight matches")
        self.highlight_all.stateChanged.connect(self.toggle_highlight_all)
        adv_options_layout.addWidget(self.highlight_all)
        options_layout.addLayout(adv_options_layout)

        layout.addLayout(options_layout)

        button_layout = QHBoxLayout()
        self.find_button = QPushButton("Find Next")
        self.find_prev_button = QPushButton("Find Previous")
        self.replace_button = QPushButton("Replace")
        self.replace_all_button = QPushButton("Replace All")
        self.close_button = QPushButton("Close")

        button_layout.addWidget(self.find_button)
        button_layout.addWidget(self.find_prev_button)
        button_layout.addWidget(self.replace_button)
        button_layout.addWidget(self.replace_all_button)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        self.find_button.clicked.connect(self.find_next)
        self.find_prev_button.clicked.connect(self.find_previous)
        self.replace_button.clicked.connect(self.replace)
        self.replace_all_button.clicked.connect(self.replace_all)
        self.close_button.clicked.connect(self.close)
        self.find_text.textChanged.connect(self.update_buttons)

        self.case_sensitive.stateChanged.connect(self.reset_search)
        self.whole_words.stateChanged.connect(self.reset_search)

        self.finished.connect(self.cleanup_on_close)

        self.update_buttons()

        self.highlight_format = QTextCharFormat()
        self.highlight_format.setBackground(
            QColor(255, 255, 0, 100)
        )  # Light yellow with transparency

        self.original_selection_formats = []

    def reset_search(self):
        self.search_wrapped = False
        self.search_start_position = None
        self.status_label.clear()

        if self.highlight_all.isChecked():
            self.toggle_highlight_all(self.highlight_all.checkState())

    def update_buttons(self):
        has_find_text = bool(self.find_text.text())
        self.find_button.setEnabled(has_find_text)
        self.find_prev_button.setEnabled(has_find_text)
        self.replace_button.setEnabled(has_find_text)
        self.replace_all_button.setEnabled(has_find_text)

        if has_find_text:
            self.status_label.setText("Ready to search")
        else:
            self.status_label.clear()

    def get_search_flags(self):
        flags = QTextDocument.FindFlag(0)
        if self.case_sensitive.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.whole_words.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords
        if self.search_backwards.isChecked() or self._is_find_previous:
            flags |= QTextDocument.FindFlag.FindBackward

        return flags

    def find_next(self):
        self._is_find_previous = False
        return self._find_text()

    def find_previous(self):
        self._is_find_previous = True
        return self._find_text()

    def _find_text(self):
        text = self.find_text.text()
        if not text:
            return False

        # Get cursor and save position if first search
        cursor = self.editor.editor.textCursor()
        if self.search_start_position is None:
            self.search_start_position = cursor.position()
            self.search_wrapped = False

        # Set search flags
        flags = self.get_search_flags()

        # Find text
        found = self.editor.editor.find(text, flags)

        if not found:
            # If we've already wrapped, show not found
            if self.search_wrapped:
                self.status_label.setText(f"No occurrences of '{text}' found.")
                # Reset for next search
                self.search_wrapped = False
                cursor.setPosition(self.search_start_position)
                self.editor.editor.setTextCursor(cursor)
                return False

            # If not found and we haven't wrapped yet, try from beginning or end
            if flags & QTextDocument.FindFlag.FindBackward:
                # If searching backwards, start from the end
                cursor.movePosition(QTextCursor.MoveOperation.End)
            else:
                # If searching forwards, start from the beginning
                cursor.movePosition(QTextCursor.MoveOperation.Start)

            self.editor.editor.setTextCursor(cursor)
            found = self.editor.editor.find(text, flags)

            if found:
                self.search_wrapped = True
                self.status_label.setText(
                    "Search wrapped to the beginning/end")
            else:
                self.status_label.setText(f"No occurrences of '{text}' found.")
                cursor.setPosition(self.search_start_position)
                self.editor.editor.setTextCursor(cursor)
        else:
            if self.search_wrapped:
                self.status_label.setText(
                    "Search wrapped to the beginning/end")
            else:
                self.status_label.setText(f"Found '{text}'")

        return found

    def replace(self):
        """Replace current selection."""
        cursor = self.editor.editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_text.text())
            self.status_label.setText("Replaced one occurrence")

        # Find the next occurrence
        self._is_find_previous = False  # Always find next after replace
        self._find_text()

    def replace_all(self):
        """Replace all occurrences."""
        text = self.find_text.text()
        replacement = self.replace_text.text()

        if not text:
            return

        # Begin undo sequence
        self.editor.editor.document().beginEditBlock()

        try:
            # Save cursor position
            cursor = self.editor.editor.textCursor()
            cursor_position = cursor.position()

            # Move to beginning
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.editor.editor.setTextCursor(cursor)

            # Set search flags - always forward for replace all
            flags = QTextDocument.FindFlag(0)
            if self.case_sensitive.isChecked():
                flags |= QTextDocument.FindFlag.FindCaseSensitively
            if self.whole_words.isChecked():
                flags |= QTextDocument.FindFlag.FindWholeWords

            # Count and replace all occurrences
            count = 0
            while self.editor.editor.find(text, flags):
                # Replace text
                cursor = self.editor.editor.textCursor()
                cursor.insertText(replacement)
                count += 1

            if count == 0:
                self.status_label.setText(f"No occurrences of '{text}' found.")
            else:
                self.status_label.setText(
                    f"Replaced {count} occurrence(s) of '{text}'."
                )

            # Restore position
            cursor = self.editor.editor.textCursor()
            cursor.setPosition(cursor_position)
            self.editor.editor.setTextCursor(cursor)

            # If highlight all was active, refresh
            if self.highlight_all.isChecked():
                self.toggle_highlight_all(True)

        finally:
            # End undo sequence
            self.editor.editor.document().endEditBlock()

    def toggle_highlight_all(self, state):
        # Clear any existing highlights
        self.clear_all_highlights()

        if not state or not self.find_text.text():
            return

        # Get search parameters
        text = self.find_text.text()

        # Only use case sensitivity and whole words for highlighting
        flags = QTextDocument.FindFlag(0)
        if self.case_sensitive.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.whole_words.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords

        # Save current cursor
        cursor = self.editor.editor.textCursor()
        saved_position = cursor.position()

        # Start from beginning
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.editor.editor.setTextCursor(cursor)

        # Find and highlight all matches
        count = 0
        while self.editor.editor.find(text, flags):
            # Get current selection
            cursor = self.editor.editor.textCursor()

            # Store the format for later restoration
            extra_selection = QTextEdit.ExtraSelection()
            extra_selection.cursor = cursor
            extra_selection.format = self.highlight_format
            self.original_selection_formats.append(extra_selection)

            count += 1

        # Show extra selections
        self.editor.editor.setExtraSelections(self.original_selection_formats)

        # Restore cursor position
        cursor.setPosition(saved_position)
        self.editor.editor.setTextCursor(cursor)

        if count > 0:
            self.status_label.setText(f"Highlighted {count} matches")

    def clear_all_highlights(self):
        self.original_selection_formats = []
        self.editor.editor.setExtraSelections([])

    def cleanup_on_close(self):
        self.clear_all_highlights()

    def closeEvent(self, event):
        self.cleanup_on_close()
        super().closeEvent(event)


class TextEditor(QMainWindow):
    # Define custom signals
    transcription_requested = pyqtSignal()
    gpt4_processing_requested = pyqtSignal()
    # Modified to accept text to format
    smart_format_requested = pyqtSignal(str)
    save_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.editor = QTextEdit()
        self.setCentralWidget(self.editor)
        self._toolbar_actions = {}
        self.find_replace_dialog = None

        # Initialize spinner manager
        self.spinner_manager = SpinnerManager(self)

        # Setup the toolbar and connect formatting updates
        self.create_toolbar()
        self.setup_keyboard_shortcuts()

        # Connect signals for formatting updates
        self.editor.cursorPositionChanged.connect(self.update_formatting)
        self.editor.selectionChanged.connect(self.update_formatting)

        # Connect text change signal for more responsive word count
        self.editor.textChanged.connect(self.on_text_changed)
        self._word_count_dirty = True
        self._update_count_pending = False

        # Set default font
        default_font = QFont("Arial", 12)
        self.editor.setFont(default_font)

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.hide()  # Initially hidden, will show when needed

        # Enable drag and drop
        self.editor.setAcceptDrops(True)
        self.setAcceptDrops(True)  # Also allow drops on the main window

        # Set document title for accessibility
        self.editor.document().setMetaInformation(
            QTextDocument.MetaInformation.DocumentTitle, "Transcript Editor"
        )

        # Enable undo/redo history
        self.editor.setUndoRedoEnabled(True)

        # Initialize formatting
        self.update_formatting()

        # Word count timer (less frequent updates as a backup)
        self.word_count_timer = QTimer(self)
        self.word_count_timer.timeout.connect(self.delayed_word_count_update)
        self.word_count_timer.start(2000)  # Update every 2 seconds

    def setup_keyboard_shortcuts(self):
        # Create shortcuts for common operations
        shortcuts = {
            QKeySequence.StandardKey.Save: lambda: self.save_requested.emit(),
            QKeySequence.StandardKey.Bold: self.bold_text,
            QKeySequence.StandardKey.Italic: self.italic_text,
            QKeySequence.StandardKey.Underline: self.underline_text,
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_L): lambda: self.set_alignment(
                Qt.AlignmentFlag.AlignLeft
            ),
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_E): lambda: self.set_alignment(
                Qt.AlignmentFlag.AlignCenter
            ),
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_R): lambda: self.set_alignment(
                Qt.AlignmentFlag.AlignRight
            ),
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_J): lambda: self.set_alignment(
                Qt.AlignmentFlag.AlignJustify
            ),
            QKeySequence(
                Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_B
            ): self.bullet_list,
            QKeySequence(
                Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_N
            ): self.numbered_list,
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Greater): self.increase_indent,
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Less): self.decrease_indent,
            # Find and replace
            QKeySequence.StandardKey.Find: self.show_find_dialog,
            QKeySequence.StandardKey.Replace: self.show_find_dialog,
            # Print shortcuts
            QKeySequence.StandardKey.Print: self.print_document,
            QKeySequence(
                Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_P
            ): self.print_preview,
            # Custom shortcuts for Transcribrr-specific actions
            # Ctrl+T for transcription
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_T): self.start_transcription,
            # Ctrl+G for GPT processing
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_G): self.process_with_gpt4,
            QKeySequence(
                Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_F
            ): self.smart_format_text,
            # Ctrl+Shift+F for smart format
        }

        # Register all shortcuts
        for key_sequence, callback in shortcuts.items():
            shortcut = QShortcut(key_sequence, self)
            shortcut.activated.connect(callback)

    def create_toolbar(self):
        self.toolbar = QToolBar("Edit")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(16, 16))
        self.addToolBar(self.toolbar)

        # Transcription actions - adding at the beginning
        self.toolbar.addSeparator()

        # Transcribe button
        self.add_toolbar_action(
            "start_transcription",
            resource_path("./icons/transcribe.svg"),
            self.start_transcription,
            "Start Transcription (Ctrl+T)",
            checkable=False,
        )

        # GPT-4 Processing button
        self.add_toolbar_action(
            "process_with_gpt4",
            resource_path("./icons/magic_wand.svg"),
            self.process_with_gpt4,
            "Process with GPT-4 (Ctrl+G)",
            checkable=False,
        )

        # Smart Format button
        self.add_toolbar_action(
            "smart_format",
            resource_path("./icons/smart_format.svg"),
            self.smart_format_text,
            "Smart Format (Ctrl+Shift+F)",
            checkable=False,
        )

        self.toolbar.addSeparator()

        # Font family selector
        self.font_family_combobox = QFontComboBox()
        self.font_family_combobox.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        self.font_family_combobox.currentFontChanged.connect(
            self.font_family_changed)
        self.toolbar.addWidget(self.font_family_combobox)

        # Font size selector
        self.font_size_combobox = QComboBox()
        self.font_size_combobox.addItems(
            [
                "8",
                "9",
                "10",
                "11",
                "12",
                "14",
                "16",
                "18",
                "20",
                "22",
                "24",
                "26",
                "28",
                "36",
                "48",
                "72",
            ]
        )
        self.font_size_combobox.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum
        )
        self.font_size_combobox.setEditable(True)
        self.font_size_combobox.setCurrentText("12")  # Default font size
        self.font_size_combobox.currentTextChanged.connect(
            self.font_size_changed)
        self.toolbar.addWidget(self.font_size_combobox)

        # Text formatting actions
        self.add_formatting_actions()

        # Alignment actions
        self.add_alignment_actions()

        # List formatting actions
        self.add_list_actions()

        # Advanced toolbar items
        self.toolbar.addSeparator()

        # Find & Replace
        self.add_toolbar_action(
            "find_replace",
            resource_path("./icons/TextEditor/find.svg"),
            self.show_find_dialog,
            "Find & Replace (Ctrl+F)",
            checkable=False,
        )

        # Print
        self.add_toolbar_action(
            "print",
            resource_path("./icons/TextEditor/print.svg"),
            self.print_document,
            "Print (Ctrl+P)",
            checkable=False,
        )

        # Export menu
        self.add_export_menu()

        # Save button
        self.add_toolbar_action(
            "save",
            resource_path("./icons/save.svg"),
            lambda: self.save_requested.emit(),
            "Save (Ctrl+S)",
            checkable=False,
        )

        # Spacer to push toolbar items to the left
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Expanding)
        self.toolbar.addWidget(spacer)

        # Word count display in main toolbar
        self.word_count_label = QLabel("Words: 0")
        self.word_count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.word_count_label.setMinimumWidth(80)
        self.toolbar.addWidget(self.word_count_label)

    def add_formatting_actions(self):
        # Bold
        bold_action = self.add_toolbar_action(
            "bold",
            resource_path("./icons/TextEditor/bold.svg"),
            self.bold_text,
            "Bold (Ctrl+B)",
            checkable=True,
        )
        bold_action.setShortcut(QKeySequence.StandardKey.Bold)

        # Italic
        italic_action = self.add_toolbar_action(
            "italic",
            resource_path("./icons/TextEditor/italic.svg"),
            self.italic_text,
            "Italic (Ctrl+I)",
            checkable=True,
        )
        italic_action.setShortcut(QKeySequence.StandardKey.Italic)

        # Underline
        underline_action = self.add_toolbar_action(
            "underline",
            resource_path("./icons/TextEditor/underline.svg"),
            self.underline_text,
            "Underline (Ctrl+U)",
            checkable=True,
        )
        underline_action.setShortcut(QKeySequence.StandardKey.Underline)

        # Strikethrough
        self.add_toolbar_action(
            "strikethrough",
            resource_path("./icons/TextEditor/strikethrough.svg"),
            self.strikethrough_text,
            "Strikethrough",
            checkable=True,
        )

        # Highlight
        self.add_toolbar_action(
            "highlight",
            resource_path("./icons/TextEditor/highlight.svg"),
            self.highlight_text,
            "Highlight Text",
        )

        # Font color
        self.add_toolbar_action(
            "font_color",
            resource_path("./icons/TextEditor/font_color.svg"),
            self.font_color,
            "Font Color",
        )

    def add_alignment_actions(self):
        alignment_group = QActionGroup(self)

        align_left_action = self.add_toolbar_action(
            "align_left",
            resource_path("./icons/TextEditor/align_left.svg"),
            lambda: self.set_alignment(Qt.AlignmentFlag.AlignLeft),
            "Align Left (Ctrl+L)",
            checkable=True,
        )

        align_center_action = self.add_toolbar_action(
            "align_center",
            resource_path("./icons/TextEditor/align_center.svg"),
            lambda: self.set_alignment(Qt.AlignmentFlag.AlignCenter),
            "Align Center (Ctrl+E)",
            checkable=True,
        )

        align_right_action = self.add_toolbar_action(
            "align_right",
            resource_path("./icons/TextEditor/align_right.svg"),
            lambda: self.set_alignment(Qt.AlignmentFlag.AlignRight),
            "Align Right (Ctrl+R)",
            checkable=True,
        )

        justify_action = self.add_toolbar_action(
            "justify",
            resource_path("./icons/TextEditor/justify.svg"),
            lambda: self.set_alignment(Qt.AlignmentFlag.AlignJustify),
            "Justify Text (Ctrl+J)",
            checkable=True,
        )

        for action in [
            align_left_action,
            align_center_action,
            align_right_action,
            justify_action,
        ]:
            alignment_group.addAction(action)

    def add_list_actions(self):
        self.add_toolbar_action(
            "bullet_list",
            resource_path("./icons/TextEditor/bullet.svg"),
            self.bullet_list,
            "Bullet List (Ctrl+Shift+B)",
        )
        self.add_toolbar_action(
            "numbered_list",
            resource_path("./icons/TextEditor/numbered.svg"),
            self.numbered_list,
            "Numbered List (Ctrl+Shift+N)",
        )
        self.add_toolbar_action(
            "increase_indent",
            resource_path("./icons/TextEditor/increase_indent.svg"),
            self.increase_indent,
            "Increase Indent (Ctrl+>)",
        )
        self.add_toolbar_action(
            "decrease_indent",
            resource_path("./icons/TextEditor/decrease_indent.svg"),
            self.decrease_indent,
            "Decrease Indent (Ctrl+<)",
        )

    def add_export_menu(self):
        self.export_menu = QMenu()
        export_pdf_action = QAction("Export to PDF", self)
        export_pdf_action.triggered.connect(self.export_to_pdf)
        self.export_menu.addAction(export_pdf_action)

        export_word_action = QAction("Export to Word", self)
        export_word_action.triggered.connect(self.export_to_word)
        self.export_menu.addAction(export_word_action)

        export_text_action = QAction("Export to Plain Text", self)
        export_text_action.triggered.connect(self.export_to_text)
        self.export_menu.addAction(export_text_action)

        export_html_action = QAction("Export to HTML", self)
        export_html_action.triggered.connect(self.export_to_html)
        self.export_menu.addAction(export_html_action)

        export_button = QToolButton()
        export_button.setText("Export")
        export_button.setIcon(load_icon("./icons/export.svg", size=24))
        export_button.setToolTip("Export to different formats")
        export_button.setMenu(self.export_menu)
        export_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        self.toolbar.addWidget(export_button)

    def add_action_with_spinner(
        self, action_name, icon_path, callback, tooltip, spinner_icon, spinner_name
    ):
        """Legacy method - no longer used with new button design.
        Kept for compatibility with existing code."""
        # Create a QPushButton with icon and text
        button = QPushButton()
        button.setIcon(load_icon(resource_path(icon_path), size=20))
        button.setIconSize(QSize(18, 18))
        button.setToolTip(tooltip)
        button.clicked.connect(callback)

        # Add as widget action
        action = QWidgetAction(self.toolbar)
        action.setDefaultWidget(button)

        # Store reference
        self._toolbar_actions[action_name] = action
        return action

    def toggle_spinner(self, spinner_name):
        """Toggle action state to indicate processing."""
        button_map = {
            "transcription": "start_transcription",
            "gpt": "process_with_gpt4",
            "smart_format": "smart_format",
        }

        button_name = button_map.get(spinner_name)
        if not button_name or button_name not in self._toolbar_actions:
            return False

        action = self._toolbar_actions[button_name]

        # Check current state
        is_active = getattr(action, "_is_processing", False)

        if not is_active:
            # Start processing state
            original_tooltip = action.toolTip()
            setattr(action, "_original_tooltip", original_tooltip)

            if spinner_name == "transcription":
                action.setToolTip("Transcribing...")
            elif spinner_name == "gpt":
                action.setToolTip("Processing...")
            elif spinner_name == "smart_format":
                action.setToolTip("Formatting...")

            action.setEnabled(False)
            setattr(action, "_is_processing", True)
            self.show_status_message("Processing...")
            return True
        else:
            # End processing state
            original_tooltip = getattr(action, "_original_tooltip", None)
            if original_tooltip:
                action.setToolTip(original_tooltip)

            action.setEnabled(True)
            setattr(action, "_is_processing", False)
            self.hide_status_message()
            return False

    def toggle_gpt_spinner(self):
        """Toggle the GPT processing state."""
        self.toggle_spinner("gpt")

    def toggle_transcription_spinner(self):
        """Toggle the transcription processing state."""
        self.toggle_spinner("transcription")

    def add_toolbar_action(
        self, action_name, icon_path, callback, tooltip, checkable=False
    ):
        # Check if icon file exists
        if icon_path and os.path.exists(icon_path):
            action = QAction(load_icon(icon_path, size=20), tooltip, self)
        else:
            # Use text-only action if icon is missing
            action = QAction(tooltip, self)
            if icon_path:
                logger.warning(f"Icon not found: {icon_path}")

        action.setCheckable(checkable)
        if callable(callback):
            action.triggered.connect(callback)
        self.toolbar.addAction(action)
        self._toolbar_actions[action_name] = action
        return action

    def font_family_changed(self, font):
        self.editor.setCurrentFont(font)
        self.show_status_message(f"Font changed to {font.family()}")

    def font_size_changed(self, size):
        try:
            size_float = float(size)
            self.editor.setFontPointSize(size_float)
            self.show_status_message(f"Font size set to {size}")
        except ValueError:
            show_error_message(
                self, "Invalid Font Size", "Please enter a valid number for font size."
            )

    def bold_text(self):
        weight = (
            QFont.Weight.Bold
            if not self.editor.fontWeight() == QFont.Weight.Bold
            else QFont.Weight.Normal
        )
        self.editor.setFontWeight(weight)
        status = "enabled" if weight == QFont.Weight.Bold else "disabled"
        self.show_status_message(f"Bold {status}")

    def italic_text(self):
        state = not self.editor.fontItalic()
        self.editor.setFontItalic(state)
        status = "enabled" if state else "disabled"
        self.show_status_message(f"Italic {status}")

    def underline_text(self):
        state = not self.editor.fontUnderline()
        self.editor.setFontUnderline(state)
        status = "enabled" if state else "disabled"
        self.show_status_message(f"Underline {status}")

    def strikethrough_text(self):
        fmt = self.editor.currentCharFormat()
        fmt.setFontStrikeOut(not fmt.fontStrikeOut())
        self.editor.mergeCurrentCharFormat(fmt)
        status = "enabled" if fmt.fontStrikeOut() else "disabled"
        self.show_status_message(f"Strikethrough {status}")

    def highlight_text(self):
        color = QColorDialog.getColor()
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self.editor.mergeCurrentCharFormat(fmt)
            self.show_status_message(
                f"Text highlighted with color: {color.name()}")

    def font_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.editor.setTextColor(color)
            self.show_status_message(f"Text color set to: {color.name()}")

    def set_alignment(self, alignment):
        self.editor.setAlignment(alignment)
        alignment_map = {
            Qt.AlignmentFlag.AlignLeft: "left",
            Qt.AlignmentFlag.AlignCenter: "center",
            Qt.AlignmentFlag.AlignRight: "right",
            Qt.AlignmentFlag.AlignJustify: "justified",
        }
        alignment_name = alignment_map.get(alignment, "unknown")
        self.show_status_message(f"Text aligned: {alignment_name}")

    def bullet_list(self):
        cursor = self.editor.textCursor()
        list_format = QTextListFormat()
        list_format.setStyle(QTextListFormat.Style.ListDisc)
        cursor.createList(list_format)
        self.show_status_message("Bullet list created")

    def numbered_list(self):
        cursor = self.editor.textCursor()
        list_format = QTextListFormat()
        list_format.setStyle(QTextListFormat.Style.ListDecimal)
        cursor.createList(list_format)
        self.show_status_message("Numbered list created")

    def increase_indent(self):
        cursor = self.editor.textCursor()
        if cursor.blockFormat().indent() < 15:
            block_format = cursor.blockFormat()
            block_format.setIndent(block_format.indent() + 1)
            cursor.setBlockFormat(block_format)
            self.show_status_message("Indent increased")

    def decrease_indent(self):
        cursor = self.editor.textCursor()
        if cursor.blockFormat().indent() > 0:
            block_format = cursor.blockFormat()
            block_format.setIndent(block_format.indent() - 1)
            cursor.setBlockFormat(block_format)
            self.show_status_message("Indent decreased")

    def show_find_dialog(self):
        """Show find and replace dialog."""
        if not self.find_replace_dialog:
            self.find_replace_dialog = FindReplaceDialog(self)
        self.find_replace_dialog.show()
        self.find_replace_dialog.raise_()
        self.find_replace_dialog.activateWindow()

    def print_document(self):
        """Show print dialog and print document."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)

        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            self.editor.document().print(printer)
            self.show_status_message("Document sent to printer")

    def print_preview(self):
        """Show print preview dialog."""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        preview = QPrintPreviewDialog(printer, self)
        preview.paintRequested.connect(
            lambda p: self.editor.document().print(p))
        preview.exec()

    def export_to_pdf(self):
        """Export document to PDF with formatting preserved - using multiple fallback approaches."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export to PDF", "", "PDF Files (*.pdf)"
        )
        if file_path:
            if not file_path.endswith(".pdf"):
                file_path += ".pdf"

            # Try multiple PDF generation approaches in sequence

            # Approach 1: Direct printing (simplest but may not preserve formatting well)
            try:
                # Simple approach - just print the document directly
                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(file_path)

                # Print directly
                success = self.editor.document().print(printer)

                if success:
                    self.show_status_message(
                        f"Document exported to {os.path.basename(file_path)}"
                    )
                    show_info_message(
                        self,
                        "Export to PDF",
                        f"Document successfully exported to {file_path}",
                    )
                    return

            except Exception as e1:
                logger.debug(f"Basic PDF export failed: {e1}")
                # Continue to next approach

            # Approach 2: Export to HTML then create PDF from that
            try:
                # Export HTML to a temporary file
                import tempfile

                html_file = tempfile.NamedTemporaryFile(
                    suffix=".html", delete=False)
                html_path = html_file.name
                html_file.close()

                # Get formatted HTML with proper styles
                html = self.editor.toHtml()

                # Add proper styling to ensure good PDF output
                styled_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            font-size: 12pt;
            line-height: 1.5;
            margin: 1.5cm;
        }}
        * {{ 
            font-size: 12pt;
        }}
    </style>
</head>
<body>
{self._extract_body_content(html)}
</body>
</html>"""

                # Write the styled HTML to the temp file
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(styled_html)

                # Check for external PDF conversion tools - use the first available one

                # Try using wkhtmltopdf if available (common HTML to PDF converter)
                import subprocess
                import shutil

                try:
                    # Check if wkhtmltopdf is installed
                    if shutil.which("wkhtmltopdf"):
                        # Use wkhtmltopdf to convert HTML to PDF
                        subprocess.check_call(
                            [
                                "wkhtmltopdf",
                                "--quiet",
                                "--page-size",
                                "A4",
                                "--margin-top",
                                "20",
                                "--margin-right",
                                "20",
                                "--margin-bottom",
                                "20",
                                "--margin-left",
                                "20",
                                "--encoding",
                                "UTF-8",
                                html_path,
                                file_path,
                            ]
                        )

                        # Clean up temp file
                        try:
                            os.unlink(html_path)
                        except:
                            pass

                        self.show_status_message(
                            f"Document exported to {os.path.basename(file_path)}"
                        )
                        show_info_message(
                            self,
                            "Export to PDF",
                            f"Document successfully exported to {file_path}",
                        )
                        return
                except Exception as e2:
                    logger.debug(f"wkhtmltopdf export failed: {e2}")

                # Try using weasyprint if available
                try:
                    import importlib.util

                    if importlib.util.find_spec("weasyprint"):
                        import weasyprint

                        weasyprint.HTML(
                            string=styled_html).write_pdf(file_path)

                        # Clean up temp file
                        try:
                            os.unlink(html_path)
                        except:
                            pass

                        self.show_status_message(
                            f"Document exported to {os.path.basename(file_path)}"
                        )
                        show_info_message(
                            self,
                            "Export to PDF",
                            f"Document successfully exported to {file_path}",
                        )
                        return
                except Exception as e3:
                    logger.debug(f"weasyprint export failed: {e3}")

                # Fallback - create a simple PDF using QPrinter but print from our styled HTML file
                try:
                    # Set up a printer
                    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                    printer.setOutputFileName(file_path)

                    # Use simpler approach without many settings
                    self.editor.document().print(printer)

                    # Clean up temp file
                    try:
                        os.unlink(html_path)
                    except:
                        pass

                    self.show_status_message(
                        f"Document exported to {os.path.basename(file_path)}"
                    )
                    show_info_message(
                        self,
                        "Export to PDF",
                        f"Document exported with basic formatting to {file_path}",
                    )
                    return
                except Exception as e4:
                    logger.debug(f"Fallback PDF export failed: {e4}")

                    # If we got here, all our PDF export attempts failed
                    # Let's just save the HTML file and tell the user
                    html_output_path = file_path.replace(".pdf", ".html")
                    try:
                        # Move our temp HTML file to final destination
                        shutil.copy(html_path, html_output_path)
                        os.unlink(html_path)

                        show_error_message(
                            self,
                            "PDF Export Failed",
                            f"Could not create PDF file. HTML file saved to {html_output_path} instead.",
                        )
                        return
                    except:
                        # Last resort - just leave the temp HTML file
                        show_error_message(
                            self,
                            "PDF Export Failed",
                            f"Could not create PDF file. HTML file saved to {html_path} instead.",
                        )
                        return

            except Exception as e:
                # If all approaches failed
                show_error_message(
                    self, "Export Error", f"Failed to export to PDF: {e}"
                )
                logger.error(
                    f"PDF export error (all methods failed): {e}", exc_info=True
                )

    def export_to_word(self):
        """Export document to Word with improved formatting preservation."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export to Word", "", "Word Documents (*.docx)"
        )
        if file_path:
            try:
                if not file_path.endswith(".docx"):
                    file_path += ".docx"

                # Lazy import document export dependencies
                try:
                    import docx  # type: ignore
                    from htmldocx import HtmlToDocx  # type: ignore
                except ImportError as e:
                    show_error_message(
                        self,
                        "Export to Word Unavailable",
                        "Export to Word requires additional packages.\n\n"
                        "Please install: python-docx and htmldocx\n"
                        "Run: pip install python-docx htmldocx",
                    )
                    logger.warning(f"Word export dependencies not available: {e}")
                    return

                doc = docx.Document()

                # Clean up HTML for better conversion
                html = self.editor.toHtml()

                # Make sure we have complete HTML with proper structure
                if not html.startswith("<!DOCTYPE html>"):
                    # Add wrapper to ensure proper parsing
                    html = f"""<!DOCTYPE html>
                    <html>
                    <head>
                    <meta charset="UTF-8">
                    <style>
                    body {{ font-family: Arial, sans-serif; }}
                    p {{ margin-bottom: 10px; }}
                    h1, h2, h3, h4, h5, h6 {{ margin-top: 20px; margin-bottom: 10px; }}
                    </style>
                    </head>
                    <body>
                    {html}
                    </body>
                    </html>"""

                # Set up the converter with better styling support
                new_parser = HtmlToDocx()

                # Try to optimize conversion settings
                try:
                    # Set the parser to use styling (if this method exists)
                    if hasattr(new_parser, "set_initial_style"):
                        new_parser.set_initial_style(doc)
                except Exception as style_err:
                    logger.debug(f"Style setup for Word export: {style_err}")

                # Add the HTML to the document
                new_parser.add_html_to_document(html, doc)

                # Save the document
                doc.save(file_path)

                self.show_status_message(
                    f"Document exported to {os.path.basename(file_path)}"
                )
                show_info_message(
                    self,
                    "Export to Word",
                    f"Document successfully exported to {file_path}",
                )
            except Exception as e:
                show_error_message(
                    self, "Export Error", f"Failed to export to Word: {e}"
                )
                logger.error(f"Word export error: {e}", exc_info=True)

    def export_to_text(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export to Plain Text", "", "Text Files (*.txt)"
        )
        if file_path:
            try:
                if not file_path.endswith(".txt"):
                    file_path += ".txt"

                plain_text = self.editor.toPlainText()
                with open(file_path, "w", encoding="utf-8") as file:
                    file.write(plain_text)

                self.show_status_message(
                    f"Document exported to {os.path.basename(file_path)}"
                )
                show_info_message(
                    self,
                    "Export to Text",
                    f"Document successfully exported to {file_path}",
                )
            except Exception as e:
                show_error_message(
                    self, "Export Error", f"Failed to export to text: {e}"
                )
                logger.error(f"Text export error: {e}")

    def export_to_html(self):
        """Export document to HTML file with better formatting and styling."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export to HTML", "", "HTML Files (*.html)"
        )
        if file_path:
            try:
                if not file_path.endswith(".html"):
                    file_path += ".html"

                # Get the HTML content
                html = self.editor.toHtml()

                # Fix up the HTML for better standalone viewing - improve CSS and structure
                if not html.startswith("<!DOCTYPE html>"):
                    # This is a fragment - wrap it in a proper document with styling
                    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Exported Document from Transcribrr</title>
    <style>
        body {{
            font-family: Arial, Helvetica, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }}
        p {{
            margin-bottom: 1em;
        }}
        h1, h2, h3, h4, h5, h6 {{
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            font-weight: bold;
            color: #222;
        }}
        h1 {{ font-size: 2em; }}
        h2 {{ font-size: 1.75em; }}
        h3 {{ font-size: 1.5em; }}
        h4 {{ font-size: 1.25em; }}
        h5 {{ font-size: 1.1em; }}
        h6 {{ font-size: 1em; }}
        pre {{
            background-color: #f5f5f5;
            padding: 0.5em;
            border-radius: 4px;
            overflow-x: auto;
        }}
        ul, ol {{
            padding-left: 2em;
            margin-bottom: 1em;
        }}
        li {{
            margin-bottom: 0.5em;
        }}
        a {{
            color: #0066cc;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
        blockquote {{
            border-left: 3px solid #ccc;
            padding-left: 1em;
            margin-left: 0;
            color: #666;
        }}
        img {{
            max-width: 100%;
            height: auto;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin-bottom: 1em;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }}
        th {{
            background-color: #f2f2f2;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}
    </style>
</head>
<body>
    {html}
</body>
</html>"""
                else:
                    # Extract the HTML content between body tags and add our improved styling
                    import re

                    head_match = re.search(
                        r"<head>(.*?)</head>", html, re.DOTALL)
                    body_match = re.search(
                        r"<body.*?>(.*?)</body>", html, re.DOTALL)

                    if head_match and body_match:
                        head_content = head_match.group(1)
                        body_content = body_match.group(1)

                        # Create a new document with better styling
                        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Exported Document from Transcribrr</title>
    {head_content}
    <style>
        body {{
            font-family: Arial, Helvetica, sans-serif;
            line-height: 1.6;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            color: #333;
        }}
        p {{
            margin-bottom: 1em;
        }}
        h1, h2, h3, h4, h5, h6 {{
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            color: #222;
        }}
        pre {{
            background-color: #f5f5f5;
            padding: 0.5em;
            border-radius: 4px;
            overflow-x: auto;
        }}
        ul, ol {{
            padding-left: 2em;
            margin-bottom: 1em;
        }}
    </style>
</head>
<body>
    {body_content}
</body>
</html>"""

                # Write the improved HTML to file
                with open(file_path, "w", encoding="utf-8") as file:
                    file.write(html)

                self.show_status_message(
                    f"Document exported to {os.path.basename(file_path)}"
                )
                show_info_message(
                    self,
                    "Export to HTML",
                    f"Document successfully exported to {file_path}",
                )
            except Exception as e:
                show_error_message(
                    self, "Export Error", f"Failed to export to HTML: {e}"
                )
                logger.error(f"HTML export error: {e}", exc_info=True)

    def show_status_message(self, message, timeout=3000):
        """Show a temporary status message."""
        self.statusBar().showMessage(message, timeout)
        if not self.statusBar().isVisible():
            self.statusBar().show()

    def hide_status_message(self):
        """Hide the status bar if it's showing a message."""
        self.statusBar().clearMessage()
        self.statusBar().hide()

    def on_text_changed(self):
        """Called when the text content changes."""
        self._word_count_dirty = True

        # Use a single-shot timer to avoid updating on every keystroke
        if not self._update_count_pending:
            self._update_count_pending = True
            QTimer.singleShot(300, self.update_word_count)

    def delayed_word_count_update(self):
        """Update word count if it's marked as dirty (backup for any missed updates)."""
        if self._word_count_dirty:
            self.update_word_count()

    def update_word_count(self):
        """Update the word count display with accurate word count."""
        self._update_count_pending = False
        self._word_count_dirty = False

        text = self.editor.toPlainText()
        # Improved word count calculation - splits on whitespace and removes empty strings
        words = [word for word in text.split() if word.strip()]
        word_count = len(words)
        char_count = len(text)
        self.word_count_label.setText(
            f"Words: {word_count} | Chars: {char_count}")

    def _extract_body_content(self, html):
        """Extract the body content from HTML, or return the entire HTML if no body tags are found."""
        import re

        # Try to find body content
        body_match = re.search(
            r"<body.*?>(.*?)</body>", html, re.DOTALL | re.IGNORECASE
        )

        if body_match:
            # Return just the content inside the body tags
            return body_match.group(1)

        # If we have a full HTML document but couldn't extract body for some reason
        if html.lower().startswith("<!doctype html>") or html.lower().startswith(
            "<html"
        ):
            # Just return everything after the head section
            head_end = html.lower().find("</head>")
            if head_end > 0:
                html_start = html.lower().find("<html", head_end)
                if html_start > 0:
                    return html[html_start:]

        # Return the original content as a fallback
        return html

    def serialize_text_document(self):
        """Serialize the text document to HTML."""
        try:
            formatted_text = self.editor.toHtml()
            return formatted_text
        except Exception as e:
            logger.error(f"Error serializing text document: {e}")
            return None

    def deserialize_text_document(self, text_data):
        """Deserialize and load text into the editor."""
        if text_data:
            try:
                # If it's bytes, decode to string
                if isinstance(text_data, bytes):
                    text_data = text_data.decode("utf-8")

                # More robust HTML detection - checks for proper HTML structure
                is_html = False

                # Check if it has HTML content tag
                if text_data.startswith("<!DOCTYPE html>") or text_data.startswith(
                    "<html"
                ):
                    is_html = True
                # Check if it has HTML body elements
                elif "<body" in text_data and "</body>" in text_data:
                    is_html = True
                # Check if it has style elements or other common HTML tags
                elif (
                    ("<p>" in text_data and "</p>" in text_data)
                    or ("<div>" in text_data and "</div>" in text_data)
                    or ("<pre>" in text_data and "</pre>" in text_data)
                    or ("<h1>" in text_data and "</h1>" in text_data)
                    or ("<style>" in text_data and "</style>" in text_data)
                ):
                    is_html = True

                if is_html:
                    self.editor.setHtml(text_data)
                else:
                    self.editor.setPlainText(text_data)
            except Exception as e:
                logger.error(f"Error deserializing text document: {e}")
                self.editor.clear()
                self.editor.setPlainText("Error loading document.")
        else:
            self.editor.clear()

        # Update word count
        self.update_word_count()

    def setHtml(self, html):
        """Set HTML content to the editor."""
        self.editor.setHtml(html)
        self.update_word_count()

    def toHtml(self):
        """Get HTML content from the editor."""
        return self.editor.toHtml()

    def toPlainText(self):
        """Get plain text content from the editor."""
        return self.editor.toPlainText()

    def clear(self):
        """Clear the editor content."""
        self.editor.clear()
        self.update_word_count()

    def save_editor_state(self):
        """Emit signal to request saving the editor state."""
        self.save_requested.emit()

    def process_with_gpt4(self):
        """Emit signal to request GPT-4 processing."""
        self.gpt4_processing_requested.emit()

    def start_transcription(self):
        """Emit signal to request transcription."""
        self.transcription_requested.emit()

    def smart_format_text(self):
        """Emit signal to request smart formatting with the current text."""
        current_text = self.editor.toPlainText()
        if not current_text.strip():
            show_error_message(
                self, "Empty Text", "Please add some text before formatting."
            )
            return

        # Confirm with user if text is long
        if len(current_text) > 10000:  # Roughly 2000 words
            response = QMessageBox.question(
                self,
                "Format Long Text",
                "The text is quite long, which may take some time to process. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if response == QMessageBox.StandardButton.No:
                return

        # Set the smart format action to processing state
        self.toggle_spinner("smart_format")

        self.smart_format_requested.emit(current_text)
        self.show_status_message("Smart formatting requested...")

    def update_formatting(self):
        """Update the toolbar buttons to reflect current formatting."""
        fmt = self.editor.currentCharFormat()
        cursor = self.editor.textCursor()

        # Block signals to avoid recursion
        self.font_family_combobox.blockSignals(True)
        self.font_size_combobox.blockSignals(True)

        # Update font family
        current_font = fmt.font()
        self.font_family_combobox.setCurrentFont(current_font)

        # Update font size
        size = current_font.pointSize()
        if size > 0:
            self.font_size_combobox.setCurrentText(str(int(size)))
        else:
            self.font_size_combobox.setCurrentText("")

        self.font_family_combobox.blockSignals(False)
        self.font_size_combobox.blockSignals(False)

        # Update formatting actions
        if "bold" in self._toolbar_actions:
            self._toolbar_actions["bold"].setChecked(current_font.bold())
        if "italic" in self._toolbar_actions:
            self._toolbar_actions["italic"].setChecked(current_font.italic())
        if "underline" in self._toolbar_actions:
            self._toolbar_actions["underline"].setChecked(
                current_font.underline())
        if "strikethrough" in self._toolbar_actions:
            self._toolbar_actions["strikethrough"].setChecked(
                current_font.strikeOut())

        # Update alignment actions
        alignment = self.editor.alignment()
        if "align_left" in self._toolbar_actions:
            self._toolbar_actions["align_left"].setChecked(
                alignment == Qt.AlignmentFlag.AlignLeft
            )
        if "align_center" in self._toolbar_actions:
            self._toolbar_actions["align_center"].setChecked(
                alignment == Qt.AlignmentFlag.AlignCenter
            )
        if "align_right" in self._toolbar_actions:
            self._toolbar_actions["align_right"].setChecked(
                alignment == Qt.AlignmentFlag.AlignRight
            )
        if "justify" in self._toolbar_actions:
            self._toolbar_actions["justify"].setChecked(
                alignment == Qt.AlignmentFlag.AlignJustify
            )

    def __del__(self):
        """Clean up resources when the editor is destroyed."""
        try:
            # Cleanup timer if still active
            if hasattr(self, "word_count_timer") and self.word_count_timer.isActive():
                self.word_count_timer.stop()

            # Close any open dialog
            if hasattr(self, "find_replace_dialog") and self.find_replace_dialog:
                self.find_replace_dialog.close()
                self.find_replace_dialog = None
        except Exception as e:
            # Protect against errors during shutdown
            logger.error(f"Error in TextEditor cleanup: {e}")

    def dragEnterEvent(self, event):
        """Handle drag enter events for drag and drop functionality."""
        # Accept drag events if they contain text, URLs, or HTML
        mime_data = event.mimeData()
        if mime_data.hasText() or mime_data.hasUrls() or mime_data.hasHtml():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Handle drop events for drag and drop functionality."""
        mime_data = event.mimeData()

        # Handle URLs (like files)
        if mime_data.hasUrls():
            urls = mime_data.urls()
            if urls:
                # For now, just handle the first URL
                url = urls[0]
                if url.isLocalFile():
                    file_path = url.toLocalFile()
                    self.load_file(file_path)
                    event.acceptProposedAction()
                    return

        # Handle HTML content (preferred over plain text for rich formatting)
        if mime_data.hasHtml():
            html = mime_data.html()
            cursor = self.editor.cursorForPosition(event.position().toPoint())
            cursor.insertHtml(html)
            event.acceptProposedAction()
            return

        # Handle plain text
        if mime_data.hasText():
            text = mime_data.text()
            cursor = self.editor.cursorForPosition(event.position().toPoint())
            cursor.insertText(text)
            event.acceptProposedAction()
            return

        event.ignore()

    def load_file(self, file_path):
        """Load content from a file into the editor with improved error handling and encoding detection."""
        try:
            # Check file extension to determine how to load it
            _, extension = os.path.splitext(file_path)
            extension = extension.lower()

            supported_text_extensions = [
                ".txt",
                ".md",
                ".csv",
                ".json",
                ".xml",
                ".log",
                ".py",
                ".js",
                ".css",
            ]
            supported_html_extensions = [".html", ".htm", ".xhtml"]

            if extension in supported_text_extensions + supported_html_extensions:
                # Try different encodings if UTF-8 fails
                encodings_to_try = ["utf-8", "latin-1", "cp1252", "iso-8859-1"]
                text = None

                for encoding in encodings_to_try:
                    try:
                        with open(file_path, "r", encoding=encoding) as file:
                            text = file.read()
                        break  # Successfully read the file
                    except UnicodeDecodeError:
                        continue  # Try the next encoding

                if text is None:
                    raise ValueError(
                        f"Unable to decode file with any of the attempted encodings: {', '.join(encodings_to_try)}"
                    )

                if extension in supported_html_extensions:
                    self.editor.setHtml(text)
                else:
                    self.editor.setPlainText(text)

                # Update word count
                self.update_word_count()
                self.show_status_message(
                    f"Loaded file: {os.path.basename(file_path)}")
            else:
                show_error_message(
                    self,
                    "Unsupported File",
                    f"The file type {extension} is not supported for direct editing.",
                )

        except FileNotFoundError:
            show_error_message(
                self, "File Not Found", f"The file {file_path} could not be found."
            )
            logger.error(f"File not found: {file_path}")
        except PermissionError:
            show_error_message(
                self,
                "Permission Error",
                f"You do not have permission to access {file_path}.",
            )
            logger.error(f"Permission error accessing file {file_path}")
        except ValueError as e:
            show_error_message(self, "Encoding Error", str(e))
            logger.error(f"Encoding error with file {file_path}: {e}")
        except Exception as e:
            show_error_message(self, "Error Loading File",
                               f"Failed to load file: {e}")
            logger.error(f"Error loading file {file_path}: {e}", exc_info=True)


# For standalone testing
def main():
    app = QApplication(sys.argv)
    editor = TextEditor()
    editor.resize(800, 600)
    editor.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
