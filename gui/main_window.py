from dataclasses import replace

from PyQt5.QtWidgets import QApplication, QMessageBox
from qfluentwidgets import (
    FluentIcon,
    FluentWindow,
    NavigationItemPosition,
)

from .editor_page import EditorPage
from .settings_page import SettingsPage
from .workspace_page import WorkspacePage


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
        self.workspace.openDocument.connect(self._open_document)
        self.settings.editorFontChanged.connect(self.editor._apply_theme)

        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            self.move(g.x() + (g.width() - self.width()) // 2,
                      g.y() + (g.height() - self.height()) // 2)

    def _open_document(self, request):
        if not self._confirm_discard_changes():
            return
        from .settings_page import Settings
        cfg = Settings.load()
        if (cfg.default_encoding != 'auto'
                and request.target_encoding == 'auto'):
            request = replace(request, target_encoding=cfg.default_encoding)
        try:
            self.editor.open_document(request)
        except Exception as exc:  # noqa: BLE001 - GUI error boundary
            QMessageBox.critical(self, '打开文档失败', str(exc))
            return
        if request.switch_to_editor:
            self.switchTo(self.editor)

    def _confirm_discard_changes(self) -> bool:
        if not self.editor.is_modified:
            return True
        answer = QMessageBox.question(
            self, '未保存修改', '当前文档有未保存修改，是否先保存？',
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            if self.editor.can_save:
                self.editor._save()
            else:
                self.editor._save_as()
            return not self.editor.is_modified
        return True

    def closeEvent(self, event):
        if not self._confirm_discard_changes():
            event.ignore()
            return
        if not self.workspace.shutdown():
            QMessageBox.information(
                self, '后台任务仍在结束', '请稍后再次关闭窗口。')
            event.ignore()
            return
        event.accept()
