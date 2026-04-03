import struct
from pathlib import Path
from typing import Optional


class YSTLEntry:
    __slots__ = ('sequence', 'path', 'text_count', 'variable_count',
                 'label_count')

    def __init__(self):
        self.sequence: int = 0
        self.path: str = ''
        self.text_count: int = 0
        self.variable_count: int = 0
        self.label_count: int = 0

    @property
    def ybn_name(self) -> str:
        return f"yst{self.sequence:05d}.ybn"

    @property
    def has_text(self) -> bool:
        return self.text_count > 0


class YSTLFile:
    def __init__(self):
        self.version: int = 0
        self.is_v5: bool = False
        self.entries: list[YSTLEntry] = []

    @classmethod
    def from_file(cls, filepath: str) -> 'YSTLFile':
        data = Path(filepath).read_bytes()
        return cls.from_bytes(data)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'YSTLFile':
        if len(data) < 12:
            raise ValueError("数据大小异常")
        if data[:4] != b'YSTL':
            raise ValueError(f"文件头异常: 意外的文件头 {data[:4]}")

        obj = cls()
        obj.version = struct.unpack_from('<I', data, 4)[0]
        entry_count = struct.unpack_from('<I', data, 8)[0]
        obj.is_v5 = obj.version >= 300

        pos = 12
        for _ in range(entry_count):
            entry = YSTLEntry()
            entry.sequence = struct.unpack_from('<I', data, pos)[0]
            path_size = struct.unpack_from('<I', data, pos + 4)[0]
            pos += 8

            path_bytes = data[pos:pos + path_size]
            try:
                entry.path = path_bytes.decode('shift_jis').replace('\\', '/')
            except UnicodeDecodeError:
                entry.path = path_bytes.decode('shift_jis', errors='replace').replace('\\', '/')
            pos += path_size

            if obj.is_v5:
                pos += 8  
                entry.variable_count = struct.unpack_from('<I', data, pos)[0]
                entry.label_count = struct.unpack_from('<I', data, pos + 4)[0]
                entry.text_count = struct.unpack_from('<I', data, pos + 8)[0]
                pos += 12
            else:
                pos += 16

            obj.entries.append(entry)

        return obj

    def get_text_scripts(self) -> list[YSTLEntry]:
        if self.is_v5:
            return [e for e in self.entries if e.text_count > 0]
        return list(self.entries)

    def get_path(self, sequence: int) -> Optional[str]:
        for entry in self.entries:
            if entry.sequence == sequence:
                return entry.path
        return None

    def get_entry_by_ybn(self, ybn_name: str) -> Optional[YSTLEntry]:
        for entry in self.entries:
            if entry.ybn_name == ybn_name:
                return entry
        return None

    def get_userscript_entries(self) -> list[YSTLEntry]:
        return [e for e in self.entries
                if 'userscript' in e.path.lower()]
