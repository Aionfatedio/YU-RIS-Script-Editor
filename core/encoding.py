from __future__ import annotations

import codecs
import struct
from typing import ClassVar


class Encoding:
    SJIS = 'shift_jis'
    GBK = 'gbk'
    BIG5 = 'big5'
    UTF8 = 'utf-8'

    SUPPORTED: ClassVar[tuple[str, ...]] = (SJIS, GBK, BIG5, UTF8)
    SJIS_TO_GBK_REPLACE: ClassVar[dict[str, str]] = {
        '\u266a': '', '\u301c': '~',
    }
    SJIS_KEEP_CHARS: ClassVar[tuple[str, ...]] = ('\uff20', '\uff03')
    RUBY_MARKER = b'\x87\x55'


_ALIASES = {
    'sjis': Encoding.SJIS,
    'shift-jis': Encoding.SJIS,
    'shift_jis': Encoding.SJIS,
    'cp932': Encoding.SJIS,
    'ms932': Encoding.SJIS,
    'utf8': Encoding.UTF8,
    'utf-8-sig': Encoding.UTF8,
    'gb2312': Encoding.GBK,
    'gb18030': Encoding.GBK,
    'big5hkscs': Encoding.BIG5,
}

_JAPANESE_PUNCTUATION = set('　「」『』【】（）［］・ー〜…‥！？。、')
_SIMPLIFIED_HINTS = set(
    '这为个后发里过还么们从与对时会说让无机开关国门体书东车云'
    '见观听读写话边变点画万亿广义产业务实认应当种样级线网'
)
_TRADITIONAL_HINTS = set(
    '這為個後發裡過還麼們從與對時會說讓無機開關國門體書東車雲'
    '見觀聽讀寫話邊變點畫萬億廣義產業務實認應當種樣級線網'
)


def normalize_encoding(value: str | None, default: str = Encoding.SJIS) -> str:
    if not value:
        return default
    name = value.strip().lower().replace(' ', '')
    name = _ALIASES.get(name, name)
    try:
        canonical = codecs.lookup(name).name
    except LookupError:
        return default
    return _ALIASES.get(canonical, canonical)


def xor_block(data: bytes, key: bytes) -> bytes:
    if not data:
        return data
    result = bytearray(data)
    key_int = struct.unpack('<I', key)[0]
    aligned = len(result) & ~3
    for i in range(0, aligned, 4):
        val = struct.unpack_from('<I', result, i)[0]
        struct.pack_into('<I', result, i, val ^ key_int)
    for i in range(aligned, len(result)):
        result[i] ^= key[i & 3]
    return bytes(result)


def _script_counts(text: str) -> tuple[int, int, int, int, int]:
    kana = sum('\u3040' <= ch <= '\u30ff' for ch in text)
    cjk = sum('\u3400' <= ch <= '\u9fff' for ch in text)
    jp_punct = sum(ch in _JAPANESE_PUNCTUATION for ch in text)
    simplified = sum(ch in _SIMPLIFIED_HINTS for ch in text)
    traditional = sum(ch in _TRADITIONAL_HINTS for ch in text)
    return kana, cjk, jp_punct, simplified, traditional


def _decoded_score(text: str, encoding: str) -> float:
    if not text:
        return 0.0
    printable = sum(ch.isprintable() or ch.isspace() for ch in text)
    controls = sum(ord(ch) < 0x20 and ch not in '\r\n\t' for ch in text)
    score = printable / len(text) * 4.0 - controls * 8.0
    kana, cjk, jp_punct, simplified, traditional = _script_counts(text)
    if encoding == Encoding.SJIS:
        score += kana * 6.0 + jp_punct * 1.25 + cjk * 0.08
    elif encoding == Encoding.GBK:
        score += simplified * 5.0 + cjk * 0.12 - kana * 2.0
    elif encoding == Encoding.BIG5:
        score += traditional * 5.0 + cjk * 0.12 - kana * 2.0
    elif encoding == Encoding.UTF8:
        score += (1.0 + kana * 6.0 + jp_punct * 1.25
                  + max(simplified, traditional) * 5.0 + cjk * 0.12)
    return score


