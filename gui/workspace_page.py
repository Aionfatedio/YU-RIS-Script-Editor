from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    CaptionLabel,
    CardWidget,
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    PrimaryPushButton,
    ProgressBar,
    PushButton,
    ScrollArea,
    StrongBodyLabel,
    TableWidget,
    TextEdit,
    isDarkTheme,
)

from application.documents import ArchiveBinding, DocumentRequest
from core.encoding import Encoding
from core.ypf import YPFReader

from .theme import info_html
from .workers import AnalysisWorker, BatchOperationWorker


def _fmt(n: int) -> str:
    if n >= 1048576:
        return f"{n / 1048576:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


class _SizeItem(QTableWidgetItem):
    def __init__(self, size: int):
        super().__init__(_fmt(size))
        self._size = size

    def __lt__(self, other):
        if isinstance(other, _SizeItem):
            return self._size < other._size
        return super().__lt__(other)


class DropZone(QFrame):
    fileDropped = pyqtSignal(list)  

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover = False
        self.setAcceptDrops(True)
        self.setFixedHeight(130)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(4, 4, -4, -4)
        if self._hover:
            bg, bc = QColor(0, 120, 212, 25), QColor(0, 120, 212)
        else:
            bg = QColor(255, 255, 255, 8) if isDarkTheme() else QColor(0, 0, 0, 6)
            bc = QColor(255, 255, 255, 40) if isDarkTheme() else QColor(0, 0, 0, 30)
        p.setBrush(bg)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(r, 8, 8)
        p.setPen(QPen(bc, 1.5, Qt.DashLine))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r.adjusted(2, 2, -2, -2), 6, 6)
        tc = QColor(0, 120, 212) if self._hover else (
            QColor(170, 170, 170) if isDarkTheme() else QColor(100, 100, 100))
        p.setPen(tc)
        f = QFont()
        f.setPointSize(11)
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter,
                   "拖放文件到此处 · 左键选择文件 · 右键选择文件夹\n"
                   "支持 .ybn 脚本 | .ypf 封包 | .txt 文本 | ysbin 文件夹")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择文件", "",
                "支持的文件 (*.ybn *.ypf *.exe *.txt);;所有文件 (*)")
            if path:
                self.fileDropped.emit([path])
        elif event.button() == Qt.RightButton:
            path = QFileDialog.getExistingDirectory(self, "选择 ysbin 文件夹")
            if path:
                self.fileDropped.emit([path])

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._hover = True
            self.update()

    def dragLeaveEvent(self, e):
        self._hover = False
        self.update()

    def dropEvent(self, e):
        self._hover = False
        self.update()
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        if paths:
            self.fileDropped.emit(paths)


