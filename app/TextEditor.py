import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QToolBar, QColorDialog, QWidget,
    QWidgetAction, QFontComboBox, QComboBox, QSizePolicy, QLabel, QToolButton, QMenu, QFileDialog,
    QMessageBox, QPlainTextEdit, QPushButton, QStatusBar, QDialog, QVBoxLayout,
    QHBoxLayout, QCheckBox, QTabWidget, QScrollArea
)
from PyQt6.QtGui import (
    QIcon, QFont, QColor, QTextListFormat, QActionGroup, QTextCursor, QAction, QMovie,
    QTextCharFormat, QKeySequence, QPixmap, QTextDocument, QTextDocumentWriter,
    QShortcut  # Import QShortcut from QtGui, not QtWidgets
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QUrl, QTimer, QMimeData
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
import docx
from htmldocx import HtmlToDocx
from PyPDF2 import PdfFileWriter
import logging
from app.utils import resource_path
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class FindReplaceDialog(QDialog):
    """Dialog for finding and replacing text."""

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Find and Replace")
        self.setModal(False)
        self.setFixedWidth(400)

        layout = QVBoxLayout(self)

        # Find section
        find_layout = QHBoxLayout()
        find_label = QLabel("Find:")
        self.find_text = QLineEdit()
        self.find_text.setPlaceholderText("Enter text to find")
        find_layout.addWidget(find_label)
        find_layout.addWidget(self.find_text)
        layout.addLayout(find_layout)

        # Replace section
        replace_layout = QHBoxLayout()
        replace_label = QLabel("Replace:")
        self.replace_text = QLineEdit()
        self.replace_text.setPlaceholderText("Enter replacement text")
        replace_layout.addWidget(replace_label)
        replace_layout.addWidget(self.replace_text)
        layout.addLayout(replace_layout)

        # Options
        options_layout = QHBoxLayout()
        self.case_sensitive = QCheckBox("Case sensitive")
        self.whole_words = QCheckBox("Whole words only")
        options_layout.addWidget(self.case_sensitive)
        options_layout.addWidget(self.whole_words)
        layout.addLayout(options_layout)

        # Buttons
        button_layout = QHBoxLayout()
        self.find_button = QPushButton("Find Next")
        self.replace_button = QPushButton("Replace")
        self.replace_all_button = QPushButton("Replace All")
        self.close_button = QPushButton("Close")

        button_layout.addWidget(self.find_button)
        button_layout.addWidget(self.replace_button)
        button_layout.addWidget(self.replace_all_button)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)

        # Connect signals
        self.find_button.clicked.connect(self.find_next)
        self.replace_button.clicked.connect(self.replace)
        self.replace_all_button.clicked.connect(self.replace_all)
        self.close_button.clicked.connect(self.close)
        self.find_text.textChanged.connect(self.update_buttons)

        # Initial button state
        self.update_buttons()

    def update_buttons(self):
        """Enable/disable buttons based on input."""
        has_find_text = bool(self.find_text.text())
        self.find_button.setEnabled(has_find_text)
        self.replace_button.setEnabled(has_find_text)
        self.replace_all_button.setEnabled(has_find_text)

    def find_next(self):
        """Find the next occurrence of the search text."""
        text = self.find_text.text()
        if not text:
            return

        # Set search flags
        flags = QTextDocument.FindFlag(0)
        if self.case_sensitive.isChecked():
            flags |= QTextDocument.FindFlag.FindCaseSensitively
        if self.whole_words.isChecked():
            flags |= QTextDocument.FindFlag.FindWholeWords

        # Find text
        cursor = self.editor.editor.textCursor()
        # Start from current position
        found = self.editor.editor.find(text, flags)

        if not found:
            # If not found from current position, try from beginning
            cursor = self.editor.editor.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            self.editor.editor.setTextCursor(cursor)
            found = self.editor.editor.find(text, flags)

            if not found:
                QMessageBox.information(self, "Search Result", f"No occurrences of '{text}' found.")

        return found

    def replace(self):
        """Replace the current selection with the replacement text."""
        cursor = self.editor.editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(self.replace_text.text())

        # Find the next occurrence
        self.find_next()

    def replace_all(self):
        """Replace all occurrences of the search text."""
        text = self.find_text.text()
        replacement = self.replace_text.text()

        if not text:
            return

        # Save cursor position
        cursor = self.editor.editor.textCursor()
        cursor_position = cursor.position()

        # Move to beginning
        cursor.movePosition(QTextCursor.MoveOperation.Start)
        self.editor.editor.setTextCursor(cursor)

        # Set search flags
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
            QMessageBox.information(self, "Replace Result", f"No occurrences of '{text}' found.")
        else:
            QMessageBox.information(self, "Replace Result", f"Replaced {count} occurrence(s) of '{text}'.")

        # Restore position
        cursor = self.editor.editor.textCursor()
        cursor.setPosition(cursor_position)
        self.editor.editor.setTextCursor(cursor)


