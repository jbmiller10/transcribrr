import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QToolBar, QColorDialog, QWidget,
    QWidgetAction, QFontComboBox, QComboBox, QSizePolicy, QLabel, QToolButton, QMenu, QFileDialog,
    QMessageBox, QPlainTextEdit, QPushButton
)
from PyQt6.QtGui import QIcon, QFont, QColor, QTextListFormat, QActionGroup, QTextCursor, QAction, QMovie, QTextCharFormat, QKeySequence
from PyQt6.QtCore import Qt, QSize, pyqtSignal
import docx
from htmldocx import HtmlToDocx
from PyPDF2 import PdfFileWriter
from PyQt6.QtPrintSupport import QPrinter
from bs4 import BeautifulSoup
import logging
from app.utils import resource_path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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

        # Setup the toolbar and connect formatting updates
        self.create_toolbar()
        self.editor.cursorPositionChanged.connect(self.update_formatting)
        self.editor.selectionChanged.connect(self.update_formatting)
        self.update_formatting()

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
        self.font_size_combobox.currentTextChanged.connect(self.font_size_changed)
        self.toolbar.addWidget(self.font_size_combobox)

        # Text formatting actions
        self.add_formatting_actions()

        # Alignment actions
        self.add_alignment_actions()

        # List formatting actions
        self.add_list_actions()

        # Export menu
        self.add_export_menu()

        # Save button
        self.add_toolbar_action(
            'save', resource_path('./icons/save.svg'), lambda: self.save_requested.emit(), 'Save', checkable=False
        )

        # Spacer to push toolbar items to the left
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.toolbar.addWidget(spacer)

        # Transcription and GPT-4 buttons
        self.add_action_with_spinner(
            'start_transcription', resource_path('./icons/transcribe.svg'), self.start_transcription,
            'Start Transcription', './icons/spinner.gif', 'transcription_spinner'
        )

        self.add_action_with_spinner(
            'process_with_gpt4', resource_path('./icons/magic_wand.svg'), self.process_with_gpt4,
            'Process with GPT-4', './icons/spinner.gif', 'gpt_spinner'
        )

        # Smart Format button
        self.add_toolbar_action(
            'smart_format', resource_path('./icons/smart_format.svg'), self.smart_format_text, 'Smart Format', checkable=False
        )

    def add_formatting_actions(self):
        # Bold
        bold_action = self.add_toolbar_action(
            'bold', resource_path('./icons/TextEditor/bold.svg'), self.bold_text, 'Bold (Ctrl+B)', checkable=True
        )
        bold_action.setShortcut(QKeySequence.StandardKey.Bold)

        # Italic
        italic_action = self.add_toolbar_action(
            'italic', resource_path('./icons/TextEditor/italic.svg'), self.italic_text, 'Italic (Ctrl+I)', checkable=True
        )
        italic_action.setShortcut(QKeySequence.StandardKey.Italic)

        # Underline
        underline_action = self.add_toolbar_action(
            'underline', resource_path('./icons/TextEditor/underline.svg'), self.underline_text, 'Underline (Ctrl+U)', checkable=True
        )
        underline_action.setShortcut(QKeySequence.StandardKey.Underline)

        # Strikethrough
        self.add_toolbar_action(
            'strikethrough', resource_path('./icons/TextEditor/strikethrough.svg'), self.strikethrough_text, 'Strikethrough', checkable=True
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
        align_left_action.setShortcut('Ctrl+L')

        align_center_action = self.add_toolbar_action(
            'align_center', resource_path('./icons/TextEditor/align_center.svg'),
            lambda: self.set_alignment(Qt.AlignmentFlag.AlignCenter), 'Align Center (Ctrl+E)', checkable=True
        )
        align_center_action.setShortcut('Ctrl+E')

        align_right_action = self.add_toolbar_action(
            'align_right', resource_path('./icons/TextEditor/align_right.svg'),
            lambda: self.set_alignment(Qt.AlignmentFlag.AlignRight), 'Align Right (Ctrl+R)', checkable=True
        )
        align_right_action.setShortcut('Ctrl+R')

        justify_action = self.add_toolbar_action(
            'justify', resource_path('./icons/TextEditor/justify.svg'),
            lambda: self.set_alignment(Qt.AlignmentFlag.AlignJustify), 'Justify Text', checkable=True
        )

        for action in [align_left_action, align_center_action, align_right_action, justify_action]:
            alignment_group.addAction(action)

    def add_list_actions(self):
        self.add_toolbar_action(
            'bullet_list', resource_path('./icons/TextEditor/bullet.svg'), self.bullet_list, 'Bullet List'
        )
        self.add_toolbar_action(
            'numbered_list', resource_path('./icons/TextEditor/numbered.svg'), self.numbered_list, 'Numbered List'
        )
        self.add_toolbar_action(
            'increase_indent', resource_path('./icons/TextEditor/increase_indent.svg'), self.increase_indent, 'Increase Indent'
        )
        self.add_toolbar_action(
            'decrease_indent', resource_path('./icons/TextEditor/decrease_indent.svg'), self.decrease_indent, 'Decrease Indent'
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

        export_button = QToolButton()
        export_button.setText('Export')
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
        button = getattr(self, f"{spinner_name}_button")
        spinner_action = getattr(self, f"{spinner_name}_action")
        spinner_movie = getattr(self, f"{spinner_name}_movie")

        if button.isVisible():
            spinner_action.setVisible(True)
            spinner_movie.start()
            button.setVisible(False)
        else:
            spinner_movie.stop()
            spinner_action.setVisible(False)
            button.setVisible(True)

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

    def font_size_changed(self, size):
        try:
            size_float = float(size)
            self.editor.setFontPointSize(size_float)
        except ValueError:
            QMessageBox.warning(self, "Invalid Font Size", "Please enter a valid number for font size.")

    def bold_text(self):
        weight = QFont.Weight.Bold if not self.editor.fontWeight() == QFont.Weight.Bold else QFont.Weight.Normal
        self.editor.setFontWeight(weight)

    def italic_text(self):
        state = not self.editor.fontItalic()
        self.editor.setFontItalic(state)

    def underline_text(self):
        state = not self.editor.fontUnderline()
        self.editor.setFontUnderline(state)

    def strikethrough_text(self):
        fmt = self.editor.currentCharFormat()
        fmt.setFontStrikeOut(not fmt.fontStrikeOut())
        self.editor.mergeCurrentCharFormat(fmt)

    def highlight_text(self):
        color = QColorDialog.getColor()
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setBackground(color)
            self.editor.mergeCurrentCharFormat(fmt)

    def font_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.editor.setTextColor(color)

    def set_alignment(self, alignment):
        self.editor.setAlignment(alignment)

    def bullet_list(self):
        cursor = self.editor.textCursor()
        list_format = QTextListFormat()
        list_format.setStyle(QTextListFormat.Style.ListDisc)
        cursor.createList(list_format)

    def numbered_list(self):
        cursor = self.editor.textCursor()
        list_format = QTextListFormat()
        list_format.setStyle(QTextListFormat.Style.ListDecimal)
        cursor.createList(list_format)

    def increase_indent(self):
        cursor = self.editor.textCursor()
        if cursor.blockFormat().indent() < 15:
            block_format = cursor.blockFormat()
            block_format.setIndent(block_format.indent() + 1)
            cursor.setBlockFormat(block_format)

    def decrease_indent(self):
        cursor = self.editor.textCursor()
        if cursor.blockFormat().indent() > 0:
            block_format = cursor.blockFormat()
            block_format.setIndent(block_format.indent() - 1)
            cursor.setBlockFormat(block_format)

    def export_to_pdf(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to PDF", "", "PDF Files (*.pdf)")
        if file_path:
            printer = QPrinter(QPrinter.PrinterMode.HighResolution)
            printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
            printer.setOutputFileName(file_path)
            self.editor.document().print(printer)
            QMessageBox.information(self, "Export to PDF", f"Document successfully exported to {file_path}")

    def export_to_word(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to Word", "", "Word Documents (*.docx)")
        if file_path:
            doc = docx.Document()
            html = self.editor.toHtml()
            new_parser = HtmlToDocx()
            new_parser.add_html_to_document(html, doc)
            doc.save(file_path)
            QMessageBox.information(self, "Export to Word", f"Document successfully exported to {file_path}")

    def export_to_text(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Export to Plain Text", "", "Text Files (*.txt)")
        if file_path:
            plain_text = self.editor.toPlainText()
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(plain_text)
            QMessageBox.information(self, "Export to Text", f"Document successfully exported to {file_path}")

    def serialize_text_document(self):
        formatted_text = self.editor.document().toHtml()
        return formatted_text.encode('utf-8')

    def deserialize_text_document(self, text_data):
        if text_data:
            self.editor.setHtml(text_data.decode('utf-8') if isinstance(text_data, bytes) else text_data)
        else:
            self.editor.clear()

    def save_editor_state(self):
        # Save the current state of the text editor to the database
        # The actual database interaction is not modified here
        pass  # Leaving as is to respect external dependencies

    def process_with_gpt4(self):
        self.gpt4_processing_requested.emit()

    def start_transcription(self):
        self.transcription_requested.emit()

    def smart_format_text(self):
        # Emit the smart_format_requested signal with the current text as argument
        self.smart_format_requested.emit(self.editor.toPlainText())

    def update_formatting(self):
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
        self._toolbar_actions['bold'].setChecked(current_font.bold())
        self._toolbar_actions['italic'].setChecked(current_font.italic())
        self._toolbar_actions['underline'].setChecked(current_font.underline())
        self._toolbar_actions['strikethrough'].setChecked(current_font.strikeOut())

        # Update alignment actions
        alignment = self.editor.alignment()
        self._toolbar_actions['align_left'].setChecked(alignment == Qt.AlignmentFlag.AlignLeft)
        self._toolbar_actions['align_center'].setChecked(alignment == Qt.AlignmentFlag.AlignCenter)
        self._toolbar_actions['align_right'].setChecked(alignment == Qt.AlignmentFlag.AlignRight)
        self._toolbar_actions['justify'].setChecked(alignment == Qt.AlignmentFlag.AlignJustify)