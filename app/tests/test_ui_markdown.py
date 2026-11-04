"""Markdown in a tk.Text (ui_markdown): what the LLM answers are written in."""

import os
import sys
import tkinter as tk

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import ui_markdown as md  # noqa: E402

SAMPLE = """# Title

A paragraph that the model
wrapped over two lines, with **bold**, *italic* and `code`.

## Levels

- first
  - nested
1. one

| Level | Price |
|---|---|
| Support | 100 |

> a quote

---

```
x = 1
```
See [the docs](http://example.org)."""


def test_blocks_read_every_kind():
    kinds = [(k, t, tags) for k, t, tags in md.blocks(SAMPLE)]
    texts = [t for _, t, _ in kinds]
    assert ("inline", "Title\n", ("h1",)) in kinds
    assert (
        "A paragraph that the model wrapped over two lines, with **bold**, *italic* "
        "and `code`.\n"
    ) in texts  # one paragraph: the soft wrap runs on
    assert ("inline", "• first\n", ("bullet",)) in kinds
    assert ("inline", "  • nested\n", ("bullet",)) in kinds
    assert ("inline", "1. one\n", ("bullet",)) in kinds
    table = next(t for k, t, tags in kinds if tags == ("table",))
    assert table.splitlines() == ["Level    Price", "-------  -----", "Support  100"]
    assert ("inline", "a quote\n", ("quote",)) in kinds
    assert any(tags == ("rule",) for _, _, tags in kinds)
    assert ("plain", "x = 1\n", ("codeblock",)) in kinds


def test_inline_marks():
    assert md.inline_spans("a **b** *c* `d` [e](http://f)") == [
        ("a ", ()),
        ("b", ("bold",)),
        (" ", ()),
        ("c", ("italic",)),
        (" ", ()),
        ("d", ("code",)),
        (" ", ()),
        ("e", ("link",)),
        (" (http://f)", ("muted",)),
    ]
    assert md.inline_spans("2 * 3 * 4 and snake_case_name") == [
        ("2 * 3 * 4 and snake_case_name", ())
    ]


@pytest.fixture
def root():
    last = None
    for _ in range(5):
        try:
            r = tk.Tk()
            break
        except tk.TclError as exc:
            last = exc
    else:
        pytest.skip(f"Tk cannot start: {last}")
    r.withdraw()
    yield r
    r.destroy()


def test_show_renders_into_a_read_only_text(root):
    text = tk.Text(root)
    text.configure(state="disabled")
    md.show(text, SAMPLE)
    shown = text.get("1.0", "end-1c")
    assert "**" not in shown and "```" not in shown and "# Title" not in shown
    assert "h1" in text.tag_names(text.search("Title", "1.0"))
    assert "bold" in text.tag_names(text.search("bold", "1.0"))
    assert str(text.cget("state")) == "disabled"