class TextEditor(QMainWindow):
    # Define custom signals
    transcription_requested = pyqtSignal()
    gpt4_processing_requested = pyqtSignal()
    smart_format_requested = pyqtSignal(str)  # Modified to accept text to format
    save_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.editor = QTextEdit()
        self.setCentralWidget(self.editor)
        self._toolbar_actions = {}
        self.is_markdown_mode = False  # Track current mode (unused but kept for completeness)
        self.find_replace_dialog = None

        # Setup the toolbar and connect formatting updates
        self.create_toolbar()
        self.setup_keyboard_shortcuts()

        # Connect signals for formatting updates
        self.editor.cursorPositionChanged.connect(self.update_formatting)
        self.editor.selectionChanged.connect(self.update_formatting)

        # Set default font
        default_font = QFont("Arial", 12)
        self.editor.setFont(default_font)

        # Create status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.hide()  # Initially hidden, will show when needed

        # Enable drag and drop
        self.editor.setAcceptDrops(True)

        # Initialize formatting
        self.update_formatting()

        # Word count timer
        self.word_count_timer = QTimer(self)
        self.word_count_timer.timeout.connect(self.update_word_count)
        self.word_count_timer.start(2000)  # Update every 2 seconds

    def setup_keyboard_shortcuts(self):
        """Setup keyboard shortcuts for common actions."""
        # Create shortcuts for common operations
        shortcuts = {
            QKeySequence.StandardKey.Save: lambda: self.save_requested.emit(),
            QKeySequence.StandardKey.Bold: self.bold_text,
            QKeySequence.StandardKey.Italic: self.italic_text,
            QKeySequence.StandardKey.Underline: self.underline_text,
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_L): lambda: self.set_alignment(Qt.AlignmentFlag.AlignLeft),
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_E): lambda: self.set_alignment(Qt.AlignmentFlag.AlignCenter),
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_R): lambda: self.set_alignment(Qt.AlignmentFlag.AlignRight),
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_J): lambda: self.set_alignment(Qt.AlignmentFlag.AlignJustify),
            QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_B): self.bullet_list,
            QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_N): self.numbered_list,
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Greater): self.increase_indent,
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Less): self.decrease_indent,
            # Find and replace
            QKeySequence.StandardKey.Find: self.show_find_dialog,
            QKeySequence.StandardKey.Replace: self.show_find_dialog,
            # Print shortcuts
            QKeySequence.StandardKey.Print: self.print_document,
            QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_P): self.print_preview,
            # Custom shortcuts for Transcribrr-specific actions
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_T): self.start_transcription,  # Ctrl+T for transcription
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_G): self.process_with_gpt4,  # Ctrl+G for GPT processing
            QKeySequence(Qt.Modifier.CTRL | Qt.Modifier.SHIFT | Qt.Key.Key_F): self.smart_format_text
            # Ctrl+Shift+F for smart format
        }

        # Register all shortcuts
        for key_sequence, callback in shortcuts.items():
            shortcut = QShortcut(key_sequence, self)
            shortcut.activated.connect(callback)

    def create_toolbar(self):
        self.toolbar = QToolBar("Edit")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(self.toolbar)

        # Font family selector
        self.font_family_combobox = QFontComboBox()
        self.font_family_combobox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.font_family_combobox.currentFontChanged.connect(self.font_family_changed)
        self.toolbar.addWidget(self.font_family_combobox)

        # Font size selector
        self.font_size_combobox = QComboBox()
        self.font_size_combobox.addItems(
            ['8', '9', '10', '11', '12', '14', '16', '18', '20', '22', '24', '26', '28', '36', '48', '72']
        )
        self.font_size_combobox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.font_size_combobox.setEditable(True)
        self.font_size_combobox.setCurrentText('12')  # Default font size
        self.font_size_combobox.currentTextChanged.connect(self.font_size_changed)
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
            'find_replace', resource_path('./icons/TextEditor/find.svg'),
            self.show_find_dialog, 'Find & Replace (Ctrl+F)', checkable=False
        )

        # Print
        self.add_toolbar_action(
            'print', resource_path('./icons/TextEditor/print.svg'),
            self.print_document, 'Print (Ctrl+P)', checkable=False
        )

        # Export menu
        self.add_export_menu()

        # Save button
        self.add_toolbar_action(
            'save', resource_path('./icons/save.svg'), lambda: self.save_requested.emit(), 'Save (Ctrl+S)',
            checkable=False
        )

        # Spacer to push toolbar items to the left
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.toolbar.addWidget(spacer)

        # Transcription and GPT-4 buttons
        self.add_action_with_spinner(
            'start_transcription', resource_path('./icons/transcribe.svg'), self.start_transcription,
            'Start Transcription (Ctrl+T)', './icons/spinner.gif', 'transcription_spinner'
        )

        self.add_action_with_spinner(
            'process_with_gpt4', resource_path('./icons/magic_wand.svg'), self.process_with_gpt4,
            'Process with GPT-4 (Ctrl+G)', './icons/spinner.gif', 'gpt_spinner'
        )

        # Smart Format button
        self.add_toolbar_action(
            'smart_format', resource_path('./icons/smart_format.svg'), self.smart_format_text,
            'Smart Format (Ctrl+Shift+F)', checkable=False
        )

        # Word count display
        self.word_count_label = QLabel("Words: 0")
        self.word_count_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.word_count_label.setMinimumWidth(80)
        self.toolbar.addWidget(self.word_count_label)

    def add_formatting_actions(self):
        # Bold
        bold_action = self.add_toolbar_action(
            'bold', resource_path('./icons/TextEditor/bold.svg'), self.bold_text, 'Bold (Ctrl+B)', checkable=True
        )
        bold_action.setShortcut(QKeySequence.StandardKey.Bold)

        # Italic
        italic_action = self.add_toolbar_action(
            'italic', resource_path('./icons/TextEditor/italic.svg'), self.italic_text, 'Italic (Ctrl+I)',
            checkable=True
        )
        italic_action.setShortcut(QKeySequence.StandardKey.Italic)

        # Underline
        underline_action = self.add_toolbar_action(
            'underline', resource_path('./icons/TextEditor/underline.svg'), self.underline_text, 'Underline (Ctrl+U)',
            checkable=True
        )
        underline_action.setShortcut(QKeySequence.StandardKey.Underline)

        # Strikethrough
        self.add_toolbar_action(
            'strikethrough', resource_path('./icons/TextEditor/strikethrough.svg'), self.strikethrough_text,
            'Strikethrough', checkable=True
        )

        # Highlight
        self.add_toolbar_action(
            'highlight', resource_path('./icons/TextEditor/highlight.svg'), self.highlight_text, 'Highlight Text'
        )

        # Font color
        self.add_toolbar_action(
            'font_color', resource_path('./icons/TextEditor/font_color.svg'), self.font_color, 'Font Color'
        )

    def add_alignment_actions(self):
        alignment_group = QActionGroup(self)

        align_left_action = self.add_toolbar_action(
            'align_left', resource_path('./icons/TextEditor/align_left.svg'),
            lambda: self.set_alignment(Qt.AlignmentFlag.AlignLeft), 'Align Left (Ctrl+L)', checkable=True
        )

        align_center_action = self.add_toolbar_action(
            'align_center', resource_path('./icons/TextEditor/align_center.svg'),
            lambda: self.set_alignment(Qt.AlignmentFlag.AlignCenter), 'Align Center (Ctrl+E)', checkable=True
        )

        align_right_action = self.add_toolbar_action(
            'align_right', resource_path('./icons/TextEditor/align_right.svg'),
            lambda: self.set_alignment(Qt.AlignmentFlag.AlignRight), 'Align Right (Ctrl+R)', checkable=True
        )

        justify_action = self.add_toolbar_action(
            'justify', resource_path('./icons/TextEditor/justify.svg'),
            lambda: self.set_alignment(Qt.AlignmentFlag.AlignJustify), 'Justify Text (Ctrl+J)', checkable=True
        )

        for action in [align_left_action, align_center_action, align_right_action, justify_action]:
            alignment_group.addAction(action)

    def add_list_actions(self):
        self.add_toolbar_action(
            'bullet_list', resource_path('./icons/TextEditor/bullet.svg'), self.bullet_list,
            'Bullet List (Ctrl+Shift+B)'
        )
        self.add_toolbar_action(
            'numbered_list', resource_path('./icons/TextEditor/numbered.svg'), self.numbered_list,
            'Numbered List (Ctrl+Shift+N)'
        )
        self.add_toolbar_action(
            'increase_indent', resource_path('./icons/TextEditor/increase_indent.svg'), self.increase_indent,
            'Increase Indent (Ctrl+>)'
        )
        self.add_toolbar_action(
            'decrease_indent', resource_path('./icons/TextEditor/decrease_indent.svg'), self.decrease_indent,
            'Decrease Indent (Ctrl+<)'
        )

    def add_export_menu(self):
        self.export_menu = QMenu()
        export_pdf_action = QAction('Export to PDF', self)
        export_pdf_action.triggered.connect(self.export_to_pdf)
        self.export_menu.addAction(export_pdf_action)

        export_word_action = QAction('Export to Word', self)
        export_word_action.triggered.connect(self.export_to_word)
        self.export_menu.addAction(export_word_action)

        export_text_action = QAction('Export to Plain Text', self)
        export_text_action.triggered.connect(self.export_to_text)
        self.export_menu.addAction(export_text_action)

        export_html_action = QAction('Export to HTML', self)
        export_html_action.triggered.connect(self.export_to_html)
        self.export_menu.addAction(export_html_action)

        export_button = QToolButton()
        export_button.setText('Export')
        export_button.setIcon(QIcon(resource_path('./icons/export.svg')))
        export_button.setToolTip('Export to different formats')
        export_button.setMenu(self.export_menu)
        export_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.toolbar.addWidget(export_button)

    def add_action_with_spinner(self, action_name, icon_path, callback, tooltip, spinner_icon, spinner_name):
        action_button = self.add_toolbar_action(
            action_name, resource_path(icon_path), callback, tooltip, checkable=False
        )
        spinner_movie = QMovie(resource_path(spinner_icon))
        spinner_movie.setScaledSize(QSize(30, 30))
        spinner_label = QLabel()
        spinner_label.setMovie(spinner_movie)
        spinner_label.setFixedSize(QSize(30, 30))
        spinner_action = QWidgetAction(self.toolbar)
        spinner_action.setDefaultWidget(spinner_label)
        self.toolbar.addAction(spinner_action)
        spinner_action.setVisible(False)
        setattr(self, f"{spinner_name}_button", action_button)
        setattr(self, f"{spinner_name}_movie", spinner_movie)
        setattr(self, f"{spinner_name}_action", spinner_action)

    def toggle_spinner(self, spinner_name):
        button = getattr(self, f"{spinner_name}_button", None)
        spinner_action = getattr(self, f"{spinner_name}_action", None)
        spinner_movie = getattr(self, f"{spinner_name}_movie", None)

        if not all([button, spinner_action, spinner_movie]):
            logging.error(f"Spinner components not found for {spinner_name}")
            return

        if button.isVisible():
            spinner_action.setVisible(True)
            spinner_movie.start()
            button.setVisible(False)
            self.show_status_message("Processing...")
        else:
            spinner_movie.stop()
            spinner_action.setVisible(False)
            button.setVisible(True)
            self.hide_status_message()

    def toggle_gpt_spinner(self):
        self.toggle_spinner('gpt_spinner')

    def toggle_transcription_spinner(self):
        self.toggle_spinner('transcription_spinner')

    def add_toolbar_action(self, action_name, icon_path, callback, tooltip, checkable=False):
        action = QAction(QIcon(icon_path) if icon_path else None, tooltip, self)
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
            QMessageBox.warning(self, "Invalid Font Size", "Please enter a valid number for font size.")

    def bold_text(self):
        weight = QFont.Weight.Bold if not self.editor.fontWeight() == QFont.Weight.Bold else QFont.Weight.Normal
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
            self.show_status_message(f"Text highlighted with color: {color.name()}")

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
            Qt.AlignmentFlag.AlignJustify: "justified"
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
        preview.paintRequested.connect(lambda p: self.editor.document().print(p))
        preview.exec()

    def export_to_pdf(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to PDF", "", "PDF Files (*.pdf)")
        if file_path:
            try:
                if not file_path.endswith('.pdf'):
                    file_path += '.pdf'

                printer = QPrinter(QPrinter.PrinterMode.HighResolution)
                printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
                printer.setOutputFileName(file_path)
                self.editor.document().print(printer)

                self.show_status_message(f"Document exported to {os.path.basename(file_path)}")
                QMessageBox.information(self, "Export to PDF", f"Document successfully exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export to PDF: {e}")
                logging.error(f"PDF export error: {e}")

    def export_to_word(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to Word", "", "Word Documents (*.docx)")
        if file_path:
            try:
                if not file_path.endswith('.docx'):
                    file_path += '.docx'

                doc = docx.Document()
                html = self.editor.toHtml()
                new_parser = HtmlToDocx()
                new_parser.add_html_to_document(html, doc)
                doc.save(file_path)

                self.show_status_message(f"Document exported to {os.path.basename(file_path)}")
                QMessageBox.information(self, "Export to Word", f"Document successfully exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export to Word: {e}")
                logging.error(f"Word export error: {e}")

    def export_to_text(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to Plain Text", "", "Text Files (*.txt)")
        if file_path:
            try:
                if not file_path.endswith('.txt'):
                    file_path += '.txt'

                plain_text = self.editor.toPlainText()
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(plain_text)

                self.show_status_message(f"Document exported to {os.path.basename(file_path)}")
                QMessageBox.information(self, "Export to Text", f"Document successfully exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export to text: {e}")
                logging.error(f"Text export error: {e}")

    def export_to_html(self):
        """Export document to HTML file."""
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to HTML", "", "HTML Files (*.html)")
        if file_path:
            try:
                if not file_path.endswith('.html'):
                    file_path += '.html'

                html = self.editor.toHtml()
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(html)

                self.show_status_message(f"Document exported to {os.path.basename(file_path)}")
                QMessageBox.information(self, "Export to HTML", f"Document successfully exported to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export to HTML: {e}")
                logging.error(f"HTML export error: {e}")

    def show_status_message(self, message, timeout=3000):
        """Show a temporary status message."""
        self.statusBar().showMessage(message, timeout)
        if not self.statusBar().isVisible():
            self.statusBar().show()

    def hide_status_message(self):
        """Hide the status bar if it's showing a message."""
        self.statusBar().clearMessage()
        self.statusBar().hide()

    def update_word_count(self):
        """Update the word count display."""
        text = self.editor.toPlainText()
        word_count = len(text.split()) if text else 0
        self.word_count_label.setText(f"Words: {word_count}")

    def serialize_text_document(self):
        """Serialize the text document to HTML."""
        try:
            formatted_text = self.editor.toHtml()
            return formatted_text
        except Exception as e:
            logging.error(f"Error serializing text document: {e}")
            return None

    def deserialize_text_document(self, text_data):
        """Deserialize and load text into the editor."""
        if text_data:
            try:
                # If it's bytes, decode to string
                if isinstance(text_data, bytes):
                    text_data = text_data.decode('utf-8')

                # Check if it contains HTML tags
                if '<' in text_data and '>' in text_data:
                    self.editor.setHtml(text_data)
                else:
                    self.editor.setPlainText(text_data)
            except Exception as e:
                logging.error(f"Error deserializing text document: {e}")
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
            QMessageBox.warning(self, "Empty Text", "Please add some text before formatting.")
            return

        # Confirm with user if text is long
        if len(current_text) > 10000:  # Roughly 2000 words
            response = QMessageBox.question(
                self,
                "Format Long Text",
                "The text is quite long, which may take some time to process. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if response == QMessageBox.StandardButton.No:
                return

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
            self.font_size_combobox.setCurrentText('')

        self.font_family_combobox.blockSignals(False)
        self.font_size_combobox.blockSignals(False)

        # Update formatting actions
        if 'bold' in self._toolbar_actions:
            self._toolbar_actions['bold'].setChecked(current_font.bold())
        if 'italic' in self._toolbar_actions:
            self._toolbar_actions['italic'].setChecked(current_font.italic())
        if 'underline' in self._toolbar_actions:
            self._toolbar_actions['underline'].setChecked(current_font.underline())
        if 'strikethrough' in self._toolbar_actions:
            self._toolbar_actions['strikethrough'].setChecked(current_font.strikeOut())

        # Update alignment actions
        alignment = self.editor.alignment()
        if 'align_left' in self._toolbar_actions:
            self._toolbar_actions['align_left'].setChecked(alignment == Qt.AlignmentFlag.AlignLeft)
        if 'align_center' in self._toolbar_actions:
            self._toolbar_actions['align_center'].setChecked(alignment == Qt.AlignmentFlag.AlignCenter)
        if 'align_right' in self._toolbar_actions:
            self._toolbar_actions['align_right'].setChecked(alignment == Qt.AlignmentFlag.AlignRight)
        if 'justify' in self._toolbar_actions:
            self._toolbar_actions['justify'].setChecked(alignment == Qt.AlignmentFlag.AlignJustify)

    def dragEnterEvent(self, event):
        """Handle drag enter events for drag and drop functionality."""
        # Accept drag events if they contain text or URLs
        if event.mimeData().hasText() or event.mimeData().hasUrls():
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

        # Handle plain text
        if mime_data.hasText():
            text = mime_data.text()
            cursor = self.editor.cursorForPosition(event.position().toPoint())
            cursor.insertText(text)
            event.acceptProposedAction()
            return

        event.ignore()

    def load_file(self, file_path):
        """Load content from a file into the editor."""
        try:
            # Check file extension to determine how to load it
            _, extension = os.path.splitext(file_path)
            extension = extension.lower()

            if extension in ['.txt', '.md', '.csv', '.json', '.xml', '.html', '.htm']:
                with open(file_path, 'r', encoding='utf-8') as file:
                    text = file.read()

                if extension in ['.html', '.htm']:
                    self.editor.setHtml(text)
                else:
                    self.editor.setPlainText(text)

                self.show_status_message(f"Loaded file: {os.path.basename(file_path)}")

            else:
                QMessageBox.warning(self, "Unsupported File",
                                    f"The file type {extension} is not supported for direct editing.")

        except Exception as e:
            QMessageBox.critical(self, "Error Loading File", f"Failed to load file: {e}")
            logging.error(f"Error loading file {file_path}: {e}")


# For standalone testing
def main():
    app = QApplication(sys.argv)
    editor = TextEditor()
    editor.resize(800, 600)
    editor.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()