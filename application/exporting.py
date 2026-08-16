from __future__ import annotations

import struct
import zlib
from collections.abc import Callable
from pathlib import Path

from core.encoding import Encoding
from core.ypf import YPFReader, normalize_archive_path, safe_output_path
from core.ystb import YSTBFile

ProgressCallback = Callable[[int, int, str], None]
_BATCH_ERRORS = (
    OSError, ValueError, struct.error, UnicodeError, LookupError, zlib.error,
)


def _relative_output(base: str | Path, relative: str,
                     suffix: str | None = None) -> Path:
    path = normalize_archive_path(relative)
    if suffix is not None:
        path = path.with_suffix(suffix)
    return safe_output_path(base, path.as_posix())


def _item_bytes(item: dict, reader: YPFReader | None) -> bytes:
    if reader is None:
        return Path(item['path']).read_bytes()
    entry = reader.find_entry(item['path'])
    if entry is None:
        raise ValueError(f"YPF 中未找到 {item['path']}")
    return reader.extract(entry)


def _export_ystb(ystb: YSTBFile, target: Path, fmt: str,
                 encoding: str) -> int:
    texts = ystb.extract_texts(encoding)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', encoding='utf-8-sig', newline='\n') as stream:
        for entry in texts:
            if fmt == 'raw':
                prefix = '[OPT] ' if entry.is_option else ''
                stream.write(f'{prefix}{entry.text}\n')
                continue
            suffix = 'opt' if entry.is_option else ''
            stream.write(f'[{entry.args_offset}]{suffix}\n')
            stream.write(f'ORI={entry.text}\n')
            stream.write(f'TR1={entry.text}\n')
            stream.write(f'TR2={entry.text}\n')
    return len(texts)


def export_text(result: dict, output_dir: str | Path, fmt: str = 'raw',
                progress: ProgressCallback | None = None) -> tuple[int, list[str]]:
    if fmt not in ('raw', 'triline'):
        raise ValueError(f'未知导出格式: {fmt}')
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    progress = progress or (lambda _current, _total, _name: None)

    if result['mode'] == 'file':
        source = Path(result['path'])
        if result.get('kind') == 'text':
            (output / source.name).write_bytes(source.read_bytes())
        else:
            ystb = YSTBFile.from_file(
                str(source), key=result.get('key', 0))
            _export_ystb(
                ystb, output / f'{source.stem}.txt', fmt,
                result.get('encoding', Encoding.SJIS))
        progress(1, 1, source.name)
        return 1, []

    files = [
        item for item in result.get('files', [])
        if item.get('text_count', 0) > 0
    ]
    reader = YPFReader(result['path']) if result['mode'] == 'ypf' else None
    key = result.get('key', 0)
    errors = []
    exported = 0
    for index, item in enumerate(files, 1):
        relative = item.get('relative_path') or item['name']
        try:
            data = _item_bytes(item, reader)
            target = _relative_output(
                output, relative, None if item.get('is_txt') else '.txt')
            if item.get('is_txt'):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            else:
                ystb = YSTBFile.from_bytes(data, key=key)
                _export_ystb(
                    ystb, target, fmt,
                    item.get('encoding', result.get(
                        'encoding', Encoding.SJIS)))
            exported += 1
        except _BATCH_ERRORS as exc:
            errors.append(f'{relative}: {exc}')
        progress(index, len(files), relative)
    return exported, errors


def decrypt(result: dict, output_dir: str | Path,
            progress: ProgressCallback | None = None) -> tuple[int, list[str]]:
    output = Path(output_dir).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    progress = progress or (lambda _current, _total, _name: None)
    key = result.get('key', 0)

    if result['mode'] == 'file':
        source = Path(result['path'])
        ystb = YSTBFile.from_file(str(source), key=key)
        ystb.save(str(output / source.name), key=0)
        progress(1, 1, source.name)
        return 1, []

    files = [
        item for item in result.get('files', [])
        if not item.get('is_txt')
    ]
    reader = YPFReader(result['path']) if result['mode'] == 'ypf' else None
    errors = []
    count = 0
    for index, item in enumerate(files, 1):
        relative = item.get('relative_path') or item['name']
        try:
            ystb = YSTBFile.from_bytes(_item_bytes(item, reader), key=key)
            target = _relative_output(output, relative, '.ybn')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(ystb.to_bytes(0))
            count += 1
        except _BATCH_ERRORS as exc:
            errors.append(f'{relative}: {exc}')
        progress(index, len(files), relative)
    return count, errors


def extract_archive(result: dict, output_dir: str | Path,
                    progress: ProgressCallback | None = None) -> tuple[int, list[str]]:
    reader = YPFReader(result['path'])
    progress = progress or (lambda _current, _total, _name: None)
    errors = []
    count = 0
    total = len(reader.entries)
    for index, entry in enumerate(reader.entries, 1):
        try:
            reader.extract_to_file(entry, str(output_dir))
            count += 1
        except _BATCH_ERRORS as exc:
            errors.append(f'{entry.path}: {exc}')
        progress(index, total, entry.path)
    return count, errors
