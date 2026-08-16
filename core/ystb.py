import struct
from collections import Counter
from pathlib import Path

from .encoding import Encoding, detect_text_encoding, xor_block

HEADER_SIZE = 0x20
MAGIC = b'YSTB'
ARGS_ENTRY_SIZE = 12


class TextEntry:
    __slots__ = ('args_offset', 'is_option', 'raw_data', 'text')

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
        self.trailing_data: bytes = b''

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

        if obj.is_v2:
            sizes = [
                struct.unpack_from('<I', data, 0x08)[0],
                struct.unpack_from('<I', data, 0x0C)[0],
            ]
        else:
            sizes = [
                struct.unpack_from('<I', data, 0x0C)[0],
                struct.unpack_from('<I', data, 0x10)[0],
                struct.unpack_from('<I', data, 0x14)[0],
                struct.unpack_from('<I', data, 0x18)[0],
            ]
        if HEADER_SIZE + sum(sizes) > len(data):
            raise ValueError("YSTB 段大小超出文件范围")

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

        result.extend(data[offset:])

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
        offset += line_num_size
        self.trailing_data = data[offset:]

    def _parse_v2(self, data: bytes):
        code_seg_size = struct.unpack_from('<I', data, 0x08)[0]
        args_seg_size = struct.unpack_from('<I', data, 0x0C)[0]
        self.v2_args_seg_offset = struct.unpack_from('<I', data, 0x10)[0]

        offset = HEADER_SIZE
        self.code_segment = bytearray(data[offset:offset + code_seg_size])
        offset += code_seg_size

        self.args_segment = data[offset:offset + args_seg_size]
        offset += args_seg_size
        self.trailing_data = data[offset:]

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
            return YSTBFile._guess_v2_key(data)
        return YSTBFile._guess_v5_key(data)

    @staticmethod
    def _guess_v5_key(data: bytes) -> int:
        inst_idx_size = struct.unpack_from('<I', data, 0x0C)[0]
        args_idx_size = struct.unpack_from('<I', data, 0x10)[0]
        args_data_size = struct.unpack_from('<I', data, 0x14)[0]
        args_start = HEADER_SIZE + inst_idx_size
        if (args_idx_size == 0 or args_idx_size % ARGS_ENTRY_SIZE
                or args_start + args_idx_size > len(data)):
            return 0

        evidence: Counter[int] = Counter()
        for base in range(args_start, args_start + args_idx_size,
                          ARGS_ENTRY_SIZE):
            # Text entries use arg_id=0 and arg_type=0. Their encrypted first
            # dword therefore is the XOR key itself, so each entry can validate
            # its own candidate against the encrypted size and data offset.
            key = struct.unpack_from('<I', data, base)[0]
            size = struct.unpack_from('<I', data, base + 4)[0] ^ key
            offset = struct.unpack_from('<I', data, base + 8)[0] ^ key
            if (0 < size <= 4096 and offset <= args_data_size
                    and size <= args_data_size - offset):
                evidence[key] += 1

        return evidence.most_common(1)[0][0] if evidence else 0

    @staticmethod
    def _guess_v2_key(data: bytes) -> int:
        code_size = struct.unpack_from('<I', data, 0x08)[0]
        args_size = struct.unpack_from('<I', data, 0x0C)[0]
        if HEADER_SIZE + code_size + args_size > len(data) or code_size < 2:
            return 0
        encrypted_code = data[HEADER_SIZE:HEADER_SIZE + code_size]
        candidates = {0}
        for pos in range(0, min(len(encrypted_code) - 3, 0x100), 4):
            candidates.add(struct.unpack_from('<I', encrypted_code, pos)[0])
        if len(data) >= 0x30:
            candidates.add(struct.unpack_from('<I', data, 0x2C)[0])
        ranked = sorted((YSTBFile._score_v2_key(
                            encrypted_code, args_size, key), key)
                        for key in candidates)
        best_score, best_key = ranked[-1]
        zero_score = next(score for score, key in ranked if key == 0)
        if zero_score >= best_score - 0.5:
            return 0
        return best_key if best_score > 0 else 0

    @staticmethod
    def _score_v2_key(encrypted_code: bytes, args_size: int,
                      key: int) -> float:
        code = xor_block(encrypted_code, struct.pack('<I', key))
        pos = 0
        blocks = 0
        structure_score = 0.0
        empty_blocks = 0
        while pos + 2 <= len(code) and blocks < 128:
            op = code[pos]
            argc = code[pos + 1]
            if op == 0x38:
                block_size = 0xA
            else:
                block_size = argc * 12 + 6
            if block_size < 6 or pos + block_size > len(code):
                break

            if op == 0 and argc == 0:
                empty_blocks += 1
            if code[pos + 2:pos + 6] == b'\x00' * 4:
                structure_score += 0.05

            if op != 0x38:
                for arg_index in range(argc):
                    arg_pos = pos + 6 + arg_index * ARGS_ENTRY_SIZE
                    arg_id, arg_type, size, offset = struct.unpack_from(
                        '<HHII', code, arg_pos)
                    structure_score += 0.15 if arg_id <= 0x1000 else -1.0
                    structure_score += 0.25 if arg_type <= 0x40 else -1.5
                    in_range = (offset <= args_size
                                and size <= args_size - offset)
                    if op == 0x54:
                        structure_score += (
                            4.0 if 0 < size <= 4096 and in_range else -6.0)
                    elif size == 0 or in_range:
                        structure_score += 0.15
                    else:
                        structure_score -= 0.5
            pos += block_size
            blocks += 1
        coverage = pos / len(code) if code else 0.0
        return (coverage * 10.0 + blocks * 0.02 + structure_score
                - empty_blocks * 0.15)

    def _read_args_data(self, size: int, offset: int) -> bytes | None:
        total_data = self.args_data + bytes(self._append_region)
        if offset + size > len(total_data):
            return None
        return total_data[offset:offset + size]

    def detect_text_encoding(self, preferred: str | None = Encoding.SJIS) -> str:
        samples = []
        if self.is_v2:
            code = self.code_segment
            pos = 0
            while pos + 2 <= len(code) and len(samples) < 30:
                op = code[pos]
                argc = code[pos + 1]
                block_size = 0xA if op == 0x38 else argc * 12 + 6
                if block_size < 6 or pos + block_size > len(code):
                    break
                if op == 0x54 and argc >= 1:
                    entry_offset = pos + 6
                    if entry_offset + 12 <= len(code):
                        size = struct.unpack_from(
                            '<I', code, entry_offset + 4)[0]
                        offset = struct.unpack_from(
                            '<I', code, entry_offset + 8)[0]
                        if (0 < size <= 4096 and offset <= len(self.args_segment)
                                and size <= len(self.args_segment) - offset):
                            samples.append(
                                self.args_segment[offset:offset + size])
                pos += block_size
        else:
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
                            and b'\x00' not in data and not data.startswith(b'cg'):
                        clean = data.replace(Encoding.RUBY_MARKER, b'')
                        if clean:
                            samples.append(clean)
                if len(samples) >= 30:
                    break

        if not samples:
            return preferred or Encoding.SJIS

        return detect_text_encoding(b'\n'.join(samples), preferred=preferred)

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
                            text = inner.decode(encoding)
                            texts.append(TextEntry(base, text, is_option=True,
                                                   raw_data=data))
                        except UnicodeDecodeError:
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
                        or b'\x00' in data or data.startswith(b'cg')):
                    continue

                clean_data = data.replace(Encoding.RUBY_MARKER, b'')
                try:
                    text = clean_data.decode(encoding)
                    texts.append(TextEntry(base, text, raw_data=data))
                except UnicodeDecodeError:
                    pass

        return texts

    def _extract_texts_v2(self, encoding: str) -> list[TextEntry]:
        texts = []
        code = self.code_segment
        res = self.args_segment
        pos = 0

        while pos < len(code):
            if pos + 2 > len(code):
                break
            op = code[pos]
            argc = code[pos + 1]

            if op == 0x38:
                if pos + 0xA > len(code):
                    break
                pos += 0xA
                continue

            block_size = argc * 12 + 6
            if block_size < 6 or pos + block_size > len(code):
                break

            if op == 0x54 and argc >= 1:
                entry_offset = pos + 6
                if entry_offset + 12 > len(code):
                    break
                arg_size = struct.unpack_from('<I', code, entry_offset + 4)[0]
                arg_rva = struct.unpack_from('<I', code, entry_offset + 8)[0]

                if arg_rva + arg_size <= len(res):
                    data = res[arg_rva:arg_rva + arg_size]
                    try:
                        text = data.decode(encoding)
                        texts.append(TextEntry(entry_offset, text,
                                               raw_data=data))
                    except UnicodeDecodeError:
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

        base_size = len(self.args_segment) if self.is_v2 else len(self.args_data)
        data_offset = base_size + len(self._append_region)
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

        base_size = len(self.args_segment) if self.is_v2 else len(self.args_data)
        data_offset = base_size + len(self._append_region)
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
                         + self.args_segment + self._append_region
                         + self.trailing_data)
        else:
            new_args_data_size = len(self.args_data) + len(self._append_region)
            struct.pack_into('<I', header, 0x14, new_args_data_size)
            return bytes(header + self.inst_index + self.args_index
                         + self.args_data + self._append_region
                         + self.line_numbers + self.trailing_data)

    def to_bytes(self, key: int = 0) -> bytes:
        data = self.build()
        return self._encrypt(data, key) if key else data

    def save(self, filepath: str, key: int = 0):
        Path(filepath).write_bytes(self.to_bytes(key))

    def reset_append(self):
        self._append_region = bytearray()
