import json
from pathlib import Path
from dataclasses import dataclass, asdict

from PyQt5.QtCore import Qt, pyqtSignal, QUrl
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
)
from PyQt5.QtGui import QFontDatabase, QFont, QDesktopServices
from qfluentwidgets import (
    BodyLabel, CaptionLabel, StrongBodyLabel, SubtitleLabel,
    SwitchButton, ComboBox, CardWidget, ScrollArea,
    PushButton, PrimaryPushButton, FluentIcon, HyperlinkLabel,
    SpinBox, Slider, SearchLineEdit,
    Flyout, FlyoutViewBase
)

_CFG_PATH = Path(__file__).resolve().parent.parent / 'config.json'


@dataclass
class Settings:
    auto_backup: bool = True
    default_encoding: str = 'auto'   
    editor_font_family: str = ''     
    editor_font_size: int = 14       
    def save(self):
        _CFG_PATH.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2),
            encoding='utf-8')

    @classmethod
    def load(cls) -> 'Settings':
        if _CFG_PATH.exists():
            try:
                d = json.loads(_CFG_PATH.read_text(encoding='utf-8'))
                return cls(**{k: v for k, v in d.items()
                              if k in cls.__dataclass_fields__})
            except Exception:
                pass
        return cls()


class SettingsPage(ScrollArea):
    editorFontChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsPage")
        self.setWidgetResizable(True)
        self.enableTransparentBackground()

        self.cfg = Settings.load()

        c = QWidget()
        c.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(c)
        lay.setContentsMargins(28, 20, 28, 20)
        lay.setSpacing(16)

        lay.addWidget(StrongBodyLabel("设置"))

        card1 = CardWidget()
        cl1 = QHBoxLayout(card1)
        cl1.setContentsMargins(20, 14, 20, 14)
        lbl1 = QVBoxLayout()
        lbl1.addWidget(BodyLabel("保存时备份"))
        lbl1.addWidget(CaptionLabel("保存修改时将源 YBN 文件备份"))
        cl1.addLayout(lbl1, 1)
        self.sw_backup = SwitchButton()
        self.sw_backup.setChecked(self.cfg.auto_backup)
        self.sw_backup.checkedChanged.connect(self._on_backup)
        cl1.addWidget(self.sw_backup)
        lay.addWidget(card1)

        card2 = CardWidget()
        cl2 = QHBoxLayout(card2)
        cl2.setContentsMargins(20, 14, 20, 14)
        lbl2 = QVBoxLayout()
        lbl2.addWidget(BodyLabel("默认编码"))
        lbl2.addWidget(CaptionLabel("解密和封包时的编码"))
        cl2.addLayout(lbl2, 1)
        self.enc_combo = ComboBox()
        self.enc_combo.addItems(["自动", "SHIFT_JIS", "GBK", "UTF-8", "BIG5"])
        idx = {"auto": 0, "shift_jis": 1, "gbk": 2, "utf-8": 3, "big5": 4}
        self.enc_combo.setCurrentIndex(idx.get(self.cfg.default_encoding, 0))
        self.enc_combo.currentIndexChanged.connect(self._on_enc)
        self.enc_combo.setMaximumWidth(160)
        cl2.addWidget(self.enc_combo)
        lay.addWidget(card2)

        card_font = CardWidget()
        clf = QHBoxLayout(card_font)
        clf.setContentsMargins(20, 14, 20, 14)
        lblf = QVBoxLayout()
        lblf.addWidget(BodyLabel("编辑器字体"))
        lblf.addWidget(CaptionLabel("修改编辑器字体"))
        clf.addLayout(lblf, 1)
        self.font_label = CaptionLabel(self._font_display_text())
        self.font_label.setStyleSheet("color: rgba(255,255,255,0.6);")
        clf.addWidget(self.font_label)
        self.btn_font = PushButton(FluentIcon.FONT, "选择字体")
        self.btn_font.setMaximumWidth(120)
        self.btn_font.clicked.connect(self._pick_font)
        clf.addWidget(self.btn_font)
        self.btn_font_reset = PushButton("重置")
        self.btn_font_reset.setMaximumWidth(60)
        self.btn_font_reset.clicked.connect(self._reset_font)
        clf.addWidget(self.btn_font_reset)
        lay.addWidget(card_font)

        lay.addSpacing(20)
        lay.addWidget(StrongBodyLabel("关于"))

        card3 = CardWidget()
        cl3 = QVBoxLayout(card3)
        cl3.setContentsMargins(20, 14, 20, 14)
        cl3.setSpacing(6)
        cl3.addWidget(BodyLabel("YU-RIS Script Editor"))
        cl3.addWidget(CaptionLabel("支持 YU-RIS V2 / V5 引擎"))
        link_repo = HyperlinkLabel("项目地址", "https://github.com/Aionfatedio/YU-RIS-Script-Editor")
        link_repo.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://github.com/Aionfatedio/YU-RIS-Script-Editor")))
        cl3.addWidget(link_repo)
        cl3.addWidget(BodyLabel("感谢以下项目提供的工具和思路"))
        thanks_row = QHBoxLayout()
        thanks_row.setSpacing(16)
        for name, url in [
            ("YURIS_TOOLS", "https://github.com/jyxjyx1234/YURIS_TOOLS"),
            ("RxYuris", "https://github.com/ZQF-ReVN/RxYuris"),
            ("GARbro", "https://github.com/morkt/GARbro"),
        ]:
            link = HyperlinkLabel(name, url)
            link.clicked.connect(
                lambda _=None, u=url: QDesktopServices.openUrl(QUrl(u)))
            thanks_row.addWidget(link)
        thanks_row.addStretch()
        cl3.addLayout(thanks_row)
        lay.addWidget(card3)

        lay.addStretch()
        self.setWidget(c)

    def _font_display_text(self) -> str:
        f = self.cfg.editor_font_family
        s = self.cfg.editor_font_size
        if not f:
            return f"默认 ({s}px)"
        return f"{f}, {s}px"

    def _pick_font(self):
        page = self

        class FontFlyoutView(FlyoutViewBase):
            def __init__(self, parent=None):
                super().__init__(parent)
                self._all_fonts = QFontDatabase().families()

                vl = QVBoxLayout(self)
                vl.setContentsMargins(20, 16, 20, 16)
                vl.setSpacing(10)

                vl.addWidget(StrongBodyLabel("编辑器字体配置"))

                self._search = SearchLineEdit()
                self._search.setPlaceholderText("搜索字体...")
                self._search.textChanged.connect(self._filter_fonts)
                vl.addWidget(self._search)

                row1 = QHBoxLayout()
                row1.addWidget(BodyLabel("字体:"))
                self._family = ComboBox()
                self._family.addItems(self._all_fonts)
                cur = page.cfg.editor_font_family or 'Consolas'
                idx = self._family.findText(cur)
                if idx >= 0:
                    self._family.setCurrentIndex(idx)
                self._family.setMinimumWidth(240)
                self._family.currentTextChanged.connect(self._update_preview)
                row1.addWidget(self._family, 1)
                vl.addLayout(row1)

                row2 = QHBoxLayout()
                row2.addWidget(BodyLabel("大小:"))
                self._slider = Slider(Qt.Horizontal)
                self._slider.setRange(8, 32)
                self._slider.setValue(page.cfg.editor_font_size)
                self._slider.valueChanged.connect(self._update_preview)
                row2.addWidget(self._slider, 1)
                self._size_lbl = BodyLabel(f"{self._slider.value()} px")
                self._size_lbl.setFixedWidth(50)
                row2.addWidget(self._size_lbl)
                vl.addLayout(row2)

                row3 = QHBoxLayout()
                row3.addWidget(BodyLabel("粗体:"))
                row3.addStretch()
                self._bold = SwitchButton()
                self._bold.setChecked(False)
                self._bold.checkedChanged.connect(self._update_preview)
                row3.addWidget(self._bold)
                vl.addLayout(row3)

                self._preview = BodyLabel(
                    "HelloWorld 你好 君の名前は？ 1234567890")
                self._preview.setAlignment(Qt.AlignCenter)
                self._preview.setMinimumHeight(44)
                self._preview.setStyleSheet(
                    "BodyLabel{padding:10px;color:white;"
                    "border:1px solid #555;border-radius:6px}")
                vl.addWidget(self._preview)

                btn_row = QHBoxLayout()
                btn_row.addStretch()
                btn_reset = PushButton("重置")
                btn_reset.clicked.connect(self._reset)
                btn_apply = PrimaryPushButton("应用")
                btn_apply.clicked.connect(self._apply)
                btn_row.addWidget(btn_reset)
                btn_row.addWidget(btn_apply)
                vl.addLayout(btn_row)

                self._update_preview()

            def _filter_fonts(self, text):
                self._family.blockSignals(True)
                self._family.clear()
                if text:
                    filtered = [f for f in self._all_fonts
                                if text.lower() in f.lower()]
                else:
                    filtered = self._all_fonts
                self._family.addItems(filtered)
                self._family.blockSignals(False)
                if filtered:
                    self._family.setCurrentIndex(0)
                    self._update_preview()

            def _update_preview(self, *_):
                family = self._family.currentText()
                size = self._slider.value()
                bold = self._bold.isChecked()
                self._size_lbl.setText(f"{size} px")
                font = QFont(family, size)
                font.setBold(bold)
                self._preview.setFont(font)

            def _apply(self):
                page.cfg.editor_font_family = self._family.currentText()
                page.cfg.editor_font_size = self._slider.value()
                page.cfg.save()
                page.font_label.setText(page._font_display_text())
                page.editorFontChanged.emit()
                self.parent().close()

            def _reset(self):
                page.cfg.editor_font_family = ''
                page.cfg.editor_font_size = 14
                page.cfg.save()
                page.font_label.setText(page._font_display_text())
                page.editorFontChanged.emit()
                self.parent().close()

        view = FontFlyoutView()
        flyout = Flyout(view, self.window())
        win = self.window()
        flyout.show()
        cx = win.x() + (win.width() - flyout.width()) // 2
        cy = win.y() + (win.height() - flyout.height()) // 2
        flyout.move(cx, cy)

    def _reset_font(self):
        self.cfg.editor_font_family = ''
        self.cfg.editor_font_size = 14
        self.cfg.save()
        self.font_label.setText(self._font_display_text())
        self.editorFontChanged.emit()

    def _on_backup(self, checked):
        self.cfg.auto_backup = checked
        self.cfg.save()

    def _on_enc(self, idx):
        enc_map = {0: 'auto', 1: 'shift_jis', 2: 'gbk', 3: 'utf-8', 4: 'big5'}
        self.cfg.default_encoding = enc_map.get(idx, 'auto')
        self.cfg.save()
