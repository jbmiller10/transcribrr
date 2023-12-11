import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QTextEdit, QToolBar, QColorDialog, QFontDialog, QFontComboBox, QComboBox
from PyQt6.QtGui import QIcon, QFont, QColor, QTextListFormat, QKeyEvent,QAction,QActionGroup
from PyQt6.QtCore import Qt, QEvent
import markdown2

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

        # Bold, Italic, Underline Actions
        bold_action = QAction(QIcon("../icons/TextEditor/bold.svg"), "Bold", self)
        bold_action.setCheckable(True)  # Make the action toggleable
        bold_action.setShortcut("Ctrl+B")
        bold_action.triggered.connect(self.bold_text)
        toolbar.addAction(bold_action)

        italic_action = QAction(QIcon("../icons/TextEditor/italic.svg"), "Italic", self)
        italic_action.setCheckable(True)  # Make the action toggleable
        italic_action.setShortcut("Ctrl+I")
        italic_action.triggered.connect(self.italic_text)
        toolbar.addAction(italic_action)

        underline_action = QAction(QIcon("../icons/TextEditor/underline.svg"), "Underline", self)
        underline_action.setCheckable(True)  # Make the action toggleable
        underline_action.setShortcut("Ctrl+U")
        underline_action.triggered.connect(self.underline_text)
        toolbar.addAction(underline_action)

        font_color_action = QAction(QIcon("../icons/TextEditor/font_color.svg"), "Font Color", self)
        font_color_action.triggered.connect(self.font_color)
        toolbar.addAction(font_color_action)

        alignment_group = QActionGroup(self)

        # Alignment Actions
        align_left_action = QAction(QIcon("../icons/TextEditor/align_left.svg"), "Align Left", self)
        align_left_action.setCheckable(True)
        align_left_action.setShortcut("Ctrl+L")
        align_left_action.triggered.connect(lambda: self.set_alignment(Qt.AlignmentFlag.AlignLeft))
        toolbar.addAction(align_left_action)
        alignment_group.addAction(align_left_action)

        align_center_action = QAction(QIcon("../icons/TextEditor/align_center.svg"), "Align Center", self)
        align_center_action.setCheckable(True)
        align_center_action.setShortcut("Ctrl+E")
        align_center_action.triggered.connect(lambda: self.set_alignment(Qt.AlignmentFlag.AlignCenter))
        toolbar.addAction(align_center_action)
        alignment_group.addAction(align_center_action)

        align_right_action = QAction(QIcon("../icons/TextEditor/align_right.svg"), "Align Right", self)
        align_right_action.setCheckable(True)
        align_right_action.setShortcut("Ctrl+R")
        align_right_action.triggered.connect(lambda: self.set_alignment(Qt.AlignmentFlag.AlignRight))
        toolbar.addAction(align_right_action)
        alignment_group.addAction(align_right_action)

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
        self.editor.setFocus()

    def italic_text(self):
        font = self.editor.currentFont()
        font.setItalic(not font.italic())
        self.editor.setCurrentFont(font)
        self.editor.setFocus()

    def underline_text(self):
        font = self.editor.currentFont()
        font.setUnderline(not font.underline())
        self.editor.setCurrentFont(font)
        self.editor.setFocus()

    def set_alignment(self, alignment):
        self.editor.setAlignment(alignment)
        self.editor.setFocus()

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

    def insert_html(self, html_text):
        #Inserts HTML formatted text into the editor.
        self.editor.insertHtml(html_text)

    def insert_markdown(self, markdown_text):
        html_text = markdown2.markdown(markdown_text)
        self.editor.setHtml(html_text)

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
    editor.insert_html('''<h1>Exploring the Ingenuity of the Nintendo Zapper with High-Speed Camera Technology</h1>

<p>In an age of advanced gaming technology, it's fascinating to look back at how earlier innovations paved the way for today's entertainment experiences. A prime example is the Nintendo Zapper, a groundbreaking accessory from the era of the NES (Nintendo Entertainment System). Let’s dive into the mechanics behind this iconic piece of gaming history using high-speed cameras, or "slomo," to uncover its intricacies.</p>

<h2>The Nintendo Zapper's Functionality</h2>

<p>Many of us fondly remember the simple yet captivating light gun known as the Nintendo Zapper, which was made famous by games like "Duck Hunt." Unlike modern peripherals requiring complex setups, the Zapper could precisely detect where it was aimed on the screen using only the gun itself, a marvel of its time.</p>

<h2>The Science of the Screen</h2>

<p>Understanding how the Zapper interacts with the television requires a bit of a technical dive into TV operations. Televisions of that era used cathode-ray tube (CRT) displays, which drew images line by line from top to bottom. With the help of slow-motion footage, we can observe that lines travel across the screen from left to right at incredible speeds. In terms of numbers, this equates to around 24,500 miles per hour—quick enough to circle the Earth in one hour!</p>

<h2>Persistence of Vision</h2>

<p>At standard viewing speeds, the human eye perceives a continuous image on the screen due to what is known as persistence of vision. However, when filmed at high speeds, one can see only the individual lines as they are drawn. By artificially extending the trails of each frame, it becomes clearer which frame is currently being drawn.</p>

<h2>How the Zapper Detects Targets</h2>

<p>When the Zapper's trigger is pulled, a signal is sent to the console. The key to its operation lies in a focused light sensor at the back of the gun. If the Zapper is pointed at a target, like a duck in “Duck Hunt,” the console will send a black frame to the TV, essentially clearing the screen, followed by a frame that draws a white box over where the duck's sprite was. If the Zapper detects the white box, it registers a hit.</p>

<h2>In-Game Action and Reaction</h2>

<p>A successful shot results in several quick changes on the screen: the sprite disappears, the background is redrawn, the score updates, and then the duck is shown as being hit. This process is so rapid that it's virtually imperceptible to the naked eye. In a two-duck mode, the game cleverly draws the boxes for each duck on separate frames, ensuring accurate detection by the light sensor.</p>

<h2>Preventing Cheating</h2>

<p>An impressive aspect of the Zapper’s design is its cheat-proofing measure. The sequence of a black frame followed by a white box prevents players from simply pointing the gun at a bright light source to score points. The sensor must see the sequence of dark followed by light to register a successful hit.</p>

<h2>Menu Navigation with Zapper</h2>

<p>The Zapper was even utilized for menu navigation. By using the same detection methodology, players could select menu items without a need for additional buttons or peripherals. An entire screen flash would change the menu selection, and detecting the flash would confirm the choice.</p>

<h2>The Legacy of the Nintendo Zapper</h2>

<p>The Nintendo Zapper stands as a testament to ingenious engineering. Its compatibility with nearly every television of its time without extensive setup is a remarkable feat that continues to inspire awe. Despite being developed over 40 years ago, the Zapper demonstrates the potential for simple, effective technology – a precursor to the complex gaming systems we enjoy today.</p>

<h3>Conclusion and Invitation for Discussion</h3>

<p>The elegant design of the Zapper invites us to appreciate the wonder of technology. Discovering other electronics that function in unique ways can offer us further insight into the genius of past inventions. Let's continue to explore these marvels, like the Nintendo Zapper, and keep the conversation about historical tech innovations going. For those who share this fascination, make sure to join the journey by subscribing for more explorations into the world of "slomo" technology.</p>''')
    sys.exit(app.exec())