class WorkspacePage(ScrollArea):
    openDocument = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("workspacePage")
        self.setWidgetResizable(True)
        self.enableTransparentBackground()
        self._worker = None
        self._batch_worker = None
        self._result = None

        c = QWidget()
        c.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(c)
        lay.setContentsMargins(28, 12, 28, 12)
        lay.setSpacing(6)

        self.drop = DropZone()
        self.drop.fileDropped.connect(self._on_drop)
        lay.addWidget(self.drop)

        self.status = CaptionLabel("")
        lay.addWidget(self.status)

        self.info_card = CardWidget()
        ic = QVBoxLayout(self.info_card)
        ic.setContentsMargins(16, 8, 16, 8)
        ic.setSpacing(4)
        self.info_title = StrongBodyLabel("")
        self.info_body = QLabel("")
        self.info_body.setWordWrap(True)
        self.info_body.setTextFormat(Qt.RichText)
        self.info_body.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.info_body.setStyleSheet("background: transparent;")
        ic.addWidget(self.info_title)
        ic.addWidget(self.info_body)
        self.info_card.hide()
        lay.addWidget(self.info_card)

        br = QHBoxLayout()
        br.setSpacing(8)
        self.btn_editor = PrimaryPushButton(FluentIcon.EDIT, "在编辑器中查看")
        self.btn_raw = PushButton(FluentIcon.DOCUMENT, "导出脚本文本")
        self.btn_tri = PushButton(FluentIcon.ALIGNMENT, "导出翻译三行")
        self.btn_dec = PushButton(FluentIcon.VPN, "解密为 YBN")
        self.btn_ypf_all = PushButton(FluentIcon.FOLDER, "导出资源文件")
        for b in (self.btn_editor, self.btn_raw, self.btn_tri,
                  self.btn_dec, self.btn_ypf_all):
            br.addWidget(b)
        self.btn_editor.clicked.connect(self._open_editor)
        self.btn_raw.clicked.connect(lambda: self._export('raw'))
        self.btn_tri.clicked.connect(lambda: self._export('triline'))
        self.btn_dec.clicked.connect(self._decrypt)
        self.btn_ypf_all.clicked.connect(self._export_ypf_all)
        br.addStretch()

        from qfluentwidgets import TransparentToolButton
        self.btn_filter = TransparentToolButton(FluentIcon.FILTER)
        self.btn_filter.setToolTip("筛选")
        self.btn_filter.clicked.connect(self._show_filter_popup)
        self.btn_filter.hide()
        br.addWidget(self.btn_filter)

        self._filter_types = {}  # type_name -> enabled (dynamic)
        self.action_bar = QWidget()
        self.action_bar.setStyleSheet("background: transparent;")
        self.action_bar.setLayout(br)
        self.action_bar.hide()
        lay.addWidget(self.action_bar)

        self.table = TableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["文件名", "大小", "类型"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeToContents)

        vh = self.table.verticalHeader()
        vh.setDefaultSectionSize(32)
        vh.setDefaultAlignment(Qt.AlignCenter)
        vh.setFixedWidth(40)
        self.table.setSelectionBehavior(self.table.SelectRows)
        self.table.setEditTriggers(self.table.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setMinimumHeight(200)
        self.table.setMaximumHeight(16777215)
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.doubleClicked.connect(self._table_dblclick)
        self.table.hide()
        lay.addWidget(self.table, 10)  

        self.preview_lbl = StrongBodyLabel("文本预览")
        self.preview_lbl.hide()
        lay.addWidget(self.preview_lbl)
        self.preview = TextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(150)
        self.preview.setMaximumHeight(16777215)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview.hide()
        lay.addWidget(self.preview, 10)  

        self.progress_label = CaptionLabel("")
        self.progress_label.hide()
        lay.addWidget(self.progress_label)
        self.progress_bar = ProgressBar()
        self.progress_bar.hide()
        lay.addWidget(self.progress_bar)

        self._spacer = lay.addStretch(1)

        self.setWidget(c)

    def _on_drop(self, paths):
        p = paths[0]
        if ((self._worker and self._worker.isRunning())
                or (self._batch_worker and self._batch_worker.isRunning())):
            return
        self._hide_all()
        self.drop.setEnabled(False)
        self.status.setText(f"分析: {Path(p).name} ...")
        self._worker = AnalysisWorker(p)
        self._worker.progress.connect(lambda m: self.status.setText(m))
        self._worker.resultReady.connect(self._done)
        self._worker.failed.connect(self._analysis_failed)
        self._worker.finished.connect(self._analysis_finished)
        self._worker.start()

    def _analysis_failed(self, message: str):
        self.status.setText("ERROR")
        self._show_err(message)

    def _analysis_finished(self):
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        if not (self._batch_worker and self._batch_worker.isRunning()):
            self.drop.setEnabled(True)

    def _hide_all(self):
        for w in (self.info_card, self.action_bar, self.table,
                  self.preview_lbl, self.preview,
                  self.progress_label, self.progress_bar,
                  self.btn_filter):
            w.hide()

    def _show_err(self, msg):
        self.info_title.setText("错误")
        self.info_body.setText(msg)
        self.info_card.show()

    def _done(self, r):
        self._result = r
        self._filter_types = {}  # reset filter on new data
        if 'error' in r:
            self.status.setText("ERROR")
            self._show_err(r['error'])
            return
        m = r['mode']
        if m == 'file':
            self._show_file(r)
        elif m == 'folder':
            self._show_folder(r)
        elif m == 'exe':
            self._show_exe(r)
        elif m == 'ypf':
            self._show_ypf(r)

    def _show_file(self, r):
        self.status.setText("分析完成")
        ks = f"0x{r['key']:08X}" if r['key'] else 'N/A'
        self.info_title.setText(Path(r['path']).name)
        self.info_body.setText(info_html([
            ("文件类型", r['file_type']),
            ("文件大小", _fmt(r['size'])),
            ("加密密钥", ks),
            ("引擎版本", str(r['version'])),
            ("文本编码", r['encoding'].upper()),
            ("文本条数", f"{r['text_count']:,} 条"),
        ], isDarkTheme()))
        self.info_card.show()
        self.btn_editor.setVisible(r['is_text'])
        self.btn_raw.setVisible(r['is_text'])
        self.btn_tri.setVisible(r['is_text'] and r.get('kind') != 'text')
        self.btn_dec.setVisible(r.get('kind') != 'text' and r['key'] != 0)
        self.btn_ypf_all.hide()
        self.action_bar.show()
        if r['is_text'] and r.get('preview'):
            self.preview_lbl.setText(
                f"文本预览 (前 {min(r['text_count'], 30)} 条)")
            self.preview_lbl.show()
            self.preview.setText(r['preview'])
            self.preview.show()
        if r['is_text']:
            self.openDocument.emit(self._file_request(r, switch=False))

    def _show_folder(self, r):
        self.status.setText(f"完成 - {r['file_count']} 个文件")
        ks = f"0x{r['key']:08X}" if r['key'] else 'N/A'
        self.info_title.setText(f"{Path(r['path']).name}/")
        story = sum(item['text_count'] > 0 for item in r['files'])
        ctrl = sum(item['text_count'] == 0 for item in r['files'])
        unknown = sum(item['text_count'] < 0 for item in r['files'])
        rows = [
            ("YBN 文件", f"{r['file_count']} 个"),
            ("加密密钥", ks),
            ("文本编码", r.get('encoding', 'shift_jis').upper()),
            ("剧情脚本", f"{story} 个"),
            ("控制脚本", f"{ctrl} 个"),
        ]
        if unknown:
            rows.append(("未知脚本", f"{unknown} 个"))
        self.info_body.setText(info_html(rows, isDarkTheme()))
        self.info_card.show()
        self.btn_editor.hide()
        self.btn_raw.setVisible(r['text_script_count'] > 0)
        self.btn_tri.setVisible(r['text_script_count'] > 0)
        self.btn_dec.setVisible(r['key'] != 0)
        self.btn_ypf_all.hide()
        self.action_bar.show()
        self._populate_table(r['files'])

    def _show_exe(self, r):
        ypf_files = r.get('ypf_files', [])
        self.status.setText(f"发现 {len(ypf_files)} 个 YPF 封包, 请选择其一")
        self.info_title.setText("游戏目录")
        rows = [("游戏程序", r['exe_name'])]
        for yf in ypf_files:
            rows.append((yf['name'], _fmt(yf['size'])))
        self.info_body.setText(info_html(rows, isDarkTheme()))
        self.info_card.show()
        self.btn_editor.hide()
        self.btn_raw.hide()
        self.btn_tri.hide()
        self.btn_dec.hide()
        self.btn_ypf_all.hide()
        self.action_bar.show()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["封包文件", "大小"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, self.table.horizontalHeader().Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            1, self.table.horizontalHeader().ResizeToContents)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(ypf_files))
        for i, yf in enumerate(ypf_files):
            name_item = QTableWidgetItem(yf['name'])
            name_item.setData(Qt.UserRole, yf['path'])
            self.table.setItem(i, 0, name_item)
            self.table.setItem(i, 1, _SizeItem(yf['size']))
        self.table.setSortingEnabled(True)
        self.table.show()

    def _show_ypf(self, r):
        script_only = r.get('script_only', False)
        resource_only = r.get('resource_only', False)
        has_ybn = r.get('has_ybn', False)
        has_txt = r.get('has_txt', False)
        script_folder = r.get('script_folder', 'ysbin')

        if resource_only:
            label = f"YPF 资源包 - {r['file_count']} 个文件"
        elif has_txt and not has_ybn:
            label = f"YPF 分析完成 - {r['file_count']} 个TXT脚本"
        else:
            label = f"YPF 分析完成 - {r['file_count']} 个脚本"
            if script_only:
                label += " [脚本 YPF]"
        self.status.setText(label)

        ks = f"0x{r['key']:08X}" if r['key'] else 'N/A'
        folders = r.get('folders', {})
        folders_str = ' / '.join(f"{k} ({v})" for k, v in folders.items())
        ybn_files = [item for item in r['files'] if not item.get('is_txt')]
        story = sum(item['text_count'] > 0 for item in ybn_files)
        ctrl = sum(item['text_count'] == 0 for item in ybn_files)
        unknown = sum(item['text_count'] < 0 for item in ybn_files)
        self.info_title.setText(Path(r['path']).name)

        if resource_only:
            ext_str = ', '.join(f"{k} ({v})" for k, v
                                in r.get('ext_counts', {}).items())
            self.info_body.setText(info_html([
                ("YPF 总文件", f"{r['ypf_total']:,} 个，{_fmt(r['ypf_size'])}"),
                ("资源目录", folders_str),
                ("文件类型", ext_str or '(无)'),
            ], isDarkTheme()))
        elif has_txt and not has_ybn:
            self.info_body.setText(info_html([
                ("YPF 总文件", f"{r['ypf_total']:,} 个，{_fmt(r['ypf_size'])}"),
                ("脚本目录", script_folder),
                ("TXT", f"{r['file_count']} 个"),
                ("资源目录", folders_str),
            ], isDarkTheme()))
        else:
            rows = [
                ("YPF 总文件", f"{r['ypf_total']:,} 个，{_fmt(r['ypf_size'])}"),
                ("脚本目录", f"{script_folder} ({r['file_count']} 个)"),
                ("加密密钥", ks),
                ("文本编码", r.get('encoding', 'shift_jis').upper()),
                ("剧情脚本", f"{story} 个"),
                ("控制脚本", f"{ctrl} 个"),
            ]
            if has_txt:
                txt_count = sum(
                    item.get('is_txt', False) for item in r['files'])
                rows.append(("TXT 脚本", f"{txt_count} 个"))
            if unknown:
                rows.append(("未知脚本", f"{unknown} 个"))
            rows.append(("资源目录", folders_str))
            self.info_body.setText(info_html(rows, isDarkTheme()))
        self.info_card.show()

        # --- Button visibility ---
        has_ybn_text = any(
            f['text_count'] > 0 and not f.get('is_txt')
            for f in r['files'])
        has_resources = not script_only

        self.btn_editor.hide()
        self.btn_raw.setVisible(has_txt or has_ybn_text)
        self.btn_tri.setVisible(has_ybn_text)
        self.btn_dec.setVisible(has_ybn and r['key'] != 0)
        self.btn_ypf_all.setVisible(has_resources)
        self.action_bar.show()
        self._populate_table(r['files'])

    def _populate_table(self, files: list):
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["文件名", "大小", "类型"])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, hdr.Stretch)
        hdr.setSectionResizeMode(1, hdr.ResizeToContents)
        hdr.setSectionResizeMode(2, hdr.ResizeToContents)

        # Build dynamic type set, init new types as True
        all_types = sorted({f['type'] for f in files})
        for t in all_types:
            if t not in self._filter_types:
                self._filter_types[t] = True
        # Remove stale types not in current data
        self._filter_types = {
            k: v for k, v in self._filter_types.items() if k in all_types}

        filtered = [f for f in files
                    if self._filter_types.get(f['type'], True)]
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(filtered))
        for i, f in enumerate(filtered):
            name_item = QTableWidgetItem(f.get('display_name', f['name']))
            name_item.setData(Qt.UserRole, f['path'])
            self.table.setItem(i, 0, name_item)
            self.table.setItem(i, 1, _SizeItem(f['size']))
            tp = f['type']
            if f.get('is_txt') and f['text_count'] > 0:
                tp += f" ({f['text_count']}行)"
            elif f['text_count'] > 0:
                tp += f" ({f['text_count']}条)"
            self.table.setItem(i, 2, QTableWidgetItem(tp))
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.AscendingOrder)
        self.table.show()
        self.btn_filter.setVisible(len(all_types) > 1)

    def _show_filter_popup(self):
        from qfluentwidgets import CheckBox, Flyout, FlyoutViewBase, PrimaryPushButton

        page = self
        types = dict(page._filter_types)  # snapshot

        class FilterView(FlyoutViewBase):
            def __init__(self, parent=None):
                super().__init__(parent)
                vl = QVBoxLayout(self)
                vl.setContentsMargins(16, 12, 16, 12)
                vl.setSpacing(10)
                self._cbs = {}
                for name, checked in types.items():
                    cb = CheckBox(name)
                    cb.setChecked(checked)
                    vl.addWidget(cb)
                    self._cbs[name] = cb
                btn_row = QHBoxLayout()
                btn_row.addStretch()
                btn_reset = PushButton("重置")
                btn_reset.clicked.connect(self._reset)
                btn_apply = PrimaryPushButton("应用")
                btn_apply.clicked.connect(self._apply)
                btn_row.addWidget(btn_reset)
                btn_row.addWidget(btn_apply)
                vl.addLayout(btn_row)

            def _apply(self):
                for name, cb in self._cbs.items():
                    page._filter_types[name] = cb.isChecked()
                r = page._result
                if r and 'files' in r:
                    page._populate_table(r['files'])
                self.parent().close()

            def _reset(self):
                for cb in self._cbs.values():
                    cb.setChecked(True)

        view = FilterView()
        flyout = Flyout(view, self.window())
        win = self.window()
        flyout.show()
        cx = win.x() + (win.width() - flyout.width()) // 2
        cy = win.y() + (win.height() - flyout.height()) // 2
        flyout.move(cx, cy)

    def _open_editor(self):
        r = self._result
        if not r or not r.get('is_text'):
            return
        self.openDocument.emit(self._file_request(r, switch=True))

    @staticmethod
    def _file_request(result: dict, switch: bool = True) -> DocumentRequest:
        return DocumentRequest(
            display_name=Path(result['path']).name,
            kind=result.get('kind', 'ystb'),
            source_path=Path(result['path']),
            key=result.get('key', 0),
            source_encoding=result.get('encoding', Encoding.SJIS),
            switch_to_editor=switch,
        )


    def _table_dblclick(self, idx):
        r = self._result
        if not r:
            return
        name_item = self.table.item(idx.row(), 0)
        if not name_item:
            return
        identity = name_item.data(Qt.UserRole)

        if r['mode'] == 'exe':
            ypf_files = r.get('ypf_files', [])
            yf = next((x for x in ypf_files if x['path'] == identity), None)
            if yf:
                self._on_drop([yf['path']])
            return

        f = next((x for x in r['files'] if x['path'] == identity), None)
        if not f:
            return

        is_txt = f.get('is_txt', False)

        if not is_txt and f['text_count'] <= 0:
            return

        if r['mode'] == 'ypf':
            self._open_ypf_entry_in_editor(f)
        else:
            self.openDocument.emit(DocumentRequest(
                display_name=Path(f['path']).name,
                kind='text' if is_txt else 'ystb',
                source_path=Path(f['path']),
                key=r.get('key', 0),
                source_encoding=f.get('encoding', r.get('encoding', Encoding.SJIS)),
            ))

    def _open_ypf_entry_in_editor(self, f: dict):
        r = self._result
        is_txt = f.get('is_txt', False)
        try:
            reader = YPFReader(r['path'])
            entry = reader.find_entry(f['path'])
            if not entry:
                raise ValueError(f"YPF 中未找到 {f['path']}")
            data = reader.extract(entry)
            binding = ArchiveBinding(
                archive_path=Path(r['path']), entry_path=f['path'],
                writable=bool(r.get('script_only')))
            self.openDocument.emit(DocumentRequest(
                display_name=f.get('display_name', f['name']),
                kind='text' if is_txt else 'ystb',
                source_bytes=data,
                key=r.get('key', 0),
                source_encoding=f.get('encoding', r.get('encoding', Encoding.SJIS)),
                archive=binding,
            ))
        except Exception as e:  # noqa: BLE001 - GUI error boundary
            self._err(str(e))

    def _export(self, fmt):
        r = self._result
        if not r:
            return
        out = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if not out:
            return
        self._start_batch('export_text', out, fmt)

    def _decrypt(self):
        r = self._result
        if not r:
            return
        out = QFileDialog.getExistingDirectory(self, "解密输出目录")
        if not out:
            return
        self._start_batch('decrypt', out)

    def _export_ypf_all(self):
        r = self._result
        if not r or r['mode'] != 'ypf':
            return
        out = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if not out:
            return
        self._start_batch('extract_archive', out)

    def _start_batch(self, operation: str, output_dir: str,
                     fmt: str = 'raw'):
        if ((self._batch_worker and self._batch_worker.isRunning())
                or (self._worker and self._worker.isRunning())):
            return
        r = self._result
        if not r:
            return
        if operation == 'extract_archive':
            total = r.get('ypf_total', 0)
        elif r['mode'] == 'file':
            total = 1
        elif operation == 'decrypt':
            total = sum(not item.get('is_txt')
                        for item in r.get('files', []))
        else:
            total = sum(item.get('text_count', 0) > 0
                        for item in r.get('files', []))
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"处理中 0/{total} ...")
        self.progress_label.show()
        self.progress_bar.show()
        self.action_bar.setEnabled(False)
        self.drop.setEnabled(False)
        self._batch_worker = BatchOperationWorker(
            operation, r, output_dir, fmt)
        self._batch_worker.progress.connect(self._batch_progress)
        self._batch_worker.resultReady.connect(self._batch_done)
        self._batch_worker.failed.connect(self._batch_failed)
        self._batch_worker.finished.connect(self._batch_finished)
        self._batch_worker.start()

    def _batch_progress(self, current: int, total: int, name: str):
        self.progress_bar.setRange(0, max(total, 1))
        self.progress_bar.setValue(current)
        self.progress_label.setText(
            f"处理中 {current}/{total} · {Path(name).name}")

    def _batch_done(self, result: dict):
        self.action_bar.setEnabled(True)
        count = result['count']
        errors = result.get('errors', [])
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_label.setText(
            f"处理完成: {count} 个文件，失败 {len(errors)} 个")
        if errors:
            preview = '\n'.join(errors[:5])
            InfoBar.warning(
                '部分文件处理失败', preview,
                parent=self.window(), duration=8000,
                position=InfoBarPosition.TOP)
        else:
            self._ok(f"已处理 {count} 个文件 → {result['output_dir']}")
    def _batch_failed(self, message: str):
        self.action_bar.setEnabled(True)
        self.progress_label.setText('处理失败')
        self._err(message)

    def _batch_finished(self):
        worker = self._batch_worker
        self._batch_worker = None
        if worker is not None:
            worker.deleteLater()
        self.action_bar.setEnabled(True)
        if not (self._worker and self._worker.isRunning()):
            self.drop.setEnabled(True)

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        workers = [worker for worker in (self._worker, self._batch_worker)
                   if worker is not None and worker.isRunning()]
        for worker in workers:
            worker.requestInterruption()
        wait_results = [worker.wait(timeout_ms) for worker in workers]
        return all(wait_results)

    def _ok(self, msg):
        InfoBar.success("完成", msg, parent=self.window(),
                        duration=3000, position=InfoBarPosition.TOP)

    def _err(self, msg):
        InfoBar.error("错误", msg, parent=self.window(),
                      duration=5000, position=InfoBarPosition.TOP)
