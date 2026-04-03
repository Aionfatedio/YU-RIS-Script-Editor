import struct
from pathlib import Path
from typing import Optional


class YSCMArg:
    __slots__ = ('name', 'value0', 'value1')

    def __init__(self, name: str, value0: int, value1: int):
        self.name = name
        self.value0 = value0
        self.value1 = value1


class YSCMCommand:
    __slots__ = ('opcode', 'name', 'args')

    def __init__(self, opcode: int, name: str):
        self.opcode = opcode
        self.name = name
        self.args: list[YSCMArg] = []


class YSCMFile:
    def __init__(self):
        self.version: int = 0
        self.commands: list[YSCMCommand] = []

    @classmethod
    def from_file(cls, filepath: str) -> 'YSCMFile':
        data = Path(filepath).read_bytes()
        return cls.from_bytes(data)

    @classmethod
    def from_bytes(cls, data: bytes) -> 'YSCMFile':
        if len(data) < 16:
            raise ValueError("数据大小异常")
        if data[:4] != b'YSCM':
            raise ValueError(f"文件头异常: 意外的文件头 {data[:4]}")

        obj = cls()
        obj.version = struct.unpack_from('<I', data, 4)[0]
        command_count = struct.unpack_from('<I', data, 8)[0]

        pos = 16  
        for opcode in range(command_count):
            name_end = data.index(b'\x00', pos)
            name = data[pos:name_end].decode('ascii')
            pos = name_end + 1

            cmd = YSCMCommand(opcode, name)

            arg_count = data[pos]
            pos += 1

            for _ in range(arg_count):
                arg_name_end = data.index(b'\x00', pos)
                arg_name = data[pos:arg_name_end].decode('ascii')
                pos = arg_name_end + 1
                v0 = data[pos]
                v1 = data[pos + 1]
                pos += 2
                cmd.args.append(YSCMArg(arg_name, v0, v1))

            obj.commands.append(cmd)

        return obj

    def get_opcode(self, command_name: str) -> Optional[int]:
        for cmd in self.commands:
            if cmd.name == command_name:
                return cmd.opcode
        return None

    def get_command(self, opcode: int) -> Optional[YSCMCommand]:
        if 0 <= opcode < len(self.commands):
            return self.commands[opcode]
        return None

    @property
    def word_opcode(self) -> Optional[int]:
        return self.get_opcode("WORD")
