"""
Markdown in a tk.Text: what the LLM answers are written in.

``show(text_widget, markdown)`` replaces the widget's content with ``markdown``
rendered: headings (``#`` to ``######``), paragraphs, ``**bold**``, ``*italic*`` /
``_italic_``, ``inline code``, fenced code blocks, bullet and numbered lists, block
quotes, horizontal rules, tables (kept in a fixed-width font so their columns line
up) and links (the text, then the address). Anything else is shown as written. The
fonts and colours come from ui_tokens and the active palette (ui_theme), set once
per widget by ``configure_tags``.
"""

from __future__ import annotations

import re
import tkinter as tk
from typing import List, Tuple

import ui_theme
import ui_tokens

_INLINE = re.compile(
    r"(\*\*(?P<b>.+?)\*\*|__(?P<b2>.+?)__|`(?P<code>[^`]+)`"
    r"|\[(?P<lt>[^\]]+)\]\((?P<lu>[^)\s]+)\)"
    r"|(?<![\w*])\*(?P<i>[^*\s][^*]*?)\*(?![\w*])|(?<![\w_])_(?P<i2>[^_\s][^_]*?)_(?![\w_]))"
)
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^(\s*)(\d+)[.)]\s+(.*)$")
_RULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")

HEADING_ROLES = {
    1: "display",
    2: "title",
    3: "subtitle",
    4: "body",
    5: "body",
    6: "body",
}


def configure_tags(widget: tk.Text) -> None:
    p = ui_theme.active_palette()
    for level, role in HEADING_ROLES.items():
        widget.tag_configure(
            f"h{level}",
            font=ui_tokens.font(role, "bold"),
            foreground=p["ACCENT"] if level <= 2 else p["FG"],
            spacing1=8,
            spacing3=4,
        )
    widget.tag_configure("bold", font=ui_tokens.font("body", "bold"))
    widget.tag_configure("italic", font=ui_tokens.font("body", "italic"))
    widget.tag_configure("code", font=ui_tokens.mono("small"), background=p["PANEL2"])
    widget.tag_configure(
        "codeblock",
        font=ui_tokens.mono("small"),
        background=p["PANEL2"],
        lmargin1=12,
        lmargin2=12,
    )
    widget.tag_configure("table", font=ui_tokens.mono("small"))
    widget.tag_configure("quote", foreground=p["MUTED"], lmargin1=16, lmargin2=16)
    widget.tag_configure("bullet", lmargin1=8, lmargin2=24)
    widget.tag_configure("rule", foreground=p["BORDER"])
    widget.tag_configure("link", foreground=p["ACCENT2"])
    widget.tag_configure("muted", foreground=p["MUTED"])


def inline_spans(text: str) -> List[Tuple[str, Tuple[str, ...]]]:
    """``text`` cut into (piece, tags) by its inline marks."""
    out: List[Tuple[str, Tuple[str, ...]]] = []
    pos = 0
    for m in _INLINE.finditer(text):
        if m.start() > pos:
            out.append((text[pos : m.start()], ()))
        if m.group("b") or m.group("b2"):
            out.append((m.group("b") or m.group("b2"), ("bold",)))
        elif m.group("code"):
            out.append((m.group("code"), ("code",)))
        elif m.group("lt"):
            out.append((m.group("lt"), ("link",)))
            out.append((f" ({m.group('lu')})", ("muted",)))
        else:
            out.append((m.group("i") or m.group("i2"), ("italic",)))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], ()))
    return out


def _table(lines: List[str]) -> List[str]:
    """A Markdown table's rows with their columns padded to line up."""
    rows = []
    for line in lines:
        if _TABLE_RULE.match(line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(cells)
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    sizes = [max(len(r[i]) for r in rows) for i in range(width)]
    out = []
    for n, r in enumerate(rows):
        out.append("  ".join(c.ljust(sizes[i]) for i, c in enumerate(r)).rstrip())
        if n == 0:
            out.append("  ".join("-" * s for s in sizes))
    return out


def blocks(markdown: str) -> List[Tuple[str, str, Tuple[str, ...]]]:
    """``markdown`` as (kind, text, line tags): kind is "inline" (marks to read)
    or "plain"."""
    out: List[Tuple[str, str, Tuple[str, ...]]] = []
    lines = str(markdown or "").replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(("plain", "\n".join(code) + "\n", ("codeblock",)))
            continue
        if (
            line.strip().startswith("|")
            and i + 1 < len(lines)
            and _TABLE_RULE.match(lines[i + 1])
        ):
            table = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table.append(lines[i])
                i += 1
            out.append(("plain", "\n".join(_table(table)) + "\n", ("table",)))
            continue
        heading = _HEADING.match(line)
        if heading:
            level = len(heading.group(1))
            out.append(("inline", heading.group(2) + "\n", (f"h{level}",)))
        elif _RULE.match(line):
            out.append(("plain", "─" * 40 + "\n", ("rule",)))
        elif line.lstrip().startswith(">"):
            out.append(("inline", line.lstrip()[1:].lstrip() + "\n", ("quote",)))
        elif _BULLET.match(line):
            indent, rest = _BULLET.match(line).groups()
            out.append(
                ("inline", "  " * (len(indent) // 2) + "• " + rest + "\n", ("bullet",))
            )
        elif _NUMBERED.match(line):
            indent, number, rest = _NUMBERED.match(line).groups()
            out.append(
                (
                    "inline",
                    "  " * (len(indent) // 2) + f"{number}. " + rest + "\n",
                    ("bullet",),
                )
            )
        else:
            out.append(("inline", line + "\n", ()))
        i += 1
    return out


def show(widget: tk.Text, markdown: str, keep_state: bool = True) -> None:
    """Replace ``widget``'s content with ``markdown`` rendered (read-only after)."""
    if not getattr(widget, "_markdown_tags", False):
        configure_tags(widget)
        widget._markdown_tags = True
    state = str(widget.cget("state"))
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    for kind, text, line_tags in blocks(markdown):
        if kind == "plain":
            widget.insert("end", text, line_tags)
            continue
        for piece, tags in inline_spans(text):
            widget.insert("end", piece, tuple(line_tags) + tuple(tags))
    widget.configure(state=state if keep_state else "disabled")


def plain_text(widget: tk.Text) -> str:
    return widget.get("1.0", "end-1c")
