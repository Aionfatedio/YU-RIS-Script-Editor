from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from qfluentwidgets import (
    FluentWindow, FluentIcon, NavigationItemPosition,
    setTheme, Theme
)
from .workspace_page import WorkspacePage
from .editor_page import EditorPage
from .settings_page import SettingsPage


class MainWindow(FluentWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("YU-RIS Script Editor")
        self.setMinimumSize(900, 640)
        self.resize(1060, 740)

        self.workspace = WorkspacePage(self)
        self.editor = EditorPage(self)
        self.settings = SettingsPage(self)

        self.addSubInterface(
            self.workspace, FluentIcon.HOME, "工作台")
        self.addSubInterface(
            self.editor, FluentIcon.EDIT, "编辑器")
        self.addSubInterface(
            self.settings, FluentIcon.SETTING, "设置",
            NavigationItemPosition.BOTTOM)

        self.navigationInterface.setReturnButtonVisible(False)
        self.workspace.openInEditor.connect(self._open_in_editor)
        self.settings.editorFontChanged.connect(self.editor._apply_theme)

        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.move((g.width() - self.width()) // 2,
                      (g.height() - self.height()) // 2)

    def _open_in_editor(self, path: str, key: int, encoding: str,
                        switch: bool = True):
        from .settings_page import Settings
        cfg = Settings.load()
        if cfg.default_encoding != 'auto':
            encoding = cfg.default_encoding
        key = key & 0xFFFFFFFF
        ctx = self.workspace._ypf_save_context
        self.editor.set_ypf_context(ctx)
        self.editor.load_file(path, key, encoding)

        if switch:
            self.switchTo(self.editor)
