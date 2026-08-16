import struct
from pathlib import Path


class YSCMArg:
    __slots__ = ('name', 'value0', 'value1')

    def __init__(self, name: str, value0: int, value1: int):
        self.name = name
        self.value0 = value0
        self.value1 = value1


class YSCMCommand:
    __slots__ = ('args', 'name', 'opcode')

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
        if command_count > len(data):
            raise ValueError("YSCM 命令数量异常")

        pos = 16  
        for opcode in range(command_count):
            if pos >= len(data):
                raise ValueError(f"YSCM 命令 {opcode} 超出文件范围")
            name_end = data.find(b'\x00', pos)
            if name_end < 0:
                raise ValueError(f"YSCM 命令 {opcode} 名称未终止")
            try:
                name = data[pos:name_end].decode('ascii')
            except UnicodeDecodeError as exc:
                raise ValueError(f"YSCM 命令 {opcode} 名称编码异常") from exc
            pos = name_end + 1

            cmd = YSCMCommand(opcode, name)

            if pos >= len(data):
                raise ValueError(f"YSCM 命令 {opcode} 缺少参数数量")
            arg_count = data[pos]
            pos += 1

            for arg_index in range(arg_count):
                arg_name_end = data.find(b'\x00', pos)
                if arg_name_end < 0:
                    raise ValueError(
                        f"YSCM 命令 {opcode} 参数 {arg_index} 名称未终止")
                try:
                    arg_name = data[pos:arg_name_end].decode('ascii')
                except UnicodeDecodeError as exc:
                    raise ValueError(
                        f"YSCM 命令 {opcode} 参数名称编码异常") from exc
                pos = arg_name_end + 1
                if pos + 2 > len(data):
                    raise ValueError(
                        f"YSCM 命令 {opcode} 参数 {arg_index} 数据不完整")
                v0 = data[pos]
                v1 = data[pos + 1]
                pos += 2
                cmd.args.append(YSCMArg(arg_name, v0, v1))

            obj.commands.append(cmd)

        return obj

    def get_opcode(self, command_name: str) -> int | None:
        for cmd in self.commands:
            if cmd.name == command_name:
                return cmd.opcode
        return None

    def get_command(self, opcode: int) -> YSCMCommand | None:
        if 0 <= opcode < len(self.commands):
            return self.commands[opcode]
        return None

    @property
    def word_opcode(self) -> int | None:
        return self.get_opcode("WORD")
