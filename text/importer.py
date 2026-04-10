import json
from pathlib import Path
from core.ystb import YSTBFile

class TextImporter:
    @staticmethod
    def detect_format(filepath: str) -> str:
        path = Path(filepath)
        if path.suffix.lower() == '.json':
            return 'json'
        with open(filepath, 'r', encoding='utf-8') as f:
            first_line = f.readline().strip()
            if first_line.startswith('[') and first_line.endswith(']'):
                second_line = f.readline().strip()
                if second_line.startswith('ORI='):
                    return 'triline'
            if first_line in ('[', '{'):
                return 'json'
        return 'triline'

    @staticmethod
    def import_triline(ystb: YSTBFile, triline_path: str,
                       target_encoding: str = 'gbk'):
        count = 0
        with open(triline_path, 'r', encoding='utf-8') as f:
            current_offset = -1
            is_opt = False

            for line in f:
                line = line.rstrip('\n')

                if line.startswith('[') and ('ORI=' not in line
                                             and 'TR1=' not in line
                                             and 'TR2=' not in line):
                    is_opt = 'opt' in line
                    bracket_end = line.index(']')
                    offset_str = line[1:bracket_end]
                    try:
                        current_offset = int(offset_str)
                    except ValueError:
                        current_offset = -1
                    continue

                if line.startswith('TR2=') and current_offset >= 0:
                    trans_text = line[4:]
                    if trans_text:
                        ystb.insert_text(current_offset, trans_text,
                                         target_encoding, is_opt)
                        count += 1

        return count

    @staticmethod
    def import_json(ystb: YSTBFile, json_path: str,
                    triline_path: str = '',
                    target_encoding: str = 'gbk',
                    name_delimiters: tuple = ('\u3010', '\u3011')):
        left_delim, right_delim = name_delimiters

        with open(json_path, 'r', encoding='utf-8') as f:
            items = json.load(f)
        offsets = []
        opt_flags = []
        if triline_path and Path(triline_path).exists():
            with open(triline_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('[') and ('ORI=' not in line
                                                 and 'TR1=' not in line
                                                 and 'TR2=' not in line):
                        is_opt = 'opt' in line
                        bracket_end = line.index(']')
                        offset_str = line[1:bracket_end]
                        try:
                            offsets.append(int(offset_str))
                            opt_flags.append(is_opt)
                        except ValueError:
                            pass

        count = 0
        for i, item in enumerate(items):
            trans = item.get('post_zh_preview', '') or item.get('message', '')
            name = item.get('name', '')
            is_opt = item.get('_is_option', False)

            if not trans:
                continue

            if name:
                trans = f'{left_delim}{name}{right_delim}{trans}'

            if i < len(offsets):
                offset = offsets[i]
                is_opt = opt_flags[i] if i < len(opt_flags) else is_opt
            else:
                offset = item.get('_offset', -1)

            if offset < 0:
                continue

            ystb.insert_text(offset, trans, target_encoding, is_opt)
            count += 1

        return count

    @staticmethod
    def import_auto(ystb: YSTBFile, filepath: str,
                    target_encoding: str = 'gbk', **kwargs) -> int:
        fmt = TextImporter.detect_format(filepath)
        if fmt == 'json':
            return TextImporter.import_json(ystb, filepath,
                                            target_encoding=target_encoding,
                                            **kwargs)
        return TextImporter.import_triline(ystb, filepath,
                                           target_encoding=target_encoding)
