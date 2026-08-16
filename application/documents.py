from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from core.encoding import (
    Encoding,
    decode_text,
    normalize_encoding,
)
from core.ypf import YPFReader
from core.ystb import YSTBFile


@dataclass(frozen=True)
class ArchiveBinding:
    archive_path: Path
    entry_path: str
    writable: bool = False

    def __post_init__(self):
        object.__setattr__(
            self, 'archive_path',
            Path(self.archive_path).expanduser().resolve())


@dataclass(frozen=True)
class DocumentRequest:
    display_name: str
    kind: str = 'ystb'
    source_path: Path | None = None
    source_bytes: bytes | None = None
    key: int = 0
    source_encoding: str = 'auto'
    target_encoding: str = 'auto'
    archive: ArchiveBinding | None = None
    switch_to_editor: bool = True

    def __post_init__(self):
        if self.kind not in ('ystb', 'text'):
            raise ValueError(f'未知文档类型: {self.kind}')
        if self.source_path is None and self.source_bytes is None:
            raise ValueError('文档请求缺少文件路径或内存数据')
        if self.source_path is not None:
            object.__setattr__(
                self, 'source_path',
                Path(self.source_path).expanduser().resolve())
        object.__setattr__(self, 'key', self.key & 0xFFFFFFFF)


@dataclass(frozen=True)
class SaveResult:
    target: str
    changed_count: int
    archive_updated: bool = False


def _backup_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + '.bak')


def _atomic_write(path: str | Path, data: bytes, *, backup: bool = True,
                  validator: Callable[[Path], None] | None = None) -> Path:
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f'.{target.name}.', suffix='.tmp', dir=str(target.parent))
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if validator:
            validator(temp_path)
        if backup and target.exists():
            shutil.copy2(target, _backup_path(target))
        os.replace(temp_path, target)
        return target
    finally:
        temp_path.unlink(missing_ok=True)


def _replace_archive_entry(binding: ArchiveBinding, data: bytes, *,
                           backup: bool = True) -> Path:
    if not binding.writable:
        raise PermissionError('该 YPF 包含非脚本资源，仅支持另存为')
    archive = binding.archive_path
    if not archive.is_file():
        raise FileNotFoundError(archive)

    fd, temp_name = tempfile.mkstemp(
        prefix=f'.{archive.name}.', suffix='.tmp', dir=str(archive.parent))
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        shutil.copy2(archive, temp_path)
        reader = YPFReader(str(temp_path))
        entry = reader.find_entry(binding.entry_path)
        if entry is None:
            raise ValueError(f'YPF 中未找到 {binding.entry_path}')
        reader.update_entry(entry, data)

        verifier = YPFReader(str(temp_path))
        updated = verifier.find_entry(binding.entry_path)
        if updated is None or not verifier.verify_entry(updated, expected=data):
            raise ValueError(f'YPF 更新校验失败: {binding.entry_path}')

        if backup:
            shutil.copy2(archive, _backup_path(archive))
        os.replace(temp_path, archive)
        return archive
    finally:
        temp_path.unlink(missing_ok=True)


@dataclass
class ScriptEntryModel:
    index: int
    args_offset: int
    is_option: bool
    original_text: str
    text: str

    @property
    def modified(self) -> bool:
        return self.text != self.original_text


class ScriptDocument:
    def __init__(self, source_bytes: bytes, key: int = 0,
                 source_encoding: str = 'auto',
                 target_encoding: str = 'auto'):
        self._source_bytes = bytes(source_bytes)
        self.key = key & 0xFFFFFFFF
        self.source_encoding = source_encoding
        self.target_encoding = target_encoding
        self.entries: list[ScriptEntryModel] = []
        self.version = 0
        self._load(source_encoding)

    def _load(self, source_encoding: str = 'auto') -> None:
        ystb = YSTBFile.from_bytes(self._source_bytes, key=self.key)
        encoding = (
            ystb.detect_text_encoding(preferred=Encoding.SJIS)
            if not source_encoding or source_encoding == 'auto'
            else normalize_encoding(source_encoding)
        )
        self.version = ystb.version
        self.source_encoding = encoding
        self.target_encoding = (
            encoding if not self.target_encoding or self.target_encoding == 'auto'
            else normalize_encoding(self.target_encoding)
        )
        self.entries = [
            ScriptEntryModel(i, item.args_offset, item.is_option,
                             item.text, item.text)
            for i, item in enumerate(ystb.extract_texts(encoding))
        ]

    @property
    def modified(self) -> bool:
        return ((bool(self.entries)
                 and self.target_encoding != self.source_encoding)
                or any(entry.modified for entry in self.entries))

    @property
    def changed_count(self) -> int:
        if self.target_encoding != self.source_encoding:
            return len(self.entries)
        return sum(entry.modified for entry in self.entries)

    def set_text(self, index: int, text: str) -> None:
        self.entries[index].text = text

    def set_target_encoding(self, encoding: str) -> None:
        self.target_encoding = normalize_encoding(encoding)

    def build_bytes(self, key: int | None = None) -> bytes:
        output_key = self.key if key is None else key & 0xFFFFFFFF
        if not self.modified and output_key == self.key:
            return self._source_bytes

        ystb = YSTBFile.from_bytes(self._source_bytes, key=self.key)
        ystb.reset_append()
        rewrite_all = self.target_encoding != self.source_encoding
        for entry in self.entries:
            if rewrite_all or entry.modified:
                ystb.insert_text(
                    entry.args_offset, entry.text,
                    target_encoding=self.target_encoding,
                    is_option=entry.is_option)
        return ystb.to_bytes(output_key)

    def build_decrypted_bytes(self) -> bytes:
        return self.build_bytes(key=0)

    def commit(self, source_bytes: bytes) -> None:
        target_encoding = self.target_encoding
        self._source_bytes = bytes(source_bytes)
        self.target_encoding = target_encoding
        self._load(target_encoding)


