from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QShortcut,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    ComboBox,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    PushButton,
    SmoothScrollDelegate,
    isDarkTheme,
)

from application.documents import (
    DocumentRequest,
    DocumentSession,
    ScriptDocument,
)
from core.encoding import Encoding

from .theme import theme_colors

_ENCODINGS = [
    ('SHIFT_JIS', Encoding.SJIS),
    ('GBK', Encoding.GBK),
    ('UTF-8', Encoding.UTF8),
    ('BIG5', Encoding.BIG5),
]


class SearchBar(QWidget):
    def __init__(self, editor: QPlainTextEdit, parent=None):
        super().__init__(parent)
        self._editor = editor
        self._build_ui()
        self.hide()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(4)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('搜索 (Ctrl+F)')
        self.search_input.textChanged.connect(self._search_changed)
        self.search_input.returnPressed.connect(self.find_next)
        search_row.addWidget(self.search_input, 1)

        self.match_label = CaptionLabel('')
        self.match_label.setFixedWidth(70)
        self.match_label.setAlignment(Qt.AlignCenter)
        search_row.addWidget(self.match_label)

        previous = PushButton('↑')
        previous.clicked.connect(self.find_previous)
        search_row.addWidget(previous)
        following = PushButton('↓')
        following.clicked.connect(self.find_next)
        search_row.addWidget(following)
        close = PushButton('关闭')
        close.clicked.connect(self.close_bar)
        search_row.addWidget(close)
        layout.addLayout(search_row)

        replace_row = QHBoxLayout()
        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText('替换')
        replace_row.addWidget(self.replace_input, 1)
        replace_one = PushButton('替换')
        replace_one.clicked.connect(self.replace_current)
        replace_row.addWidget(replace_one)
        replace_all = PushButton('全部替换')
        replace_all.clicked.connect(self.replace_all)
        replace_row.addWidget(replace_all)
        layout.addLayout(replace_row)

    def open_bar(self):
        self.show()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def close_bar(self):
        self.hide()
        self.reset()
        self._editor.setFocus()

    def reset(self):
        self._editor.setExtraSelections([])
        self.match_label.clear()

    def _search_changed(self, text: str):
        if not text:
            self.reset()
            return
        cursor = self._editor.document().find(
            text, QTextCursor(self._editor.document()))
        if cursor.isNull():
            self.match_label.setText('无匹配')
            self._editor.setExtraSelections([])
            return
        self._select(cursor, text)

    def find_next(self):
        text = self.search_input.text()
        if not text:
            return
        document = self._editor.document()
        cursor = document.find(text, self._editor.textCursor())
        if cursor.isNull():
            cursor = document.find(text, QTextCursor(document))
        if cursor.isNull():
            self.match_label.setText('无匹配')
            return
        self._select(cursor, text)

    def find_previous(self):
        text = self.search_input.text()
        if not text:
            return
        document = self._editor.document()
        anchor = QTextCursor(document)
        anchor.setPosition(self._editor.textCursor().selectionStart())
        cursor = document.find(text, anchor, QTextDocument.FindBackward)
        if cursor.isNull():
            anchor.movePosition(QTextCursor.End)
            cursor = document.find(text, anchor, QTextDocument.FindBackward)
        if cursor.isNull():
            self.match_label.setText('无匹配')
            return
        self._select(cursor, text)

    def _select(self, cursor: QTextCursor, text: str):
        self._editor.setTextCursor(cursor)
        self._editor.centerCursor()
        self._refresh_highlights(text)

    def replace_current(self):
        query = self.search_input.text()
        if not query:
            return
        cursor = self._editor.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == query:
            cursor.insertText(self.replace_input.text())
        self.find_next()

    def replace_all(self):
        query = self.search_input.text()
        if not query:
            return
        document = self._editor.document()
        cursor = QTextCursor(document)
        cursor.beginEditBlock()
        count = 0
        while True:
            cursor = document.find(query, cursor)
            if cursor.isNull():
                break
            cursor.insertText(self.replace_input.text())
            count += 1
        cursor.endEditBlock()
        self._refresh_highlights(query)
        if count:
            InfoBar.success(
                '替换完成', f'已替换 {count} 处', parent=self.window(),
                duration=2000, position=InfoBarPosition.TOP)

    def _refresh_highlights(self, text: str):
        document = self._editor.document()
        active_start = self._editor.textCursor().selectionStart()
        normal = QTextCharFormat()
        normal.setBackground(QColor(255, 210, 0, 80))
        active = QTextCharFormat()
        active.setBackground(QColor(0, 120, 212, 120))

        selections = []
        cursor = QTextCursor(document)
        total = 0
        current = 0
        while True:
            cursor = document.find(text, cursor)
            if cursor.isNull():
                break
            total += 1
            is_active = cursor.selectionStart() == active_start
            if is_active:
                current = total
            selection = QTextEdit.ExtraSelection()
            selection.cursor = QTextCursor(cursor)
            selection.format = active if is_active else normal
            selections.append(selection)
        self._editor.setExtraSelections(selections)
        self.match_label.setText(
            f'{current}/{total}' if total else '无匹配')

    def apply_theme(self, dark: bool):
        colors = theme_colors(dark)
        self.setStyleSheet(
            f'SearchBar {{ background: {colors.editor_background}; '
            f'border-bottom: 1px solid {colors.border}; }}')
        input_style = (
            f'QLineEdit {{ background: {colors.editor_background}; '
            f'color: {colors.editor_foreground}; border: 1px solid '
            f'{colors.border}; border-radius: 4px; padding: 4px 8px; }}'
            'QLineEdit:focus { border-color: #0078D4; }')
        self.search_input.setStyleSheet(input_style)
        self.replace_input.setStyleSheet(input_style)


class EditorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('editorPage')
        self._session: DocumentSession | None = None
        self._loading = False
        self._build_ui()
        self._set_enabled(False)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QWidget()
        toolbar.setFixedHeight(44)
        bar = QHBoxLayout(toolbar)
        bar.setContentsMargins(20, 4, 20, 4)
        bar.setSpacing(10)
        self.file_label = BodyLabel('未加载文件')
        bar.addWidget(self.file_label)
        bar.addStretch()

        bar.addWidget(BodyLabel('编码:'))
        self.encoding_combo = ComboBox()
        self.encoding_combo.addItems([item[0] for item in _ENCODINGS])
        self.encoding_combo.setMaximumWidth(120)
        self.encoding_combo.currentIndexChanged.connect(
            self._encoding_changed)
        bar.addWidget(self.encoding_combo)

        self.btn_save = PrimaryPushButton(FluentIcon.SAVE, '保存')
        self.btn_save.clicked.connect(self._save)
        bar.addWidget(self.btn_save)
        self.btn_save_as = PushButton(FluentIcon.SAVE_AS, '另存为')
        self.btn_save_as.clicked.connect(self._save_as)
        bar.addWidget(self.btn_save_as)
        root.addWidget(toolbar)

        self.editor = QPlainTextEdit()
        self.editor.setTabStopDistance(32)
        self.editor.textChanged.connect(self._text_changed)
        self.editor.cursorPositionChanged.connect(self._update_line_info)
        SmoothScrollDelegate(self.editor)
        self.search_bar = SearchBar(self.editor, self)
        root.addWidget(self.search_bar)
        root.addWidget(self.editor, 1)

        status_bar = QWidget()
        status_bar.setFixedHeight(26)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(20, 0, 20, 0)
        self.status = CaptionLabel('就绪')
        status_layout.addWidget(self.status)
        status_layout.addStretch()
        self.line_info = CaptionLabel('')
        status_layout.addWidget(self.line_info)
        root.addWidget(status_bar)

        QShortcut(QKeySequence('Ctrl+F'), self, self.search_bar.open_bar)
        QShortcut(QKeySequence('Ctrl+S'), self, self._save)
        self._apply_theme()

    def open_document(self, request: DocumentRequest):
        self._session = DocumentSession(request)
        self._refresh_document()
        self.search_bar.reset()

    def load_file(self, path: str, key: int, encoding: str):
        self.open_document(DocumentRequest(
            display_name=Path(path).name, kind='ystb',
            source_path=Path(path), key=key,
            source_encoding=encoding, target_encoding=encoding))

    def load_txt_file(self, path: str):
        self.open_document(DocumentRequest(
            display_name=Path(path).name, kind='text',
            source_path=Path(path)))

    def _refresh_document(self):
        session = self._session
        if session is None:
            self._set_enabled(False)
            return
        document = session.document
        self._set_enabled(True)
        self._set_encoding(document.target_encoding)
        self.btn_save.setEnabled(session.can_save)
        self.btn_save.setToolTip(
            '' if session.can_save else '资源型 YPF 只支持另存为')

        self._loading = True
        if isinstance(document, ScriptDocument):
            lines = [
                ('[OPT] ' if entry.is_option else '')
                + self._escape_entry(entry.text)
                for entry in document.entries
            ]
            self.editor.setPlainText('\n'.join(lines))
            self.editor.setReadOnly(not document.entries)
            self.editor.setPlaceholderText(
                '该脚本没有可编辑文本' if not document.entries else '')
        else:
            self.editor.setReadOnly(False)
            self.editor.setPlaceholderText('')
            self.editor.setPlainText(document.text)
        self.editor.moveCursor(QTextCursor.Start)
        self.editor.document().setModified(False)
        self._loading = False

        source = 'YPF' if session.archive else '文件'
        writable = '' if session.can_save else ' [只读]'
        self.file_label.setText(f'{session.display_name}  [{source}]{writable}')
        self._apply_theme()
        self._update_status('已加载')

    @staticmethod
    def _escape_entry(text: str) -> str:
        return text.replace('\\', '\\\\').replace('\r', '\\r').replace('\n', '\\n')

    @staticmethod
    def _unescape_entry(text: str) -> str:
        result = []
        index = 0
        while index < len(text):
            char = text[index]
            if char != '\\' or index + 1 >= len(text):
                result.append(char)
                index += 1
                continue
            following = text[index + 1]
            if following == 'n':
                result.append('\n')
            elif following == 'r':
                result.append('\r')
            elif following == '\\':
                result.append('\\')
            else:
                result.extend(('\\', following))
            index += 2
        return ''.join(result)

    def _sync_editor(self, show_error: bool = False) -> bool:
        if not self._session:
            return False
        document = self._session.document
        if not isinstance(document, ScriptDocument):
            document.set_text(self.editor.toPlainText())
            return True

        lines = self.editor.toPlainText().split('\n')
        if not document.entries and lines == ['']:
            lines = []
        if len(lines) != len(document.entries):
            self.status.setText(
                f'文本行数已改变：当前 {len(lines)} 行，原脚本 '
                f'{len(document.entries)} 条')
            if show_error:
                InfoBar.error(
                    '脚本结构不匹配', '请撤销新增或删除的整行后再保存',
                    parent=self.window(), duration=5000,
                    position=InfoBarPosition.TOP)
            return False

        for entry, line in zip(document.entries, lines):
            if entry.is_option and line.startswith('[OPT] '):
                line = line[6:]
            document.set_text(entry.index, self._unescape_entry(line))
        return True

    def _text_changed(self):
        if not self._loading:
            self._update_status()

    def _encoding_changed(self, index: int):
        if self._loading or not self._session or index < 0:
            return
        self._session.document.set_target_encoding(_ENCODINGS[index][1])
        self._update_status()

    def _set_encoding(self, encoding: str):
        index = next((
            i for i, (_, value) in enumerate(_ENCODINGS)
            if value == encoding
        ), 0)
        self.encoding_combo.blockSignals(True)
        self.encoding_combo.setCurrentIndex(index)
        self.encoding_combo.blockSignals(False)

    def _save(self):
        if not self._session or not self._session.can_save:
            return
        if not self._sync_editor(show_error=True):
            return
        try:
            from .settings_page import Settings
            result = self._session.save(backup=Settings.load().auto_backup)
            self._refresh_document()
            message = (
                f'已更新 {Path(result.target).name}'
                if result.archive_updated
                else f'已保存 {Path(result.target).name}'
            )
            self.status.setText(f'{message} ({result.changed_count} 条)')
            InfoBar.success(
                '已保存', message, parent=self.window(), duration=3000,
                position=InfoBarPosition.TOP)
        except Exception as exc:  # noqa: BLE001 - GUI error boundary
            self._show_error('保存失败', exc)

    def _save_as(self):
        if not self._session or not self._sync_editor(show_error=True):
            return
        file_filter = (
            'YBN (*.ybn);;所有文件 (*)'
            if self._session.kind == 'ystb'
            else 'TXT (*.txt);;所有文件 (*)'
        )
        path, _ = QFileDialog.getSaveFileName(
            self, '另存为', self._session.display_name, file_filter)
        if not path:
            return
        try:
            from .settings_page import Settings
            result = self._session.save_as(
                path, backup=Settings.load().auto_backup)
            self._refresh_document()
            InfoBar.success(
                '另存为完成', result.target, parent=self.window(),
                duration=3000, position=InfoBarPosition.TOP)
        except Exception as exc:  # noqa: BLE001 - GUI error boundary
            self._show_error('另存为失败', exc)

    def _set_enabled(self, enabled: bool):
        self.editor.setEnabled(enabled)
        self.encoding_combo.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)
        self.btn_save_as.setEnabled(enabled)
        if not enabled:
            self._loading = True
            self.editor.clear()
            self.editor.document().setModified(False)
            self._loading = False
            self.file_label.setText('未加载文件')
            self.status.setText('工作台载入后启用')
            self.line_info.clear()

    def _update_status(self, clean_message: str | None = None):
        if not self._session:
            return
        if self.is_modified:
            self.status.setText('已修改（未保存）')
        elif clean_message:
            self.status.setText(clean_message)
        else:
            self.status.setText('已保存')
        self._update_line_info()

    def _update_line_info(self):
        if not self._session:
            self.line_info.clear()
            return
        line = self.editor.textCursor().blockNumber() + 1
        if isinstance(self._session.document, ScriptDocument):
            total = len(self._session.document.entries)
            self.line_info.setText(f'第 {line} 行 | 共 {total} 条文本')
        else:
            total = self.editor.document().blockCount()
            self.line_info.setText(f'第 {line} 行 | 共 {total} 行')

    @property
    def is_modified(self) -> bool:
        return bool(
            self.editor.document().isModified()
            or (self._session and self._session.modified)
        )

    @property
    def can_save(self) -> bool:
        return bool(self._session and self._session.can_save)

    def _apply_theme(self):
        colors = theme_colors(isDarkTheme())
        from .settings_page import Settings
        settings = Settings.load()
        family = settings.editor_font_family or 'Consolas'
        self.editor.setFont(QFont(family, settings.editor_font_size))
        self.editor.setStyleSheet(
            f'QPlainTextEdit {{ background: {colors.editor_background}; '
            f'color: {colors.editor_foreground}; border: none; '
            f'padding: 12px 16px; }}')
        self.file_label.setStyleSheet(
            f'color: {colors.primary}; font-weight: 500;')
        self.search_bar.apply_theme(isDarkTheme())

    def _show_error(self, title: str, error: Exception):
        InfoBar.error(
            title, str(error), parent=self.window(), duration=6000,
            position=InfoBarPosition.TOP)
