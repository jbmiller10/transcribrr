import sys

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QTextEdit, QToolBar, QColorDialog, QSpacerItem, QWidget,QWidgetAction,
    QFontDialog, QFontComboBox, QComboBox, QSizePolicy, QLabel
)
from PyQt6.QtGui import QIcon, QFont, QColor, QTextListFormat, QAction, QActionGroup,QTextCursor,QMovie
from PyQt6.QtCore import Qt, QSize, pyqtSignal,QBuffer,QIODevice,QDataStream
import markdown2
import logging

class TextEditor(QMainWindow):
    transcription_requested = pyqtSignal()
    gpt4_processing_requested = pyqtSignal()
    save_requested = pyqtSignal()

    def __init__(self):
        super().__init__()

        self.editor = QTextEdit()
        self.setCentralWidget(self.editor)
        self._toolbar_actions = {}
        self.create_toolbar()

    def create_toolbar(self):
        self.toolbar = QToolBar("Edit")
        self.toolbar.setMovable(False)
        self.toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(self.toolbar)

        self.font_family_combobox = QFontComboBox()
        self.font_family_combobox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.font_family_combobox.currentFontChanged.connect(self.font_family_changed)
        self.toolbar.addWidget(self.font_family_combobox)

        self.font_size_combobox = QComboBox()
        self.font_size_combobox.addItems(['8', '9', '10', '11', '12', '14', '16', '18', '20', '22', '24', '26', '28', '36', '48', '72'])
        self.font_size_combobox.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        self.font_size_combobox.setEditable(True)
        self.font_size_combobox.currentTextChanged.connect(self.font_size_changed)
        self.toolbar.addWidget(self.font_size_combobox)

        self.add_toolbar_action('bold', './icons/TextEditor/bold.svg', self.bold_text, 'Bold (Ctrl+B)', True)
        self.add_toolbar_action('italic', './icons/TextEditor/italic.svg', self.italic_text, 'Italic (Ctrl+I)', True)
        self.add_toolbar_action('underline', './icons/TextEditor/underline.svg', self.underline_text, 'Underline (Ctrl+U)', True)
        self.add_toolbar_action('font_color', './icons/TextEditor/font_color.svg', self.font_color, 'Font Color')

        alignment_group = QActionGroup(self)
        self.add_toolbar_action('align_left', './icons/TextEditor/align_left.svg', lambda: self.set_alignment(Qt.AlignmentFlag.AlignLeft), 'Align Left (Ctrl+L)', True)
        self.add_toolbar_action('align_center', './icons/TextEditor/align_center.svg', lambda: self.set_alignment(Qt.AlignmentFlag.AlignCenter), 'Align Center (Ctrl+E)', True)
        self.add_toolbar_action('align_right', './icons/TextEditor/align_right.svg', lambda: self.set_alignment(Qt.AlignmentFlag.AlignRight), 'Align Right (Ctrl+R)', True)

        for alignment_action in ['align_left', 'align_center', 'align_right']:
            action = self._toolbar_actions[alignment_action]
            alignment_group.addAction(action)

        self.add_toolbar_action('bullet_list', './icons/TextEditor/bullet.svg', self.bullet_list, 'Bullet List')
        self.add_toolbar_action('numbered_list', './icons/TextEditor/numbered.svg', self.numbered_list, 'Numbered List')

        self.add_toolbar_action('increase_indent', './icons/TextEditor/increase_indent.svg', self.increase_indent, 'Increase Indent')
        self.add_toolbar_action('decrease_indent', './icons/TextEditor/decrease_indent.svg', self.decrease_indent, 'Decrease Indent')

        self.add_toolbar_action(
            'save',
            './icons/save.svg',
            self.save_requested,
            'Save',
            checkable=False
        )

        spacer = QWidget()  # A simple widget that acts as a spacer
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.toolbar.addWidget(spacer)  # Add the spacer to the toolbar

        self.transcription_button = self.add_toolbar_action(
            'start_transcription',
            './icons/transcribe.svg',
            self.start_transcription,
            'Start Transcription',
            checkable=False
        )
        self.transcription_spinner_movie = QMovie('./icons/spinner.gif')
        self.transcription_spinner_movie.setScaledSize(QSize(40, 40))
        self.transcription_spinner_label = QLabel()
        self.transcription_spinner_label.setMovie(self.transcription_spinner_movie)
        self.transcription_spinner_label.setFixedSize(QSize(40, 40))
        self.transcription_spinner_action = QWidgetAction(self.toolbar)
        self.transcription_spinner_action.setDefaultWidget(self.transcription_spinner_label)
        self.toolbar.addAction(self.transcription_spinner_action)
        self.transcription_spinner_action.setVisible(False) 



        self.gpt4_button = self.add_toolbar_action(
            'process_with_gpt4',
            './icons/magic_wand.svg',
            self.process_with_gpt4,
            'Process with GPT-4',
            checkable=False
        )
        self.gpt_spinner_movie = QMovie('./icons/spinner.gif')
        self.gpt_spinner_movie.setScaledSize(QSize(40, 40))
        self.gpt_spinner_label = QLabel()
        self.gpt_spinner_label.setMovie(self.gpt_spinner_movie)
        self.gpt_spinner_label.setFixedSize(QSize(40, 40))
        self.gpt_spinner_action = QWidgetAction(self.toolbar)
        self.gpt_spinner_action.setDefaultWidget(self.gpt_spinner_label)
        self.toolbar.addAction(self.gpt_spinner_action)
        self.gpt_spinner_action.setVisible(False)


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
            action.triggered.connect(callback)
        self.toolbar.addAction(action)
        self._toolbar_actions[action_name] = action
        return action

    def font_family_changed(self, font):
        self.editor.setCurrentFont(font)

    def font_size_changed(self, size):
        self.editor.setFontPointSize(float(size))

    def bold_text(self):
        font = self.editor.currentFont()
        font.setBold(not font.bold())
        self.editor.setCurrentFont(font)

    def italic_text(self):
        font = self.editor.currentFont()
        font.setItalic(not font.italic())
        self.editor.setCurrentFont(font)

    def underline_text(self):
        font = self.editor.currentFont()
        font.setUnderline(not font.underline())
        self.editor.setCurrentFont(font)

    def set_alignment(self, alignment):
        self.editor.setAlignment(alignment)

    def font_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.editor.setTextColor(color)

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

    def start_transcription(self):
        self.transcription_requested.emit()

    def process_with_gpt4(self):
        self.gpt4_processing_requested.emit()
    def serialize_text_document(self):
        cursor = self.editor.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        formatted_text = cursor.selection().toHtml()
        return formatted_text.encode('utf-8')  # Serialize as UTF-8 bytes

    def deserialize_text_document(self, text_data):
        if text_data:  # If there's data, set it in the editor
            self.editor.setHtml(text_data.decode('utf-8') if isinstance(text_data, bytes) else text_data)
        else:  # If there's no data, clear the editor
            self.editor.clear()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    textEditor = TextEditor()
    textEditor.show()
    sys.exit(app.exec())