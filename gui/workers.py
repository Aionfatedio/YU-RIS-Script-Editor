import struct
import traceback
from pathlib import Path
from PyQt5.QtCore import QThread, pyqtSignal


class AnalysisWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def run(self):
        try:
            self.finished.emit(self._analyze(self.path))
        except Exception as e:
            self.error.emit(f"{e}\n{traceback.format_exc()}")

    def _analyze(self, path_str: str) -> dict:
        path = Path(path_str)
        if path.is_dir():
            return self._folder(path)
        if path.suffix.lower() == '.exe':
            return self._exe(path)
        if path.suffix.lower() == '.ypf':
            return self._ypf(path)
        return self._file(path)

    # ------------------------------------------------------------------
    def _file(self, path: Path) -> dict:
        from yuris_toolkit.core.ystb import YSTBFile
        data = path.read_bytes()
        if len(data) < 0x20 or data[:4] != b'YSTB':
            return {'mode': 'file', 'path': str(path),
                    'error': '非有效 YSTB 文件'}

        version = struct.unpack_from('<I', data, 4)[0]
        key = YSTBFile.guess_key(str(path))
        ystb = YSTBFile.from_file(str(path), key=key)
        encoding = ystb.detect_text_encoding()
        texts = ystb.extract_texts(encoding)

        if key != 0:
            ft = '原始 YBN'
        elif encoding == 'gbk':
            ft = '再编码 YBN (GBK)'
        elif encoding == 'utf-8':
            ft = '再编码 YBN (UTF-8)'
        else:
            ft = '未加密 YBN'
        is_text = len(texts) > 0
        if not is_text:
            ft += ' [控制脚本]'

        preview = []
        for t in texts[:30]:
            prefix = '[OPT] ' if t.is_option else ''
            preview.append(f"{prefix}{t.text}")

        return {
            'mode': 'file', 'path': str(path),
            'file_type': ft, 'key': key,
            'version': version, 'size': path.stat().st_size,
            'encoding': encoding, 'text_count': len(texts),
            'is_text': is_text, 'preview': '\n'.join(preview),
        }

    def _folder(self, path: Path) -> dict:
        from yuris_toolkit.core.ystb import YSTBFile
        ybn_files = sorted(path.glob('*.ybn'))
        if not ybn_files:
            return {'mode': 'folder', 'path': str(path),
                    'error': '文件夹中未找到 .ybn 文件'}
        self.progress.emit(f'扫描到 {len(ybn_files)} 个 YBN 文件...')

        largest = max(ybn_files, key=lambda f: f.stat().st_size)
        key = YSTBFile.guess_key(str(largest))
        self.progress.emit(f'密钥: 0x{key:08X}')

        detected_enc = 'shift_jis'
        files = []
        for i, f in enumerate(ybn_files):
            try:
                ystb = YSTBFile.from_file(str(f), key=key)
                if i == 0 or f == largest:
                    detected_enc = ystb.detect_text_encoding()
                tc = len(ystb.extract_texts(detected_enc))
            except Exception:
                tc = -1
            files.append({
                'name': f.name, 'path': str(f),
                'size': f.stat().st_size, 'text_count': tc,
                'type': '剧情脚本' if tc > 0 else (
                    '控制脚本' if tc == 0 else '未知'),
            })
            if (i + 1) % 5 == 0:
                self.progress.emit(f'分析中 {i+1}/{len(ybn_files)}')

        return {
            'mode': 'folder', 'path': str(path), 'key': key,
            'encoding': detected_enc,
            'file_count': len(ybn_files),
            'text_script_count': sum(1 for f in files if f['text_count'] > 0),
            'files': files,
        }

    def _exe(self, path: Path) -> dict:
        game_dir = path.parent
        ysbin = game_dir / 'ysbin'

        if ysbin.exists() and list(ysbin.glob('*.ybn')):
            return self._folder(ysbin)

        ypf_files = sorted(game_dir.glob('*.ypf'))

        if len(ypf_files) == 1:
            return self._ypf(ypf_files[0])

        if len(ypf_files) > 1:
            ypf_list = []
            for yf in ypf_files:
                ypf_list.append({
                    'name': yf.name,
                    'path': str(yf),
                    'size': yf.stat().st_size,
                })
            return {
                'mode': 'exe', 'path': str(path),
                'exe_name': path.name, 'game_dir': str(game_dir),
                'ypf_files': ypf_list,
            }

        return {
            'mode': 'exe', 'path': str(path),
            'exe_name': path.name, 'game_dir': str(game_dir),
            'error': '或许不是 YU-RIS 引擎？',
        }

    def _find_script_folder(self, reader) -> tuple[str, list]:
        """Auto-detect the script folder inside a YPF.
        Returns (folder_name, script_entries).
        Checks for ysbin first, then any folder with .ybn or .txt scripts.
        """
        # Try ysbin first
        ysbin = reader.list_entries('ysbin')
        if ysbin:
            return 'ysbin', ysbin

        # Search all folders for script content
        folders = reader.list_folders()
        for folder_name in folders:
            if folder_name == '(root)':
                continue
            entries = reader.list_entries(folder_name)
            has_ybn = any(e.path.lower().endswith('.ybn') for e in entries)
            has_txt = any(e.path.lower().endswith('.txt') for e in entries)
            if has_ybn or has_txt:
                return folder_name, entries

        # Check root-level scripts
        root_entries = [e for e in reader.entries
                        if '/' not in e.path.replace('\\', '/')]
        has_scripts = any(e.path.lower().endswith(('.ybn', '.txt'))
                          for e in root_entries)
        if has_scripts:
            return '(root)', root_entries

        return '', []

    def _ypf(self, path: Path) -> dict:
        from yuris_toolkit.core.ypf import YPFReader
        from yuris_toolkit.core.ystb import YSTBFile

        self.progress.emit(f'解析 {path.name} 索引...')
        reader = YPFReader(str(path))

        folders = reader.list_folders()

        script_folder, script_entries = self._find_script_folder(reader)

        if not script_entries:
            # No script folder found - show as resource YPF
            return self._ypf_resource(path, reader, folders)

        ybn_entries = [e for e in script_entries
                       if e.path.lower().endswith('.ybn')]
        txt_entries = [e for e in script_entries
                       if e.path.lower().endswith('.txt')]

        # TXT-only YPF (like sc.ypf)
        if txt_entries and not ybn_entries:
            return self._ypf_txt(path, reader, folders, script_folder,
                                 txt_entries)

        # YBN scripts (with or without TXT)
        self.progress.emit(
            f'分析 {script_folder} ({len(ybn_entries)} 个YBN文件)...')

        key = 0
        detected_enc = 'shift_jis'
        if ybn_entries:
            largest = max(ybn_entries, key=lambda e: e.decomp_size)
            try:
                data = reader.extract(largest)
                if data[:4] == b'YSTB':
                    key = YSTBFile.guess_key_from_bytes(data)
                    ystb = YSTBFile.from_bytes(data, key=key)
                    detected_enc = ystb.detect_text_encoding()
            except Exception:
                pass

        self.progress.emit(f'密钥: 0x{key:08X}')

        files = []
        for i, e in enumerate(ybn_entries):
            tc = -1
            try:
                data = reader.extract(e)
                if data[:4] == b'YSTB':
                    ystb = YSTBFile.from_bytes(data, key=key)
                    tc = len(ystb.extract_texts(detected_enc))
            except Exception:
                pass
            fname = e.path.replace('\\', '/').split('/')[-1]
            files.append({
                'name': fname, 'path': e.path,
                'size': e.decomp_size, 'text_count': tc,
                'type': '剧情脚本' if tc > 0 else (
                    '控制脚本' if tc == 0 else '未知'),
            })
            if (i + 1) % 10 == 0:
                self.progress.emit(f'分析中 {i+1}/{len(ybn_entries)}')

        # Also add TXT entries if present
        for e in txt_entries:
            fname = e.path.replace('\\', '/').split('/')[-1]
            files.append({
                'name': fname, 'path': e.path,
                'size': e.decomp_size, 'text_count': 1,
                'type': 'TXT',
                'is_txt': True,
            })

        text_count = sum(1 for f in files if f['text_count'] > 0)

        script_only = all(
            e.path.lower().endswith(('.ybn', '.txt'))
            for e in reader.entries)

        return {
            'mode': 'ypf', 'path': str(path), 'key': key,
            'encoding': detected_enc,
            'ypf_total': len(reader.entries),
            'ypf_size': path.stat().st_size,
            'folders': folders,
            'script_folder': script_folder,
            'file_count': len(ybn_entries) + len(txt_entries),
            'text_script_count': text_count,
            'has_ybn': bool(ybn_entries),
            'has_txt': bool(txt_entries),
            'files': files,
            'script_only': script_only,
            '_reader': reader,
        }

    def _ypf_txt(self, path, reader, folders, script_folder, txt_entries):
        """Handle YPF containing TXT scripts (possibly with resources)."""
        self.progress.emit(
            f'分析 {script_folder} ({len(txt_entries)} 个TXT文件)...')

        files = []
        for i, e in enumerate(txt_entries):
            fname = e.path.replace('\\', '/').split('/')[-1]
            line_count = 0
            try:
                data = reader.extract(e)
                text = self._decode_txt(data)
                line_count = text.count('\n') + 1
            except Exception:
                line_count = -1
            files.append({
                'name': fname, 'path': e.path,
                'size': e.decomp_size,
                'text_count': max(line_count, 0),
                'type': 'TXT',
                'is_txt': True,
            })
            if (i + 1) % 5 == 0:
                self.progress.emit(f'分析中 {i+1}/{len(txt_entries)}')

        script_only = all(
            e.path.lower().endswith(('.ybn', '.txt'))
            for e in reader.entries)

        return {
            'mode': 'ypf', 'path': str(path), 'key': 0,
            'encoding': 'utf-8',
            'ypf_total': len(reader.entries),
            'ypf_size': path.stat().st_size,
            'folders': folders,
            'script_folder': script_folder,
            'file_count': len(txt_entries),
            'text_script_count': len(txt_entries),
            'has_ybn': False,
            'has_txt': True,
            'files': files,
            'script_only': script_only,
            '_reader': reader,
        }

    def _ypf_resource(self, path, reader, folders):
        """Handle resource-only YPF (no scripts)."""
        # Categorize entries by type
        ext_counts = {}
        for e in reader.entries:
            ext = Path(e.path).suffix.lower()
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

        files = []
        for e in reader.entries:
            fname = e.path.replace('\\', '/').split('/')[-1]
            ext = Path(e.path).suffix.lower()
            type_names = {
                '.png': '图片', '.jpg': '图片', '.bmp': '图片',
                '.ogg': '音频', '.wav': '音频', '.mp3': '音频',
                '.ybn': '脚本', '.txt': '文本',
            }
            ft = type_names.get(ext, '资源')
            files.append({
                'name': fname, 'path': e.path,
                'size': e.decomp_size, 'text_count': 0,
                'type': ft,
            })

        return {
            'mode': 'ypf', 'path': str(path), 'key': 0,
            'encoding': 'shift_jis',
            'ypf_total': len(reader.entries),
            'ypf_size': path.stat().st_size,
            'folders': folders,
            'file_count': len(reader.entries),
            'text_script_count': 0,
            'has_ybn': False,
            'has_txt': False,
            'resource_only': True,
            'ext_counts': ext_counts,
            'files': files,
            'script_only': False,
            '_reader': reader,
        }

    @staticmethod
    def _decode_txt(data: bytes) -> str:
        if data[:3] == b'\xef\xbb\xbf':
            return data[3:].decode('utf-8')
        for enc in ('utf-8', 'big5', 'shift_jis', 'gbk'):
            try:
                return data.decode(enc)
            except (UnicodeDecodeError, ValueError):
                continue
        return data.decode('utf-8', errors='replace')
