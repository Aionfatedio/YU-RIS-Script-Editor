import struct
from pathlib import Path
from typing import Optional
from .encoding import xor_block, Encoding

HEADER_SIZE = 0x20
MAGIC = b'YSTB'
ARGS_ENTRY_SIZE = 12


class TextEntry:
    __slots__ = ('args_offset', 'text', 'is_option', 'raw_data')

    def __init__(self, args_offset: int, text: str, is_option: bool = False,
                 raw_data: bytes = b''):
        self.args_offset = args_offset
        self.text = text
        self.is_option = is_option
        self.raw_data = raw_data


class YSTBFile:
    def __init__(self):
        self.version: int = 0
        self.is_v2: bool = False

        self._header_raw: bytes = b''

        # V5 
        self.inst_entry_count: int = 0
        self.inst_index: bytes = b''
        self.args_index: bytearray = bytearray()
        self.args_data: bytes = b''
        self.line_numbers: bytes = b''

        # V2 
        self.code_segment: bytearray = bytearray()
        self.args_segment: bytes = b''
        self.v2_args_seg_offset: int = 0

        self._append_region: bytearray = bytearray()

    @classmethod
    def from_file(cls, filepath: str, key: int = 0) -> 'YSTBFile':
        data = Path(filepath).read_bytes()
        return cls.from_bytes(data, key)

    @classmethod
    def from_bytes(cls, data: bytes, key: int = 0) -> 'YSTBFile':
        if len(data) < HEADER_SIZE:
            raise ValueError("数据大小异常")
        if data[:4] != MAGIC:
            raise ValueError(f"文件头异常: 意外的文件头 {data[:4]}")

        obj = cls()
        obj._header_raw = bytearray(data[:HEADER_SIZE])
        obj.version = struct.unpack_from('<I', data, 4)[0]
        obj.is_v2 = 200 < obj.version < 300

        if key:
            data = obj._decrypt(data, key)

        if obj.is_v2:
            obj._parse_v2(data)
        else:
            obj._parse_v5(data)

        return obj

    def _decrypt(self, data: bytes, key: int) -> bytes:
        key_bytes = struct.pack('<I', key & 0xFFFFFFFF)
        header = data[:HEADER_SIZE]
        result = bytearray(header)

        if self.is_v2:
            code_seg_size = struct.unpack_from('<I', header, 0x08)[0]
            args_seg_size = struct.unpack_from('<I', header, 0x0C)[0]
            offset = HEADER_SIZE
            for seg_size in [code_seg_size, args_seg_size]:
                seg = data[offset:offset + seg_size]
                result.extend(xor_block(seg, key_bytes))
                offset += seg_size
        else:
            inst_idx_size = struct.unpack_from('<I', header, 0x0C)[0]
            args_idx_size = struct.unpack_from('<I', header, 0x10)[0]
            args_data_size = struct.unpack_from('<I', header, 0x14)[0]
            line_num_size = struct.unpack_from('<I', header, 0x18)[0]
            offset = HEADER_SIZE
            for seg_size in [inst_idx_size, args_idx_size,
                             args_data_size, line_num_size]:
                seg = data[offset:offset + seg_size]
                result.extend(xor_block(seg, key_bytes))
                offset += seg_size

        return bytes(result)

    def _encrypt(self, data: bytes, key: int) -> bytes:
        return self._decrypt(data, key)

    def _parse_v5(self, data: bytes):
        self.inst_entry_count = struct.unpack_from('<I', data, 0x08)[0]
        inst_idx_size = struct.unpack_from('<I', data, 0x0C)[0]
        args_idx_size = struct.unpack_from('<I', data, 0x10)[0]
        args_data_size = struct.unpack_from('<I', data, 0x14)[0]
        line_num_size = struct.unpack_from('<I', data, 0x18)[0]

        offset = HEADER_SIZE
        self.inst_index = data[offset:offset + inst_idx_size]
        offset += inst_idx_size

        self.args_index = bytearray(data[offset:offset + args_idx_size])
        offset += args_idx_size

        self.args_data = data[offset:offset + args_data_size]
        offset += args_data_size

        self.line_numbers = data[offset:offset + line_num_size]

    def _parse_v2(self, data: bytes):
        code_seg_size = struct.unpack_from('<I', data, 0x08)[0]
        args_seg_size = struct.unpack_from('<I', data, 0x0C)[0]
        self.v2_args_seg_offset = struct.unpack_from('<I', data, 0x10)[0]

        offset = HEADER_SIZE
        self.code_segment = bytearray(data[offset:offset + code_seg_size])
        offset += code_seg_size

        self.args_segment = data[offset:offset + args_seg_size]

    @staticmethod
    def guess_key(filepath: str) -> int:
        data = Path(filepath).read_bytes()
        return YSTBFile.guess_key_from_bytes(data)

    @staticmethod
    def guess_key_from_bytes(data: bytes) -> int:
        if len(data) < HEADER_SIZE or data[:4] != MAGIC:
            return 0
        version = struct.unpack_from('<I', data, 4)[0]

        if 200 < version < 300:
            code_seg_size = struct.unpack_from('<I', data, 0x08)[0]
            args_seg_size = struct.unpack_from('<I', data, 0x0C)[0]
            if code_seg_size + args_seg_size < 0x10:
                return 0
            pos = 0x2C
            if pos + 4 > len(data):
                return 0
            return struct.unpack_from('<I', data, pos)[0]

        args_data_size = struct.unpack_from('<I', data, 0x14)[0]
        if args_data_size == 0:
            return 0
        inst_idx_size = struct.unpack_from('<I', data, 0x0C)[0]
        args_idx_size = struct.unpack_from('<I', data, 0x10)[0]
        args_start = HEADER_SIZE + inst_idx_size
        num_entries = args_idx_size // ARGS_ENTRY_SIZE
        if num_entries == 0:
            return 0

        from collections import Counter
        candidates = Counter()
        scan_count = min(num_entries, 200)
        for i in range(scan_count):
            pos = args_start + i * ARGS_ENTRY_SIZE + 8  
            if pos + 4 > len(data):
                break
            val = struct.unpack_from('<I', data, pos)[0]
            candidates[val] += 1

        if not candidates:
            return 0
        return candidates.most_common(1)[0][0]

    def _read_args_data(self, size: int, offset: int) -> Optional[bytes]:
        total_data = self.args_data + bytes(self._append_region)
        if offset + size > len(total_data):
            return None
        return total_data[offset:offset + size]

    def detect_text_encoding(self) -> str:
        samples = []
        if not self.is_v2:
            args_count = len(self.args_index) // ARGS_ENTRY_SIZE
            for i in range(args_count):
                base = i * ARGS_ENTRY_SIZE
                arg_id = struct.unpack_from('<H', self.args_index, base)[0]
                arg_type = struct.unpack_from('<H', self.args_index, base + 2)[0]
                size = struct.unpack_from('<I', self.args_index, base + 4)[0]
                offset = struct.unpack_from('<I', self.args_index, base + 8)[0]
                if arg_id == 0 and arg_type == 0 and 0 < size <= 4096:
                    data = self._read_args_data(size, offset)
                    if data and data[0] != 0x4D and data[:2] != b'H\x03' \
                            and b'\x00' not in data and b'cg' not in data:
                        clean = data.replace(Encoding.RUBY_MARKER, b'')
                        if clean:
                            samples.append(clean)
                if len(samples) >= 30:
                    break

        if not samples:
            return 'shift_jis'

        blob = b''.join(samples)

        try:
            blob.decode('utf-8', errors='strict')
            if any(b > 0x7F for b in blob):
                return 'utf-8'
        except UnicodeDecodeError:
            pass

        sjis_text, gbk_text = None, None
        try:
            sjis_text = blob.decode('shift_jis', errors='strict')
        except UnicodeDecodeError:
            pass
        try:
            gbk_text = blob.decode('gbk', errors='strict')
        except UnicodeDecodeError:
            pass

        if sjis_text is not None and gbk_text is None:
            return 'shift_jis'
        if gbk_text is not None and sjis_text is None:
            return 'gbk'

        if sjis_text is not None:
            has_kana = any('\u3040' <= c <= '\u30FF' for c in sjis_text)
            if has_kana:
                return 'shift_jis'
            return 'gbk'

        return 'shift_jis'

    def extract_texts(self, encoding: str = 'shift_jis') -> list[TextEntry]:
        if self.is_v2:
            return self._extract_texts_v2(encoding)
        return self._extract_texts_v5(encoding)

    def _extract_texts_v5(self, encoding: str) -> list[TextEntry]:
        texts = []
        opt_flag = False
        args_count = len(self.args_index) // ARGS_ENTRY_SIZE

        sel_set_marker = b'\x4D\x0C\x00\x22\x45\x53\x2E\x53\x45\x4C\x2E\x53\x45\x54\x22'

        for i in range(args_count):
            base = i * ARGS_ENTRY_SIZE
            arg_id = struct.unpack_from('<H', self.args_index, base)[0]
            arg_type = struct.unpack_from('<H', self.args_index, base + 2)[0]
            size = struct.unpack_from('<I', self.args_index, base + 4)[0]
            offset = struct.unpack_from('<I', self.args_index, base + 8)[0]

            if size == 0 or size > 4096:
                opt_flag = False
                continue

            data = self._read_args_data(size, offset)
            if data is None:
                continue

            if opt_flag:
                if len(data) > 4 and data[0] == 0x4D:
                    inner = data[4:-1] if len(data) > 5 else b''
                    if inner:
                        try:
                            text = inner.decode(encoding, errors='replace')
                            texts.append(TextEntry(base, text, is_option=True,
                                                   raw_data=data))
                        except Exception:
                            pass
                    else:
                        opt_flag = False
                else:
                    opt_flag = False
                continue

            if arg_type == 3 and data == sel_set_marker:
                opt_flag = True
                continue

            if arg_id == 0 and arg_type == 0:
                if (data[0] == 0x4D or data[:2] == b'H\x03'
                        or b'\x00' in data or b'cg' in data):
                    continue

                clean_data = data.replace(Encoding.RUBY_MARKER, b'')
                try:
                    text = clean_data.decode(encoding)
                    texts.append(TextEntry(base, text, raw_data=data))
                except UnicodeDecodeError:
                    try:
                        text = clean_data.decode(encoding, errors='replace')
                        texts.append(TextEntry(base, text, raw_data=data))
                    except Exception:
                        pass

        return texts

    def _extract_texts_v2(self, encoding: str) -> list[TextEntry]:
        texts = []
        code = self.code_segment
        res = self.args_segment
        pos = 0

        while pos < len(code):
            op = code[pos]
            argc = code[pos + 1] if pos + 1 < len(code) else 0

            if op == 0x38:
                pos += 0xA
                continue

            block_size = argc * 12 + 6

            if op == 0x54 and argc >= 1:
                entry_offset = pos + 6
                arg_size = struct.unpack_from('<I', code, entry_offset + 4)[0]
                arg_rva = struct.unpack_from('<I', code, entry_offset + 8)[0]

                if arg_rva + arg_size <= len(res):
                    data = res[arg_rva:arg_rva + arg_size]
                    try:
                        text = data.decode(encoding, errors='replace')
                        texts.append(TextEntry(entry_offset, text,
                                               raw_data=data))
                    except Exception:
                        pass

            pos += block_size

        return texts

    def insert_text(self, args_offset: int, text: str,
                    target_encoding: str = 'gbk',
                    is_option: bool = False):
        from .encoding import encode_text_for_game

        if is_option:
            self._insert_option(args_offset, text, target_encoding)
            return

        data_offset = len(self.args_data) + len(self._append_region)
        encoded = encode_text_for_game(text, target_encoding)
        data_len = len(encoded)

        self._append_region.extend(encoded)
        self._append_region.append(0x00)

        if self.is_v2:
            struct.pack_into('<I', self.code_segment,
                             args_offset + 4, data_len)
            struct.pack_into('<I', self.code_segment,
                             args_offset + 8, data_offset)
        else:
            struct.pack_into('<I', self.args_index,
                             args_offset + 4, data_len)
            struct.pack_into('<I', self.args_index,
                             args_offset + 8, data_offset)

    def _insert_option(self, args_offset: int, text: str,
                       target_encoding: str):
        from .encoding import encode_text_for_game

        data_offset = len(self.args_data) + len(self._append_region)
        encoded = encode_text_for_game(text, target_encoding)
        wrapped = (b'\x4D'
                   + struct.pack('<H', len(encoded) + 2)
                   + b'\x22' + encoded + b'\x22')
        data_len = len(wrapped)

        self._append_region.extend(wrapped)
        self._append_region.append(0x00)

        if self.is_v2:
            struct.pack_into('<I', self.code_segment,
                             args_offset + 4, data_len)
            struct.pack_into('<I', self.code_segment,
                             args_offset + 8, data_offset)
        else:
            struct.pack_into('<I', self.args_index,
                             args_offset + 4, data_len)
            struct.pack_into('<I', self.args_index,
                             args_offset + 8, data_offset)

    def build(self) -> bytes:
        header = bytearray(self._header_raw)

        if self.is_v2:
            new_args_size = len(self.args_segment) + len(self._append_region)
            struct.pack_into('<I', header, 0x0C, new_args_size)
            return bytes(header + self.code_segment
                         + self.args_segment + self._append_region)
        else:
            new_args_data_size = len(self.args_data) + len(self._append_region)
            struct.pack_into('<I', header, 0x14, new_args_data_size)
            return bytes(header + self.inst_index + self.args_index
                         + self.args_data + self._append_region
                         + self.line_numbers)

    def save(self, filepath: str, key: int = 0):
        data = self.build()
        if key:
            data = self._encrypt(data, key)
        Path(filepath).write_bytes(data)

    def reset_append(self):
        self._append_region = bytearray()
