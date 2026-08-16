from __future__ import annotations

import html
from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeColors:
    primary: str
    secondary: str
    muted: str
    editor_background: str
    editor_foreground: str
    border: str


def theme_colors(dark: bool) -> ThemeColors:
    if dark:
        return ThemeColors(
            primary='#F5F5F5', secondary='#D0D0D0', muted='#A0A0A0',
            editor_background='#1E1E1E', editor_foreground='#D4D4D4',
            border='#3F3F46',
        )
    return ThemeColors(
        primary='#202020', secondary='#424242', muted='#6B6B6B',
        editor_background='#FFFFFF', editor_foreground='#1E1E1E',
        border='#CCCCCC',
    )


def info_html(rows: list[tuple[str, str]], dark: bool) -> str:
    colors = theme_colors(dark)
    lines = ['<table cellspacing="3" style="white-space:nowrap;font-size:9pt;">']
    for label, value in rows:
        lines.append(
            '<tr>'
            f'<td style="color:{colors.muted};padding-right:12px;">'
            f'{html.escape(str(label))}</td>'
            f'<td style="color:{colors.secondary};">'
            f'{html.escape(str(value))}</td>'
            '</tr>')
    lines.append('</table>')
    return ''.join(lines)
