import struct
import zlib
from pathlib import Path
from typing import Optional

HEADER_SIZE = 0x20

_SWAP_TABLE_00 = bytes([
    0x03, 0x48, 0x06, 0x35,
    0x0C, 0x10, 0x11, 0x19, 0x1C, 0x1E,
    0x09, 0x0B, 0x0D, 0x13, 0x15, 0x1B,
    0x20, 0x23, 0x26, 0x29, 0x2C, 0x2F, 0x2E, 0x32,
])
_SWAP_TABLE_04 = bytes([
    0x0C, 0x10, 0x11, 0x19, 0x1C, 0x1E,
    0x09, 0x0B, 0x0D, 0x13, 0x15, 0x1B,
    0x20, 0x23, 0x26, 0x29, 0x2C, 0x2F, 0x2E, 0x32,
])
_SWAP_TABLE_10 = bytes([
    0x09, 0x0B, 0x0D, 0x13, 0x15, 0x1B,
    0x20, 0x23, 0x26, 0x29, 0x2C, 0x2F, 0x2E, 0x32,
])


def _select_swap_table(version: int) -> bytes:
    if version < 0x100:
        return _SWAP_TABLE_04
    if 0x12C <= version < 0x196:
        return _SWAP_TABLE_10
    return _SWAP_TABLE_00


def _decrypt_length(swap_table: bytes, value: int) -> int:
    try:
        pos = swap_table.index(value)
    except ValueError:
        return value
    if pos & 1:
        return swap_table[pos - 1]
    return swap_table[pos + 1]


def _extra_header_size(version: int) -> int:
    if version >= 0x1D9:
        return 4
    if version == 0xDE:
        return 8
    return 0


def _validate_meta(index_data: bytes, meta_pos: int, extra_size: int,
                   file_size: int, data_start: int) -> bool:
    if meta_pos + extra_size > len(index_data):
        return False
    ft = index_data[meta_pos]
    ic = index_data[meta_pos + 1]
    ds = struct.unpack_from('<I', index_data, meta_pos + 2)[0]
    cs = struct.unpack_from('<I', index_data, meta_pos + 6)[0]
    do = struct.unpack_from('<I', index_data, meta_pos + 10)[0]
    if ft > 10:
        return False
    if ic > 1:
        return False
    if ds == 0 or ds > 0x40000000:
        return False
    if cs == 0 or cs > file_size:
        return False
    if do < data_start or do >= file_size:
        return False
    if not ic and cs != ds:
        return False
    if ic and cs > ds:
        return False
    return True


def _try_decode_name(raw_bytes: bytearray, name_key: int) -> bool:
    dec = bytearray(raw_bytes)
    for i in range(len(dec)):
        dec[i] ^= name_key
    try:
        text = bytes(dec).decode('shift_jis')
    except UnicodeDecodeError:
        return False
    for ch in text:
        o = ord(ch)
        if o < 0x20 and o not in (0x09, 0x0A, 0x0D):
            return False
    return '.' in text or '/' in text or '\\' in text


class YPFEntry:
    __slots__ = ('crc', 'path', 'file_type', 'is_compressed',
                 'decomp_size', 'comp_size', 'data_offset', 'data_crc',
                 '_meta_file_offset')

    def __init__(self):
        self.crc: int = 0
        self.path: str = ''
        self.file_type: int = 0
        self.is_compressed: bool = False
        self.decomp_size: int = 0
        self.comp_size: int = 0
        self.data_offset: int = 0
        self.data_crc: int = 0
        self._meta_file_offset: int = 0

    @property
    def size(self) -> int:
        return self.decomp_size