class PlainTextDocument:
    def __init__(self, source_bytes: bytes, source_encoding: str = 'auto',
                 target_encoding: str = 'auto'):
        self._source_bytes = bytes(source_bytes)
        self.text, self.source_encoding, self._had_bom = decode_text(
            self._source_bytes, source_encoding, preferred=Encoding.SJIS)
        self.original_text = self.text
        self.target_encoding = (
            self.source_encoding
            if not target_encoding or target_encoding == 'auto'
            else normalize_encoding(target_encoding)
        )

    @property
    def modified(self) -> bool:
        return (self.text != self.original_text
                or self.target_encoding != self.source_encoding)

    @property
    def changed_count(self) -> int:
        return int(self.modified)

    def set_text(self, text: str) -> None:
        self.text = text

    def set_target_encoding(self, encoding: str) -> None:
        self.target_encoding = normalize_encoding(encoding)

    def build_bytes(self) -> bytes:
        if not self.modified:
            return self._source_bytes
        payload = self.text.encode(self.target_encoding, errors='strict')
        if self._had_bom and self.target_encoding == Encoding.UTF8:
            payload = b'\xef\xbb\xbf' + payload
        return payload

    def commit(self, source_bytes: bytes) -> None:
        target_encoding = self.target_encoding
        self._source_bytes = bytes(source_bytes)
        self.text, self.source_encoding, self._had_bom = decode_text(
            self._source_bytes, target_encoding)
        self.original_text = self.text
        self.target_encoding = target_encoding


class DocumentSession:
    def __init__(self, request: DocumentRequest):
        self.display_name = request.display_name
        self.kind = request.kind
        self.source_path = request.source_path
        self.archive = request.archive
        source_bytes = (
            request.source_bytes if request.source_bytes is not None
            else request.source_path.read_bytes()
        )
        if request.kind == 'ystb':
            self.document: ScriptDocument | PlainTextDocument = ScriptDocument(
                source_bytes, key=request.key,
                source_encoding=request.source_encoding,
                target_encoding=request.target_encoding)
        else:
            self.document = PlainTextDocument(
                source_bytes, source_encoding=request.source_encoding,
                target_encoding=request.target_encoding)

    @property
    def modified(self) -> bool:
        return self.document.modified

    @property
    def can_save(self) -> bool:
        return self.archive.writable if self.archive else self.source_path is not None

    def save(self, *, backup: bool = True) -> SaveResult:
        changed = self.document.changed_count
        if not self.can_save:
            raise PermissionError('当前文档只读，请使用另存为')
        if not self.document.modified:
            target = (self.archive.archive_path if self.archive
                      else self.source_path)
            return SaveResult(str(target), 0, False)

        data = self.document.build_bytes()
        if self.archive:
            target = _replace_archive_entry(self.archive, data, backup=backup)
            archive_updated = True
        else:
            target = _atomic_write(
                self.source_path, data, backup=backup,
                validator=self._validator())
            archive_updated = False
        self.document.commit(data)
        return SaveResult(str(target), changed, archive_updated)

    def save_as(self, path: str | Path, *, backup: bool = True) -> SaveResult:
        target = Path(path).expanduser().resolve()
        changed = self.document.changed_count
        data = self.document.build_bytes()
        _atomic_write(target, data, backup=backup, validator=self._validator())
        self.source_path = target
        self.archive = None
        self.display_name = target.name
        self.document.commit(data)
        return SaveResult(str(target), changed, False)

    def _validator(self):
        if self.kind != 'ystb':
            return None
        key = self.document.key

        def validate(path: Path) -> None:
            parsed = YSTBFile.from_file(str(path), key=key)
            texts = parsed.extract_texts(self.document.target_encoding)
            if len(texts) != len(self.document.entries):
                raise ValueError('保存后的脚本文本数量不一致')

        return validate
