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
        bold_action = QAction(QIcon("../icons/TextEditor/bold.svg"), "Bold", self)
        bold_action.setShortcut("Ctrl+B")
        bold_action.triggered.connect(self.bold_text)
        toolbar.addAction(bold_action)

        italic_action = QAction(QIcon("../icons/TextEditor/italic.svg"), "Italic", self)
        italic_action.setShortcut("Ctrl+I")
        italic_action.triggered.connect(self.italic_text)
        toolbar.addAction(italic_action)

        underline_action = QAction(QIcon("../icons/TextEditor/underline.svg"), "Underline", self)
        underline_action.setShortcut("Ctrl+U")
        underline_action.triggered.connect(self.underline_text)
        toolbar.addAction(underline_action)

        font_color_action = QAction(QIcon("../icons/TextEditor/font_color.svg"), "Font Color", self)
        font_color_action.triggered.connect(self.font_color)
        toolbar.addAction(font_color_action)

        # Alignment Actions
        align_left_action = QAction(QIcon("../icons/TextEditor/align_left.svg"), "Align Left", self)
        align_left_action.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignLeft))
        align_left_action.setShortcut("Ctrl+L")
        toolbar.addAction(align_left_action)

        align_center_action = QAction(QIcon("../icons/TextEditor/align_center.svg"), "Align Center", self)
        align_center_action.setShortcut("Ctrl+E")
        align_center_action.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignCenter))

        toolbar.addAction(align_center_action)

        align_right_action = QAction(QIcon("../icons/TextEditor/align_right.svg"), "Align Right", self)
        align_right_action.setShortcut("Ctrl+R")
        align_right_action.triggered.connect(lambda: self.editor.setAlignment(Qt.AlignmentFlag.AlignRight))
        toolbar.addAction(align_right_action)

        # Bullet List Action
        bullet_action = QAction(QIcon("../icons/TextEditor/bullet.svg"), "Bullet List", self)
        bullet_action.triggered.connect(self.bullet_list)
        toolbar.addAction(bullet_action)

        # Numbered List Action
        numbered_action = QAction(QIcon("../icons/TextEditor/numbered.svg"), "Numbered List", self)
        numbered_action.triggered.connect(self.numbered_list)
        toolbar.addAction(numbered_action)

        # Indentation Actions
        increase_indent_action = QAction(QIcon("../icons/TextEditor/increase_indent.svg"), "Increase Indent", self)
        increase_indent_action.triggered.connect(self.increase_indent)
        toolbar.addAction(increase_indent_action)

        decrease_indent_action = QAction(QIcon("../icons/TextEditor/decrease_indent.svg"), "Decrease Indent", self)
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

    def numbered_list(self):
        cursor = self.editor.textCursor()
        list_format = QTextListFormat()
        if cursor.currentList():
            list_format = cursor.currentList().format()
        else:
            list_format.setStyle(QTextListFormat.Style.ListDecimal)
        cursor.createList(list_format)

    def bullet_list(self):
        cursor = self.editor.textCursor()
        list_format = QTextListFormat()
        if cursor.currentList():
            list_format = cursor.currentList().format()
        else:
            list_format.setStyle(QTextListFormat.Style.ListDisc)
        cursor.createList(list_format)


    def decrease_indent(self):
        cursor = self.editor.textCursor()
        if cursor.currentList():
            list_format = cursor.currentList().format()
            new_indent_level = max(list_format.indent() - 1, 1)  # Avoid negative or zero indentation
            list_format.setIndent(new_indent_level)
            cursor.createList(list_format)
    def increase_indent(self):
        cursor = self.editor.textCursor()
        if cursor.currentList():
            list_format = cursor.currentList().format()
            new_indent_level = list_format.indent() + 1
            list_format.setIndent(new_indent_level)
            cursor.createList(list_format)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    editor = TextEditor()
    editor.show()
    sys.exit(app.exec())