class YPFReader:
    def __init__(self, filepath: str):
        self.filepath = Path(filepath)
        self.version: int = 0
        self.entry_count: int = 0
        self.entries: list[YPFEntry] = []
        self._parse_index()

    def _parse_index(self):
        with open(self.filepath, 'rb') as f:
            header = f.read(HEADER_SIZE)

        if header[:4] != b'YPF\x00':
            raise ValueError(f"非有效YPF文件: {self.filepath}")

        self.version = struct.unpack_from('<I', header, 4)[0]
        self.entry_count = struct.unpack_from('<I', header, 8)[0]
        dir_size = struct.unpack_from('<I', header, 12)[0]
        file_size = self.filepath.stat().st_size
        data_start = HEADER_SIZE + dir_size

        swap_table = _select_swap_table(self.version)
        extra_size = 0x12 + _extra_header_size(self.version)

        with open(self.filepath, 'rb') as f:
            f.seek(HEADER_SIZE)
            index_data = f.read(dir_size)

        pos = 0
        name_key = -1

        for _ in range(self.entry_count):
            if pos + 5 + extra_size > len(index_data):
                break

            crc = struct.unpack_from('<I', index_data, pos)[0]
            pos += 4

            raw_len_byte = index_data[pos] ^ 0xFF
            name_size = _decrypt_length(swap_table, raw_len_byte)
            pos += 1

            name_start = pos

            # Validate: try swap-table result, then brute-force if invalid
            valid = (name_size > 0
                     and name_start + name_size + extra_size <= len(index_data)
                     and _validate_meta(index_data, name_start + name_size,
                                        extra_size, file_size, data_start))

            if not valid:
                found = False
                for try_len in range(1, min(256, len(index_data) - name_start - extra_size)):
                    if try_len == name_size:
                        continue
                    meta_pos = name_start + try_len
                    if not _validate_meta(index_data, meta_pos, extra_size,
                                          file_size, data_start):
                        continue
                    if name_key >= 0:
                        raw = bytearray(index_data[name_start:name_start + try_len])
                        if _try_decode_name(raw, name_key):
                            name_size = try_len
                            found = True
                            break
                    else:
                        name_size = try_len
                        found = True
                        break
                if not found:
                    name_size = _decrypt_length(swap_table, raw_len_byte)
                    if name_size == 0 or name_start + name_size + extra_size > len(index_data):
                        break

            raw_name = bytearray(index_data[name_start:name_start + name_size])
            pos = name_start + name_size

            if name_key < 0:
                if name_size >= 4:
                    name_key = raw_name[name_size - 4] ^ ord('.')
                else:
                    name_key = 0xFF

            for i in range(name_size):
                raw_name[i] ^= name_key
            try:
                path = bytes(raw_name).decode('shift_jis')
            except UnicodeDecodeError:
                path = bytes(raw_name).decode('shift_jis', errors='replace')

            entry = YPFEntry()
            entry.crc = crc
            entry.path = path
            entry._meta_file_offset = HEADER_SIZE + pos
            entry.file_type = index_data[pos]
            entry.is_compressed = bool(index_data[pos + 1])
            entry.decomp_size = struct.unpack_from('<I', index_data, pos + 2)[0]
            entry.comp_size = struct.unpack_from('<I', index_data, pos + 6)[0]
            entry.data_offset = struct.unpack_from('<I', index_data, pos + 10)[0]
            entry.data_crc = struct.unpack_from('<I', index_data, pos + 14)[0]
            pos += extra_size

            self.entries.append(entry)

    def list_folders(self) -> dict[str, int]:
        from collections import Counter
        folders = Counter()
        for e in self.entries:
            parts = e.path.replace('\\', '/').split('/')
            folders[parts[0] if len(parts) > 1 else '(root)'] += 1
        return dict(folders.most_common())

    def list_entries(self, prefix: str = '') -> list[YPFEntry]:
        pn = prefix.replace('\\', '/').rstrip('/')
        if not pn:
            return list(self.entries)
        pn += '/'
        return [e for e in self.entries
                if e.path.replace('\\', '/').startswith(pn)]

    def extract(self, entry: YPFEntry) -> bytes:
        with open(self.filepath, 'rb') as f:
            f.seek(entry.data_offset)
            raw = f.read(entry.comp_size)
        if entry.is_compressed:
            try:
                return zlib.decompress(raw)
            except zlib.error:
                return zlib.decompress(raw, -15)
        return raw

    def extract_to_file(self, entry: YPFEntry, output_dir: str) -> Path:
        out = Path(output_dir) / entry.path.replace('\\', '/')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(self.extract(entry))
        return out

    def extract_folder(self, folder_prefix: str, output_dir: str,
                       callback=None) -> list[Path]:
        entries = self.list_entries(folder_prefix)
        results = []
        for i, entry in enumerate(entries):
            path = self.extract_to_file(entry, output_dir)
            results.append(path)
            if callback:
                callback(i + 1, len(entries), entry.path)
        return results

    def find_entry(self, path: str) -> Optional[YPFEntry]:
        n = path.replace('\\', '/')
        for e in self.entries:
            if e.path.replace('\\', '/') == n:
                return e
        return None

    def update_entry(self, entry: YPFEntry, new_data: bytes):
        if entry.is_compressed:
            new_comp = zlib.compress(new_data, 9)
        else:
            new_comp = new_data

        new_decomp = len(new_data)
        new_comp_sz = len(new_comp)

        with open(self.filepath, 'r+b') as f:
            if new_comp_sz <= entry.comp_size:
                f.seek(entry.data_offset)
                f.write(new_comp)
                if new_comp_sz < entry.comp_size:
                    f.write(b'\x00' * (entry.comp_size - new_comp_sz))
            else:
                f.seek(0, 2)
                new_offset = f.tell()
                f.write(new_comp)
                f.seek(entry._meta_file_offset + 10)
                f.write(struct.pack('<I', new_offset))
                entry.data_offset = new_offset

            f.seek(entry._meta_file_offset + 2)
            f.write(struct.pack('<I', new_decomp))
            f.write(struct.pack('<I', new_comp_sz))

        entry.decomp_size = new_decomp
        entry.comp_size = new_comp_sz
