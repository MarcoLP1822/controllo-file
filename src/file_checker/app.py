# src/file_checker/app.py
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
import sys

from file_checker.gui.main_window import FileCheckerMainWindow

def main() -> None:
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = FileCheckerApp()
    window.show()
    sys.exit(app.exec_())
