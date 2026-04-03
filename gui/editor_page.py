import shutil
from pathlib import Path
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QTextCharFormat, QTextCursor, QTextDocument, QKeySequence
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QTextEdit,
    QFileDialog, QSizePolicy, QShortcut, QLineEdit
)
from qfluentwidgets import (
    BodyLabel, CaptionLabel,
    PushButton, PrimaryPushButton, ComboBox,
    FluentIcon, InfoBar, InfoBarPosition,
    isDarkTheme, SmoothScrollDelegate
)

class SearchBar(QWidget):
    def __init__(self, editor: QPlainTextEdit, parent=None):
        super().__init__(parent)
        self._editor = editor
        self._build_ui()
        self.hide()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(4)

        sr = QHBoxLayout()
        sr.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索 (Ctrl+F)")
        self.search_input.textChanged.connect(self._on_search_changed)
        self.search_input.returnPressed.connect(self.find_next)
        sr.addWidget(self.search_input, 1)

        self.match_label = CaptionLabel("")
        self.match_label.setFixedWidth(70)
        self.match_label.setAlignment(Qt.AlignCenter)
        sr.addWidget(self.match_label)

        self.btn_prev = PushButton("↑")
        self.btn_prev.setFixedHeight(30)
        self.btn_prev.clicked.connect(self.find_prev)
        sr.addWidget(self.btn_prev)

        self.btn_next = PushButton("↓")
        self.btn_next.setFixedHeight(30)
        self.btn_next.clicked.connect(self.find_next)
        sr.addWidget(self.btn_next)

        self.btn_close = PushButton("关闭")
        self.btn_close.setFixedHeight(30)
        self.btn_close.clicked.connect(self.close_bar)
        sr.addWidget(self.btn_close)

        lay.addLayout(sr)

        # --- 替换行 ---
        rr = QHBoxLayout()
        rr.setSpacing(6)

        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("替换")
        rr.addWidget(self.replace_input, 1)

        btn_rep = PushButton("替换")
        btn_rep.setFixedHeight(30)
        btn_rep.clicked.connect(self._replace_one)
        rr.addWidget(btn_rep)

        btn_all = PushButton("全部替换")
        btn_all.setFixedHeight(30)
        btn_all.clicked.connect(self._replace_all)
        rr.addWidget(btn_all)

        lay.addLayout(rr)

    def open_bar(self):
        self.show()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def close_bar(self):
        self.hide()
        self._editor.setExtraSelections([])
        self._editor.setFocus()

    def on_file_changed(self):
        self._editor.setExtraSelections([])
        if self.search_input.text():
            self.match_label.setText("-/-")

    def _count_matches(self, text):
        if not text:
            return 0
        doc = self._editor.document()
        cursor = QTextCursor(doc)
        count = 0
        while True:
            cursor = doc.find(text, cursor)
            if cursor.isNull():
                break
            count += 1
        return count

    def _on_search_changed(self, text):
        if not text:
            self.match_label.setText("")
            self._editor.setExtraSelections([])
            return
        doc = self._editor.document()
        cursor = doc.find(text, QTextCursor(doc))
        if cursor.isNull():
            self.match_label.setText("无匹配")
            self._editor.setExtraSelections([])
            return
        self._editor.setTextCursor(cursor)
        self._editor.centerCursor()
        self._refresh_highlights_and_label(text)

    def find_next(self):
        text = self.search_input.text()
        if not text:
            return
        doc = self._editor.document()
        cursor = doc.find(text, self._editor.textCursor())
        if cursor.isNull():
            cursor = doc.find(text, QTextCursor(doc))
        if cursor.isNull():
            self.match_label.setText("无匹配")
            return
        self._editor.setTextCursor(cursor)
        self._editor.centerCursor()
        self._refresh_highlights_and_label(text)

    def find_prev(self):
        text = self.search_input.text()
        if not text:
            return
        doc = self._editor.document()
        cur = self._editor.textCursor()
        anchor = QTextCursor(doc)
        anchor.setPosition(cur.selectionStart())
        cursor = doc.find(text, anchor, QTextDocument.FindBackward)
        if cursor.isNull():
            end_cursor = QTextCursor(doc)
            end_cursor.movePosition(QTextCursor.End)
            cursor = doc.find(text, end_cursor, QTextDocument.FindBackward)
        if cursor.isNull():
            self.match_label.setText("无匹配")
            return
        self._editor.setTextCursor(cursor)
        self._editor.centerCursor()
        self._refresh_highlights_and_label(text)

    def _refresh_highlights_and_label(self, text):
        doc = self._editor.document()
        cur_start = self._editor.textCursor().selectionStart()

        sels = []
        fmt_normal = QTextCharFormat()
        fmt_normal.setBackground(QColor(255, 210, 0, 80))
        fmt_active = QTextCharFormat()
        fmt_active.setBackground(QColor(0, 120, 212, 120))

        cursor = QTextCursor(doc)
        total = 0
        current_idx = 0
        while True:
            cursor = doc.find(text, cursor)
            if cursor.isNull():
                break
            total += 1
            is_active = (cursor.selectionStart() == cur_start)
            if is_active:
                current_idx = total

            sel = QTextEdit.ExtraSelection()
            sel.format = fmt_active if is_active else fmt_normal
            sel.cursor = QTextCursor(cursor)
            sels.append(sel)

        self._editor.setExtraSelections(sels)
        if total > 0:
            self.match_label.setText(f"{current_idx}/{total}")
        else:
            self.match_label.setText("无匹配")

    def _replace_one(self):
        text = self.search_input.text()
        if not text:
            return
        cur = self._editor.textCursor()
        if cur.hasSelection() and cur.selectedText() == text:
            cur.insertText(self.replace_input.text())
        self.find_next()

    def _replace_all(self):
        text = self.search_input.text()
        repl = self.replace_input.text()
        if not text:
            return
        doc = self._editor.document()
        cursor = QTextCursor(doc)
        cursor.beginEditBlock()
        count = 0
        while True:
            cursor = doc.find(text, cursor)
            if cursor.isNull():
                break
            cursor.insertText(repl)
            count += 1
        cursor.endEditBlock()
        if count:
            self._refresh_highlights_and_label(text)
            InfoBar.success("替换完成", f"已替换 {count} 处",
                            parent=self.window(), duration=2000,
                            position=InfoBarPosition.TOP)
        else:
            self.match_label.setText("无匹配")

    def apply_theme(self, dark: bool):
        bg = '#2D2D30' if dark else '#F3F3F3'
        border = '#3F3F46' if dark else '#CCCCCC'
        fg = '#D4D4D4' if dark else '#1E1E1E'
        ibg = '#3C3C3C' if dark else '#FFFFFF'
        self.setStyleSheet(
            f"SearchBar {{ background: {bg}; "
            f"border-bottom: 1px solid {border}; }}")
        input_style = (
            f"QLineEdit {{ background: {ibg}; color: {fg}; "
            f"border: 1px solid {border}; border-radius: 4px; "
            f"padding: 4px 8px; font-size: 13px; }}"
            f"QLineEdit:focus {{ border-color: #0078D4; }}")
        self.search_input.setStyleSheet(input_style)
        self.replace_input.setStyleSheet(input_style)

class EditorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("editorPage")

        self._path = ''
        self._key = 0
        self._encoding = 'shift_jis'
        self._entries = []
        self._original_lines = []
        self._ystb = None
        self._modified = False
        self._enabled = False
        self._from_ypf = False
        self._ypf_context = None
        self._is_txt_mode = False

        self._build_ui()
        self._set_enabled(False)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        toolbar = QWidget()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet("background: transparent;")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(20, 4, 20, 4)
        tb.setSpacing(10)

        self.file_label = BodyLabel("未加载文件")
        self.file_label.setStyleSheet("color: rgba(255,255,255,0.5);")
        tb.addWidget(self.file_label)
        tb.addStretch()

        tb.addWidget(BodyLabel("编码:"))
        self.enc_combo = ComboBox()
        self.enc_combo.addItems(["SHIFT_JIS", "GBK", "UTF-8", "BIG5"])
        self.enc_combo.setMaximumWidth(120)
        self.enc_combo.currentTextChanged.connect(self._on_enc_change)
        tb.addWidget(self.enc_combo)

        self.btn_save = PrimaryPushButton(FluentIcon.SAVE, "保存")
        self.btn_save.setMaximumWidth(100)
        self.btn_save.clicked.connect(self._save)
        tb.addWidget(self.btn_save)

        self.btn_saveas = PushButton(FluentIcon.SAVE_AS, "另存为")
        self.btn_saveas.setMaximumWidth(100)
        self.btn_saveas.clicked.connect(self._save_as)
        tb.addWidget(self.btn_saveas)

        root.addWidget(toolbar)

        self.editor = QPlainTextEdit()
        self.search_bar = SearchBar(self.editor, self)
        root.addWidget(self.search_bar)

        self.editor.setTabStopDistance(32)
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.cursorPositionChanged.connect(self._on_cursor_moved)
        self.editor.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        SmoothScrollDelegate(self.editor)
        root.addWidget(self.editor, 1)

        sb = QWidget()
        sb.setFixedHeight(26)
        sb.setStyleSheet("background: transparent;")
        sbl = QHBoxLayout(sb)
        sbl.setContentsMargins(20, 0, 20, 0)
        self.status = CaptionLabel("就绪")
        sbl.addWidget(self.status)
        sbl.addStretch()
        self.line_info = CaptionLabel("")
        sbl.addWidget(self.line_info)
        root.addWidget(sb)

        QShortcut(QKeySequence("Ctrl+F"), self, self._open_search)

        self._apply_theme()

    def _open_search(self):
        self.search_bar.open_bar()

    def _apply_theme(self):
        dark = isDarkTheme()
        bg = '#1E1E1E' if dark else '#FFFFFF'
        fg = '#D4D4D4' if dark else '#1E1E1E'
        sel = 'rgba(0,120,212,0.35)' if dark else 'rgba(0,120,212,0.2)'
        from .settings_page import Settings
        cfg = Settings.load()
        family = cfg.editor_font_family or "'Cascadia Code', 'Consolas', monospace"
        if cfg.editor_font_family:
            family = f"'{cfg.editor_font_family}'"
        size = f"{cfg.editor_font_size}px"
        self.editor.setStyleSheet(
            f"QPlainTextEdit {{ background: {bg}; color: {fg}; "
            f"border: none; padding: 12px 16px; "
            f"font-family: {family}; font-size: {size}; "
            f"selection-background-color: {sel}; }}")
        self.search_bar.apply_theme(dark)

    def _set_enabled(self, on: bool):
        self._enabled = on
        self.editor.setReadOnly(not on)
        self.btn_save.setEnabled(on)
        self.btn_saveas.setEnabled(on)
        self.enc_combo.setEnabled(on)
        if not on:
            self.editor.setPlainText("")
            self.editor.setPlaceholderText(
                "工作台载入后启用")

    def set_ypf_context(self, ctx):
        self._ypf_context = ctx

    def load_file(self, path: str, key: int, encoding: str):
        from yuris_toolkit.core.ystb import YSTBFile

        self._is_txt_mode = False
        self._path = path
        self._key = key
        self._encoding = encoding.lower().replace('-', '_')

        self._ystb = YSTBFile.from_file(path, key=key)
        if not encoding or encoding == 'auto':
            self._encoding = self._ystb.detect_text_encoding()

        texts = self._ystb.extract_texts(self._encoding)
        if not texts:
            self._set_enabled(False)
            self.file_label.setText(f"{Path(path).name} (无有效文本)")
            self.status.setText("该文件包含不可编辑的文本")
            return

        self._entries = [
            (t.args_offset, t.is_option, t.text) for t in texts]

        lines = []
        for _, is_opt, txt in self._entries:
            prefix = '[OPT] ' if is_opt else ''
            lines.append(f"{prefix}{txt}")
        self._original_lines = list(lines)

        self._set_enabled(True)
        self.editor.setPlainText('\n'.join(lines))
        self.editor.moveCursor(self.editor.textCursor().Start)
        self._modified = False

        self.search_bar.on_file_changed()

        self._from_ypf = 'yuris_toolkit_ypf' in path.replace('\\', '/')

        self.btn_save.setVisible(not self._from_ypf or
                                 self._ypf_context is not None)

        enc_name = self._encoding.upper().replace('_', '-')
        idx = {'SHIFT-JIS': 0, 'SHIFT_JIS': 0, 'GBK': 1, 'UTF-8': 2,
               'BIG5': 3}
        self.enc_combo.blockSignals(True)
        self.enc_combo.setCurrentIndex(idx.get(enc_name, 0))
        self.enc_combo.blockSignals(False)

        key_s = f"  Key: 0x{key:08X}" if key else ''
        if self._ypf_context:
            ypf_s = '  [Script YPF]'
        elif self._from_ypf:
            ypf_s = '  [Archive YPF]'
        else:
            ypf_s = ''
        self.file_label.setText(f"{Path(path).name}{key_s}{ypf_s}")
        self.file_label.setStyleSheet("color: white; font-weight: 500;")
        self._update_line_info()
        self.status.setText("已加载")

    def _on_cursor_moved(self):
        if self._enabled:
            self._update_line_info()

    def _update_line_info(self):
        line = self.editor.textCursor().blockNumber() + 1
        if self._is_txt_mode:
            total = self.editor.document().blockCount()
            self.line_info.setText(f"第 {line} 行 | 共 {total} 行")
        else:
            total = len(self._entries) if self._entries else 0
            self.line_info.setText(f"第 {line} 行 | 共 {total} 条文本")

    def _on_enc_change(self, text):
        if not self._path or not self._enabled:
            return
        if self._is_txt_mode:
            return
        enc_map = {'SHIFT_JIS': 'shift_jis', 'GBK': 'gbk', 'UTF-8': 'utf-8',
                   'BIG5': 'big5'}
        new_enc = enc_map.get(text, 'shift_jis')
        if new_enc != self._encoding:
            self.load_file(self._path, self._key, new_enc)
            self.status.setText(f"已切换编码为 {text}")

    def _on_text_changed(self):
        if self._enabled:
            self._modified = True
            self.status.setText("已修改 (未保存)")

    def _save(self):
        if self._is_txt_mode:
            self._do_save_txt(self._path)
            return
        if not self._ystb or not self._path:
            return
        self._do_save(self._path)

    def _save_as(self):
        if self._is_txt_mode:
            path, _ = QFileDialog.getSaveFileName(
                self, "另存为", str(Path(self._path).parent),
                "TXT (*.txt);;All (*)")
            if path:
                self._do_save_txt(path, writeback_ypf=False)
            return
        if not self._ystb:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "另存为", str(Path(self._path).parent),
            "YBN (*.ybn);;All (*)")
        if path:
            self._do_save(path, writeback_ypf=False)

    def _do_save(self, target_path: str, writeback_ypf: bool = True):
        from yuris_toolkit.core.ystb import YSTBFile

        target = Path(target_path)
        if target.exists():
            try:
                from yuris_toolkit.gui.settings_page import Settings
                if Settings.load().auto_backup:
                    bak = target.with_suffix(target.suffix + '.bak')
                    shutil.copy2(str(target), str(bak))
            except Exception:
                pass

        try:
            ystb = YSTBFile.from_file(self._path, key=self._key)
            ystb.reset_append()

            current_lines = self.editor.toPlainText().split('\n')

            changed = 0
            for i, (offset, is_opt, orig) in enumerate(self._entries):
                if i >= len(current_lines):
                    break
                line = current_lines[i]
                if line.startswith('[OPT] '):
                    line = line[6:]

                if line != orig:
                    ystb.insert_text(offset, line,
                                     target_encoding=self._encoding,
                                     is_option=is_opt)
                    changed += 1

            ystb.save(target_path, key=self._key)
            self._modified = False
            self.status.setText(f"已保存 ({changed} 条修改)")

            if writeback_ypf and self._ypf_context and changed > 0:
                self._writeback_ypf(target_path)

            InfoBar.success("已保存",
                            f"{Path(target_path).name}: {changed} 条修改",
                            parent=self.window(), duration=3000,
                            position=InfoBarPosition.TOP)
        except Exception as e:
            InfoBar.error("保存失败", str(e),
                          parent=self.window(), duration=5000,
                          position=InfoBarPosition.TOP)

    def _writeback_ypf(self, ybn_path: str):
        ctx = self._ypf_context
        if not ctx:
            return
        try:
            reader = ctx['reader']
            entry = reader.find_entry(ctx['entry_path'])
            if not entry:
                raise ValueError(f"YPF 中未找到 {ctx['entry_path']}")
            new_data = Path(ybn_path).read_bytes()
            reader.update_entry(entry, new_data)
            self.status.setText(
                f"已保存至原 YPF: {Path(ctx['ypf_path']).name}")
            InfoBar.success("YPF 已保存",
                            f"已更新 {Path(ctx['entry_path']).name} -> "
                            f"{Path(ctx['ypf_path']).name}",
                            parent=self.window(), duration=3000,
                            position=InfoBarPosition.TOP)
        except Exception as e:
            InfoBar.error("YPF 保存失败", str(e),
                          parent=self.window(), duration=5000,
                          position=InfoBarPosition.TOP)

    @property
    def is_modified(self) -> bool:
        return self._modified

    def load_txt_file(self, path: str):
        self._is_txt_mode = True
        self._path = path
        self._key = 0
        self._ystb = None
        self._entries = []
        self._encoding = 'utf-8'

        data = Path(path).read_bytes()
        # Detect encoding
        if data[:3] == b'\xef\xbb\xbf':
            text = data[3:].decode('utf-8')
            self._encoding = 'utf-8'
        else:
            for enc in ('utf-8', 'big5', 'shift_jis', 'gbk'):
                try:
                    text = data.decode(enc)
                    self._encoding = enc
                    break
                except (UnicodeDecodeError, ValueError):
                    continue
            else:
                text = data.decode('utf-8', errors='replace')

        self._set_enabled(True)
        self.editor.setPlainText(text)
        self.editor.moveCursor(self.editor.textCursor().Start)
        self._modified = False

        self.search_bar.on_file_changed()

        self._from_ypf = 'yuris_toolkit_ypf' in path.replace('\\', '/')
        self.btn_save.setVisible(True)

        enc_name = self._encoding.upper().replace('_', '-')
        idx = {'SHIFT-JIS': 0, 'SHIFT_JIS': 0, 'GBK': 1, 'UTF-8': 2,
               'BIG5': 3}
        self.enc_combo.blockSignals(True)
        self.enc_combo.setCurrentIndex(idx.get(enc_name, 2))
        self.enc_combo.blockSignals(False)
        self.enc_combo.setEnabled(False)

        if self._ypf_context:
            ypf_s = '  [来源:脚本YPF]'
        elif self._from_ypf:
            ypf_s = '  [来源:资源YPF]'
        else:
            ypf_s = ''
        self.file_label.setText(f"{Path(path).name}  [TXT]{ypf_s}")
        self.file_label.setStyleSheet("color: white; font-weight: 500;")
        self._update_line_info()
        self.status.setText("已加载 TXT")

    def _do_save_txt(self, target_path: str, writeback_ypf: bool = True):
        target = Path(target_path)
        if target.exists():
            try:
                from yuris_toolkit.gui.settings_page import Settings
                if Settings.load().auto_backup:
                    bak = target.with_suffix(target.suffix + '.bak')
                    shutil.copy2(str(target), str(bak))
            except Exception:
                pass

        try:
            text = self.editor.toPlainText()
            encoded = text.encode(self._encoding)
            Path(target_path).write_bytes(encoded)
            self._modified = False
            self.status.setText("已保存 TXT")

            if writeback_ypf and self._ypf_context:
                self._writeback_ypf(target_path)

            InfoBar.success("已保存",
                            f"{Path(target_path).name}",
                            parent=self.window(), duration=3000,
                            position=InfoBarPosition.TOP)
        except Exception as e:
            InfoBar.error("保存失败", str(e),
                          parent=self.window(), duration=5000,
                          position=InfoBarPosition.TOP)
