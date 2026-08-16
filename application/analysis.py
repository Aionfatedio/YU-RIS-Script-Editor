from __future__ import annotations

import struct
import zlib
from collections import Counter
from collections.abc import Callable, Iterable
from pathlib import Path

from core.encoding import Encoding, decode_text
from core.ypf import YPFEntry, YPFReader
from core.ystb import YSTBFile

ProgressCallback = Callable[[str], None]
_PARSE_ERRORS = (
    OSError, ValueError, struct.error, UnicodeError, LookupError, zlib.error,
)


class AnalysisService:
    def __init__(self, progress: ProgressCallback | None = None):
        self.progress = progress or (lambda _message: None)

    def analyze(self, path_value: str | Path) -> dict:
        path = Path(path_value).expanduser().resolve()
        if path.is_dir():
            return self._folder(path)
        suffix = path.suffix.lower()
        if suffix == '.exe':
            return self._exe(path)
        if suffix == '.ypf':
            return self._ypf(path)
        if suffix == '.txt':
            return self._text_file(path)
        return self._ybn_file(path)

    def _ybn_file(self, path: Path) -> dict:
        data = path.read_bytes()
        if len(data) < 0x20 or data[:4] != b'YSTB':
            return {
                'mode': 'file', 'path': str(path),
                'error': '非有效 YSTB 文件',
            }

        version = struct.unpack_from('<I', data, 4)[0]
        key = YSTBFile.guess_key_from_bytes(data)
        encoding, texts = self._inspect_script(data, key)
        if key:
            file_type = '原始 YBN'
        elif encoding == Encoding.GBK:
            file_type = '再编码 YBN (GBK)'
        elif encoding == Encoding.BIG5:
            file_type = '再编码 YBN (BIG5)'
        elif encoding == Encoding.UTF8:
            file_type = '再编码 YBN (UTF-8)'
        else:
            file_type = '未加密 YBN'
        if not texts:
            file_type += ' [控制脚本]'

        return {
            'mode': 'file', 'kind': 'ystb', 'path': str(path),
            'file_type': file_type, 'key': key, 'version': version,
            'size': path.stat().st_size, 'encoding': encoding,
            'text_count': len(texts), 'is_text': bool(texts),
            'preview': '\n'.join(
                ('[OPT] ' if item.is_option else '') + item.text
                for item in texts[:30]
            ),
        }

    @staticmethod
    def _text_file(path: Path) -> dict:
        data = path.read_bytes()
        text, encoding, _ = decode_text(data, preferred=Encoding.SJIS)
        return {
            'mode': 'file', 'kind': 'text', 'path': str(path),
            'file_type': '纯文本', 'key': 0, 'version': 0,
            'size': len(data), 'encoding': encoding,
            'text_count': text.count('\n') + bool(text),
            'is_text': True, 'preview': '\n'.join(text.splitlines()[:30]),
        }

    def _folder(self, path: Path) -> dict:
        ybn_files = sorted(path.rglob('*.ybn'))
        if not ybn_files:
            return {
                'mode': 'folder', 'path': str(path),
                'error': '文件夹中未找到 .ybn 文件',
            }
        self.progress(f'扫描到 {len(ybn_files)} 个 YBN 文件...')

        representatives = sorted(
            ybn_files, key=lambda item: item.stat().st_size,
            reverse=True)[:8]
        key = self._detect_collection_key(
            item.read_bytes() for item in representatives)
        self.progress(f'密钥: 0x{key:08X}')

        files = []
        encoding_votes: Counter[str] = Counter()
        for index, file_path in enumerate(ybn_files, 1):
            encoding = Encoding.SJIS
            text_count = -1
            try:
                encoding, texts = self._inspect_script(
                    file_path.read_bytes(), key)
                text_count = len(texts)
                if text_count:
                    encoding_votes[encoding] += 1
            except _PARSE_ERRORS:
                pass

            relative = file_path.relative_to(path).as_posix()
            files.append({
                'name': relative, 'display_name': relative,
                'path': str(file_path), 'relative_path': relative,
                'size': file_path.stat().st_size,
                'text_count': text_count, 'encoding': encoding,
                'type': self._script_type(text_count),
            })
            if index % 5 == 0:
                self.progress(f'分析中 {index}/{len(ybn_files)}')

        return {
            'mode': 'folder', 'path': str(path), 'key': key,
            'encoding': self._main_encoding(encoding_votes),
            'file_count': len(files),
            'text_script_count': sum(
                item['text_count'] > 0 for item in files),
            'files': files,
        }

    def _exe(self, path: Path) -> dict:
        game_dir = path.parent
        ysbin = game_dir / 'ysbin'
        if ysbin.exists() and any(ysbin.rglob('*.ybn')):
            return self._folder(ysbin)

        archives = sorted(game_dir.glob('*.ypf'))
        if len(archives) == 1:
            return self._ypf(archives[0])
        if len(archives) > 1:
            return {
                'mode': 'exe', 'path': str(path), 'exe_name': path.name,
                'game_dir': str(game_dir),
                'ypf_files': [
                    {'name': item.name, 'path': str(item),
                     'size': item.stat().st_size}
                    for item in archives
                ],
            }
        return {
            'mode': 'exe', 'path': str(path), 'exe_name': path.name,
            'game_dir': str(game_dir), 'error': '或许不是 YU-RIS 引擎？',
        }

    def _ypf(self, path: Path) -> dict:
        self.progress(f'解析 {path.name} 索引...')
        reader = YPFReader(str(path))
        folders = reader.list_folders()
        ybn_entries = [
            entry for entry in reader.entries
            if entry.path.lower().endswith('.ybn')
        ]
        txt_entries = [
            entry for entry in reader.entries
            if entry.path.lower().endswith('.txt')
        ]
        if not ybn_entries and not txt_entries:
            return self._ypf_resource(path, reader, folders)

        representatives = sorted(
            ybn_entries, key=lambda item: item.decomp_size,
            reverse=True)[:8]
        key = self._detect_collection_key(
            reader.extract(entry) for entry in representatives)
        self.progress(f'密钥: 0x{key:08X}')

        files = []
        encoding_votes: Counter[str] = Counter()
        for index, entry in enumerate(ybn_entries, 1):
            encoding = Encoding.SJIS
            text_count = -1
            try:
                encoding, texts = self._inspect_script(reader.extract(entry), key)
                text_count = len(texts)
                if text_count:
                    encoding_votes[encoding] += 1
            except _PARSE_ERRORS:
                pass
            item = self._archive_file_dict(entry, text_count)
            item['encoding'] = encoding
            files.append(item)
            if index % 10 == 0:
                self.progress(f'分析中 {index}/{len(ybn_entries)}')

        for entry in txt_entries:
            line_count = -1
            encoding = Encoding.UTF8
            try:
                text, encoding, _ = decode_text(
                    reader.extract(entry), preferred=Encoding.SJIS)
                line_count = text.count('\n') + bool(text)
            except _PARSE_ERRORS:
                pass
            item = self._archive_file_dict(entry, max(line_count, 0), 'TXT')
            item.update({'is_txt': True, 'encoding': encoding})
            files.append(item)

        script_only = all(
            entry.path.lower().endswith(('.ybn', '.txt'))
            for entry in reader.entries
        )
        script_folders = sorted({
            normalized.rsplit('/', 1)[0] if '/' in normalized else '(root)'
            for entry in (*ybn_entries, *txt_entries)
            for normalized in (entry.path.replace('\\', '/'),)
        })
        return {
            'mode': 'ypf', 'path': str(path), 'key': key,
            'encoding': self._main_encoding(encoding_votes),
            'ypf_total': len(reader.entries),
            'ypf_size': path.stat().st_size, 'folders': folders,
            'script_folder': ' / '.join(script_folders),
            'script_folders': script_folders,
            'file_count': len(files),
            'text_script_count': sum(
                item['text_count'] > 0 for item in files),
            'has_ybn': bool(ybn_entries), 'has_txt': bool(txt_entries),
            'files': files, 'script_only': script_only,
        }

    @staticmethod
    def _inspect_script(data: bytes, key: int):
        ystb = YSTBFile.from_bytes(data, key=key)
        encoding = ystb.detect_text_encoding(preferred=Encoding.SJIS)
        return encoding, ystb.extract_texts(encoding)

    @staticmethod
    def _script_type(text_count: int) -> str:
        if text_count > 0:
            return '剧情脚本'
        if text_count == 0:
            return '控制脚本'
        return '未知'

    @staticmethod
    def _archive_file_dict(entry: YPFEntry, text_count: int,
                           forced_type: str | None = None) -> dict:
        path = entry.path.replace('\\', '/')
        return {
            'name': path, 'display_name': path, 'path': entry.path,
            'relative_path': path, 'size': entry.decomp_size,
            'text_count': text_count,
            'type': forced_type or AnalysisService._script_type(text_count),
        }

    @staticmethod
    def _ypf_resource(path: Path, reader: YPFReader, folders: dict) -> dict:
        type_names = {
            '.png': '图片', '.jpg': '图片', '.jpeg': '图片', '.bmp': '图片',
            '.ogg': '音频', '.wav': '音频', '.mp3': '音频',
            '.ybn': '脚本', '.txt': '文本',
        }
        ext_counts: Counter[str] = Counter()
        files = []
        for entry in reader.entries:
            ext = Path(entry.path).suffix.lower()
            ext_counts[ext or '(无扩展名)'] += 1
            files.append(AnalysisService._archive_file_dict(
                entry, 0, type_names.get(ext, '资源')))
        return {
            'mode': 'ypf', 'path': str(path), 'key': 0,
            'encoding': Encoding.SJIS, 'ypf_total': len(reader.entries),
            'ypf_size': path.stat().st_size, 'folders': folders,
            'file_count': len(files), 'text_script_count': 0,
            'has_ybn': False, 'has_txt': False, 'resource_only': True,
            'ext_counts': dict(ext_counts), 'files': files,
            'script_only': False,
        }

    @staticmethod
    def _detect_collection_key(sources: Iterable[bytes]) -> int:
        votes: Counter[int] = Counter()
        for data in sources:
            if len(data) >= 0x20 and data[:4] == b'YSTB':
                key = YSTBFile.guess_key_from_bytes(data)
                if key:
                    votes[key] += 1
        if not votes:
            return 0
        return votes.most_common(1)[0][0]

    @staticmethod
    def _main_encoding(votes: Counter[str]) -> str:
        if not votes:
            return Encoding.SJIS
        return max(votes, key=lambda item: (
            votes[item], item == Encoding.SJIS))
