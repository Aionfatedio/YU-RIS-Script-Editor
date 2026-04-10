import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt5.QtCore import Qt, QLocale, QTranslator, QLibraryInfo
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from qfluentwidgets import setTheme, Theme

from gui.main_window import MainWindow

QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

def main():
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei UI", 11))

    translator = QTranslator()
    trans_path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
    if translator.load("qt_zh_CN", trans_path):
        app.installTranslator(translator)

    setTheme(Theme.AUTO)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
