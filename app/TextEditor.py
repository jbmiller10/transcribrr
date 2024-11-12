import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QToolBar, QColorDialog, QWidget,
    QWidgetAction, QFontComboBox, QComboBox, QSizePolicy, QLabel, QToolButton, QMenu, QFileDialog,
    QMessageBox,QPlainTextEdit, QPushButton
)
from PyQt6.QtGui import QIcon, QFont, QColor, QTextListFormat, QActionGroup, QTextCursor, QAction, QMovie, QTextCharFormat
from PyQt6.QtCore import Qt, QSize, pyqtSignal
import docx
from htmldocx import HtmlToDocx
from PyPDF2 import PdfFileWriter
from PyQt6.QtPrintSupport import QPrinter
from bs4 import BeautifulSoup
import logging
from app.utils import  resource_path

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
        self.create_toolbar()
        self.is_markdown_mode = False  # Track current mode (removed, but kept false for completeness)

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
        self.font_size_combobox.addItems(['8', '9', '10', '11', '12', '14', '16', '18', '20', '22', '24', '26', '28', '36', '48', '72'])
        self.font_size_combobox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.font_size_combobox.setEditable(True)
        self.font_size_combobox.currentTextChanged.connect(self.font_size_changed)
        self.toolbar.addWidget(self.font_size_combobox)

        # Bold button
        self.add_toolbar_action('bold',  resource_path('./icons/TextEditor/bold.svg'), self.bold_text, 'Bold (Ctrl+B)', checkable=True)
        # Italic button
        self.add_toolbar_action('italic',  resource_path('./icons/TextEditor/italic.svg'), self.italic_text, 'Italic (Ctrl+I)', checkable=True)
        # Underline button
        self.add_toolbar_action('underline',  resource_path('./icons/TextEditor/underline.svg'), self.underline_text, 'Underline (Ctrl+U)', checkable=True)

        # Strikethrough button
        self.add_toolbar_action('strikethrough',  resource_path('./icons/TextEditor/strikethrough.svg'), self.strikethrough_text,
                                'Strikethrough', checkable=True)
        # Highlight button
        self.add_toolbar_action('highlight',  resource_path('./icons/TextEditor/highlight.svg'), self.highlight_text,
                                'Highlight Text')

        # Font color button
        self.add_toolbar_action('font_color',  resource_path('./icons/TextEditor/font_color.svg'), self.font_color, 'Font Color')

        # Alignment actions
        alignment_group = QActionGroup(self)
        self.add_toolbar_action('align_left',  resource_path('./icons/TextEditor/align_left.svg'),
                                lambda: self.set_alignment(Qt.AlignmentFlag.AlignLeft), 'Align Left (Ctrl+L)', checkable=True)
        self.add_toolbar_action('align_center',  resource_path('./icons/TextEditor/align_center.svg'),
                                lambda: self.set_alignment(Qt.AlignmentFlag.AlignCenter), 'Align Center (Ctrl+E)', checkable=True)
        self.add_toolbar_action('align_right',  resource_path('./icons/TextEditor/align_right.svg'),
                                lambda: self.set_alignment(Qt.AlignmentFlag.AlignRight), 'Align Right (Ctrl+R)', checkable=True)
        self.add_toolbar_action('justify',  resource_path('./icons/TextEditor/justify.svg'),
                                lambda: self.set_alignment(Qt.AlignmentFlag.AlignJustify), 'Justify Text', checkable=True)

        for action_name in ['align_left', 'align_center', 'align_right', 'justify']:
            action = self._toolbar_actions[action_name]
            alignment_group.addAction(action)

        # List formatting actions
        self.add_toolbar_action('bullet_list',  resource_path('./icons/TextEditor/bullet.svg'), self.bullet_list, 'Bullet List')
        self.add_toolbar_action('numbered_list',  resource_path('./icons/TextEditor/numbered.svg'), self.numbered_list, 'Numbered List')
        self.add_toolbar_action('increase_indent',  resource_path('./icons/TextEditor/increase_indent.svg'), self.increase_indent, 'Increase Indent')
        self.add_toolbar_action('decrease_indent',  resource_path('./icons/TextEditor/decrease_indent.svg'), self.decrease_indent, 'Decrease Indent')

        # Export menu
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

        # Save button
        self.add_toolbar_action('save',  resource_path('./icons/save.svg'), self.save_requested, 'Save', checkable=False)

        # Spacer to push toolbar items to the left
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.toolbar.addWidget(spacer)

        # Transcription and GPT-4 buttons
        self.transcription_button = self.add_toolbar_action(
            'start_transcription',
             resource_path('./icons/transcribe.svg'),
            self.start_transcription,
            'Start Transcription',
            checkable=False
        )
        self.transcription_spinner_movie = QMovie( resource_path('./icons/spinner.gif'))
        self.transcription_spinner_movie.setScaledSize(QSize(30, 30))
        self.transcription_spinner_label = QLabel()
        self.transcription_spinner_label.setMovie(self.transcription_spinner_movie)
        self.transcription_spinner_label.setFixedSize(QSize(30, 30))
        self.transcription_spinner_action = QWidgetAction(self.toolbar)
        self.transcription_spinner_action.setDefaultWidget(self.transcription_spinner_label)
        self.toolbar.addAction(self.transcription_spinner_action)
        self.transcription_spinner_action.setVisible(False)

        self.gpt4_button = self.add_toolbar_action(
            'process_with_gpt4',
             resource_path('./icons/magic_wand.svg'),
            self.process_with_gpt4,
            'Process with GPT-4',
            checkable=False
        )
        self.gpt_spinner_movie = QMovie( resource_path('./icons/spinner.gif'))
        self.gpt_spinner_movie.setScaledSize(QSize(30, 30))
        self.gpt_spinner_label = QLabel()
        self.gpt_spinner_label.setMovie(self.gpt_spinner_movie)
        self.gpt_spinner_label.setFixedSize(QSize(30, 30))
        self.gpt_spinner_action = QWidgetAction(self.toolbar)
        self.gpt_spinner_action.setDefaultWidget(self.gpt_spinner_label)
        self.toolbar.addAction(self.gpt_spinner_action)
        self.gpt_spinner_action.setVisible(False)

        # Smart Format button
        self.add_toolbar_action('smart_format',  resource_path('./icons/smart_format.svg'), self.smart_format_text, 'Smart Format', checkable=False)

    def toggle_gpt_spinner(self):
        if self.gpt4_button.isVisible():
            self.gpt_spinner_action.setVisible(True)
            self.gpt_spinner_movie.start()
            self.gpt4_button.setVisible(False)
        else:
            self.gpt_spinner_movie.stop()
            self.gpt_spinner_action.setVisible(False)
            self.gpt4_button.setVisible(True)

    def toggle_transcription_spinner(self):
        if self.transcription_button.isVisible():
            self.transcription_spinner_action.setVisible(True)
            self.transcription_spinner_movie.start()
            self.transcription_button.setVisible(False)
        else:
            self.transcription_spinner_movie.stop()
            self.transcription_spinner_action.setVisible(False)
            self.transcription_button.setVisible(True)

    def add_toolbar_action(self, action_name, icon_path, callback, tooltip, checkable=False):
        action = QAction(QIcon(icon_path) if icon_path else None, tooltip, self)
        action.setCheckable(checkable)
        if callback:
            # Ensure that callback is callable
            if isinstance(callback, str):
                pass
            else:
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
        fmt = self.editor.currentCharFormat()
        fmt.setFontWeight(QFont.Weight.Bold if not fmt.fontWeight() == QFont.Weight.Bold else QFont.Weight.Normal)
        self.editor.mergeCurrentCharFormat(fmt)

    def italic_text(self):
        fmt = self.editor.currentCharFormat()
        fmt.setFontItalic(not fmt.fontItalic())
        self.editor.mergeCurrentCharFormat(fmt)

    def underline_text(self):
        fmt = self.editor.currentCharFormat()
        fmt.setFontUnderline(not fmt.fontUnderline())
        self.editor.mergeCurrentCharFormat(fmt)

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
        # Update the checked state of alignment actions
        for action_name in ['align_left', 'align_center', 'align_right', 'justify']:
            self._toolbar_actions[action_name].setChecked(False)
        if alignment == Qt.AlignmentFlag.AlignLeft:
            self._toolbar_actions['align_left'].setChecked(True)
        elif alignment == Qt.AlignmentFlag.AlignCenter:
            self._toolbar_actions['align_center'].setChecked(True)
        elif alignment == Qt.AlignmentFlag.AlignRight:
            self._toolbar_actions['align_right'].setChecked(True)
        elif alignment == Qt.AlignmentFlag.AlignJustify:
            self._toolbar_actions['justify'].setChecked(True)

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
        list_format = cursor.currentList().format() if cursor.currentList() else QTextListFormat()
        list_format.setIndent(list_format.indent() + 1)
        cursor.createList(list_format)

    def decrease_indent(self):
        cursor = self.editor.textCursor()
        list_format = cursor.currentList().format() if cursor.currentList() else QTextListFormat()
        list_format.setIndent(max(list_format.indent() - 1, 1))
        cursor.createList(list_format)

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
        # Always save as HTML
        cursor = self.editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        formatted_text = cursor.selection().toHtml()
        return formatted_text.encode('utf-8')

    def deserialize_text_document(self, text_data):
        if text_data:
            self.editor.setHtml(text_data.decode('utf-8') if isinstance(text_data, bytes) else text_data)
        else:
            self.editor.clear()

    def save_editor_state(self):
        # Save the current state of the text editor to the database
        # Assuming 'mode_switch' and 'current_selected_item' are defined elsewhere
        if hasattr(self, 'mode_switch') and self.mode_switch.value() == 0:  # Raw transcript mode
            formatted_data = self.serialize_text_document()
            field_to_update = 'raw_transcript_formatted'
        else:  # Processed text mode
            formatted_data = self.serialize_text_document()
            field_to_update = 'processed_text_formatted'

        try:
            conn = create_connection(resource_path("./database/database.sqlite"))
            recording_id = self.current_selected_item.get_id()
            update_recording(conn, recording_id, **{field_to_update: formatted_data})
            conn.close()
            QMessageBox.information(self, "Success", "Transcription saved successfully.")
        except Exception as e:
            logging.error(f"Failed to save transcription: {e}")
            QMessageBox.critical(self, "Error", "Failed to save transcription.")

    def process_with_gpt4(self):
        self.gpt4_processing_requested.emit()

    def start_transcription(self):
        self.transcription_requested.emit()

    def smart_format_text(self):
        # Emit the smart_format_requested signal with the current text as argument
        self.smart_format_requested.emit(self.editor.toPlainText())