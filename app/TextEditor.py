import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QTextEdit, QToolBar, QColorDialog, QFontDialog, QFontComboBox, QComboBox
from PyQt6.QtGui import QIcon, QFont, QColor, QTextListFormat, QKeyEvent,QAction
from PyQt6.QtCore import Qt, QEvent

class TextEditor(QMainWindow):
    def __init__(self):
        super().__init__()

        self.editor = QTextEdit()
        self.setCentralWidget(self.editor)
        self.editor.installEventFilter(self)

        self.create_toolbar()

    def create_toolbar(self):
        toolbar = QToolBar("Edit")
        self.addToolBar(toolbar)

        # Font Family ComboBox
        self.font_family_combobox = QFontComboBox()
        self.font_family_combobox.currentFontChanged.connect(self.font_family_changed)
        toolbar.addWidget(self.font_family_combobox)

        # Font Size ComboBox
        self.font_size_combobox = QComboBox()
        self.font_size_combobox.addItems(['8', '9', '10', '11', '12', '14', '16', '18', '20', '22', '24', '26', '28', '36', '48', '72'])
        self.font_size_combobox.setEditable(True)
        self.font_size_combobox.currentTextChanged.connect(self.font_size_changed)
        toolbar.addWidget(self.font_size_combobox)

        # Bold, Italic, Underline, etc. Actions
        bold_action = QAction(QIcon("icons/bold.png"), "Bold", self)
        bold_action.triggered.connect(self.bold_text)
        toolbar.addAction(bold_action)

        italic_action = QAction(QIcon("icons/italic.png"), "Italic", self)
        italic_action.triggered.connect(self.italic_text)
        toolbar.addAction(italic_action)

        underline_action = QAction(QIcon("icons/underline.png"), "Underline", self)
        underline_action.triggered.connect(self.underline_text)
        toolbar.addAction(underline_action)

        font_color_action = QAction(QIcon("icons/font_color.png"), "Font Color", self)
        font_color_action.triggered.connect(self.font_color)
        toolbar.addAction(font_color_action)

        # Alignment Actions
        align_left_action = QAction(QIcon("icons/align_left.png"), "Align Left", self)
        align_left_action.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignLeft))
        toolbar.addAction(align_left_action)

        align_center_action = QAction(QIcon("icons/align_center.png"), "Align Center", self)
        align_center_action.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignCenter))
        toolbar.addAction(align_center_action)

        align_right_action = QAction(QIcon("icons/align_right.png"), "Align Right", self)
        align_right_action.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignRight))
        toolbar.addAction(align_right_action)

        # Bullet List Action
        bullet_action = QAction(QIcon("icons/bullet.png"), "Bullet List", self)
        bullet_action.triggered.connect(self.bullet_list)
        toolbar.addAction(bullet_action)

        # Indentation Actions
        increase_indent_action = QAction(QIcon("icons/increase_indent.png"), "Increase Indent", self)
        increase_indent_action.triggered.connect(self.increase_indent)
        toolbar.addAction(increase_indent_action)

        decrease_indent_action = QAction(QIcon("icons/decrease_indent.png"), "Decrease Indent", self)
        decrease_indent_action.triggered.connect(self.decrease_indent)
        toolbar.addAction(decrease_indent_action)

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

    def font_color(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.editor.setTextColor(color)

    def bullet_list(self):
        cursor = self.editor.textCursor()
        list_format = QTextListFormat()
        if cursor.currentList():
            list_format = cursor.currentList().format()
        else:
            list_format.setStyle(QTextListFormat.Style.ListDisc)
        cursor.createList(list_format)

    def increase_indent(self):
        self.adjust_indent(1)

    def decrease_indent(self):
        self.adjust_indent(-1)

    def adjust_indent(self, adjustment):
        cursor = self.editor.textCursor()
        if cursor.currentList():
            list_format = cursor.currentList().format()
            list_format.setIndent(list_format.indent() + adjustment)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = TextEditor()
    editor.show()
    sys.exit(app.exec())
