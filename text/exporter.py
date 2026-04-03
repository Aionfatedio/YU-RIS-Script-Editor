import json
from pathlib import Path
from yuris_toolkit.core.ystb import YSTBFile, TextEntry


class TextExporter:
    @staticmethod
    def export_triline(ystb: YSTBFile, output_path: str,
                       source_encoding: str = 'shift_jis'):
        texts = ystb.extract_texts(source_encoding)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            for entry in texts:
                if entry.is_option:
                    f.write(f'[{entry.args_offset}]opt\n')
                else:
                    f.write(f'[{entry.args_offset}]\n')
                f.write(f'ORI={entry.text}\n')
                f.write(f'TR1={entry.text}\n')
                f.write(f'TR2={entry.text}\n')

        return len(texts)

    @staticmethod
    def export_json(ystb: YSTBFile, output_path: str,
                    source_encoding: str = 'shift_jis',
                    name_delimiters: tuple = ('\u3010', '\u3011')):
        texts = ystb.extract_texts(source_encoding)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        result = []
        left_delim, right_delim = name_delimiters

        for entry in texts:
            item = {'_offset': entry.args_offset,
                    '_is_option': entry.is_option}

            text = entry.text
            if right_delim in text:
                parts = text.split(right_delim, 1)
                name = parts[0]
                if name.startswith(left_delim):
                    name = name[len(left_delim):]
                item['name'] = name
                item['message'] = parts[1]
            else:
                item['name'] = ''
                item['message'] = text

            result.append(item)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        return len(result)

    @staticmethod
    def export_raw(ystb: YSTBFile, output_path: str,
                   source_encoding: str = 'shift_jis'):
        texts = ystb.extract_texts(source_encoding)
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            for entry in texts:
                prefix = '[OPT] ' if entry.is_option else ''
                f.write(f'{prefix}{entry.text}\n')

        return len(texts)
