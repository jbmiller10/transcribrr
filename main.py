import sys
from PyQt5.QtWidgets import QApplication, QStyleFactory
from MainWindow import MainWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    mainWin = MainWindow()
    mainWin.show()
    sys.exit(app.exec_())