def detect_text_encoding(
        data: bytes, preferred: str | None = None,
        candidates: tuple[str, ...] = (
            Encoding.UTF8, Encoding.SJIS, Encoding.GBK, Encoding.BIG5,
        )) -> str:
    """Detect UTF-8, Shift-JIS, GBK or BIG5 using strict decoding."""
    if data.startswith(b'\xef\xbb\xbf'):
        return Encoding.UTF8

    preferred = normalize_encoding(preferred) if preferred else None
    decoded: dict[str, str] = {}
    scores: dict[str, float] = {}
    for candidate in candidates:
        enc = normalize_encoding(candidate)
        try:
            value = data.decode(enc, errors='strict')
        except (UnicodeDecodeError, LookupError):
            continue
        decoded[enc] = value
        scores[enc] = _decoded_score(value, enc)

    if not scores:
        return preferred or Encoding.SJIS
    if len(scores) == 1:
        return next(iter(scores))

    sjis_text = decoded.get(Encoding.SJIS, '')
    kana, _, _, _, _ = _script_counts(sjis_text)
    if kana:
        scores[Encoding.SJIS] = scores.get(Encoding.SJIS, 0.0) + 8.0

    gbk_text = decoded.get(Encoding.GBK, '')
    if gbk_text:
        _, _, _, simplified, _ = _script_counts(gbk_text)
        scores[Encoding.GBK] += simplified * 3.0

    big5_text = decoded.get(Encoding.BIG5, '')
    if big5_text:
        _, _, _, _, traditional = _script_counts(big5_text)
        scores[Encoding.BIG5] += traditional * 3.0

    if Encoding.UTF8 in scores and any(value >= 0x80 for value in data):
        # Strict non-ASCII UTF-8 is meaningful evidence, while the language
        # score above prevents valid-looking Shift-JIS byte pairs from winning.
        scores[Encoding.UTF8] += 2.0

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, best_score = ranked[0]
    if preferred in scores and best_score - scores[preferred] <= 3.0:
        best = preferred
    elif Encoding.SJIS in scores and best_score - scores[Encoding.SJIS] <= 2.0:
        best = Encoding.SJIS

    return best


def decode_text(data: bytes, encoding: str = 'auto',
                preferred: str | None = None) -> tuple[str, str, bool]:
    has_bom = data.startswith(b'\xef\xbb\xbf')
    payload = data[3:] if has_bom else data
    enc = (detect_text_encoding(payload, preferred=preferred)
           if not encoding or encoding == 'auto'
           else normalize_encoding(encoding))
    return payload.decode(enc, errors='strict'), enc, has_bom


def encode_text_for_game(text: str, target_encoding: str = Encoding.GBK,
                         errors: str = 'strict') -> bytes:
    target_encoding = normalize_encoding(target_encoding, Encoding.GBK)
    if target_encoding == Encoding.SJIS:
        return text.encode(Encoding.SJIS, errors=errors)
    if target_encoding == Encoding.UTF8:
        return text.encode(Encoding.UTF8, errors=errors)
    if target_encoding == Encoding.BIG5:
        return text.encode(Encoding.BIG5, errors=errors)
    if target_encoding != Encoding.GBK:
        raise LookupError(f'不支持的目标编码: {target_encoding}')

    for old, new in Encoding.SJIS_TO_GBK_REPLACE.items():
        text = text.replace(old, new)
    placeholders: dict[str, str] = {}
    for i, ch in enumerate(Encoding.SJIS_KEEP_CHARS):
        placeholder = f'\x01KEEP{i}\x01'
        placeholders[placeholder] = ch
        text = text.replace(ch, placeholder)
    encoded = text.encode(Encoding.GBK, errors=errors)
    for placeholder, ch in placeholders.items():
        encoded = encoded.replace(
            placeholder.encode(Encoding.GBK),
            ch.encode(Encoding.SJIS, errors=errors),
        )
    return encoded
