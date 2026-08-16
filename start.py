import sys


def main():
    from PyQt5.QtCore import QLibraryInfo, Qt, QTranslator
    from PyQt5.QtGui import QFont
    from PyQt5.QtWidgets import QApplication
    from qfluentwidgets import Theme, setTheme

    from gui.main_window import MainWindow

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

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
