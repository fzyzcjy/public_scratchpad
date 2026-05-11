"""Shared helpers for tom_refactor_<N>.py transform scripts.

The cardinal pattern: each script *cuts* a line range from a source file,
*pastes* it into a target file (optionally appending small text-substitution
fixups), and updates a small number of caller sites. The line range is
located dynamically via AST so it survives minor reflows of the base file.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Tuple


def find_method_lines(text: str, *, class_name: str, method_name: str) -> Tuple[int, int]:
    """Return 0-indexed half-open ``[start, end)`` line range of a method.

    Includes any leading decorators and the trailing blank line(s) up to the
    next method or class end — convenient for cut-and-paste.
    """
    tree = ast.parse(text)
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for i, node in enumerate(cls.body):
                if isinstance(node, func_types) and node.name == method_name:
                    start = node.lineno - 1
                    if node.decorator_list:
                        start = node.decorator_list[0].lineno - 1
                    if i + 1 < len(cls.body):
                        next_start = cls.body[i + 1].lineno - 1
                        nxt = cls.body[i + 1]
                        if isinstance(nxt, func_types + (ast.ClassDef,)) and nxt.decorator_list:
                            next_start = nxt.decorator_list[0].lineno - 1
                    else:
                        next_start = node.end_lineno
                    return start, next_start
    raise ValueError(f"{class_name}.{method_name} not found")


def find_function_lines(text: str, *, function_name: str) -> Tuple[int, int]:
    """Return 0-indexed half-open ``[start, end)`` line range of a module-level function.

    Includes any leading decorators.
    """
    tree = ast.parse(text)
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for i, node in enumerate(tree.body):
        if isinstance(node, func_types) and node.name == function_name:
            start = node.lineno - 1
            if node.decorator_list:
                start = node.decorator_list[0].lineno - 1
            if i + 1 < len(tree.body):
                next_start = tree.body[i + 1].lineno - 1
                if isinstance(tree.body[i + 1], func_types + (ast.ClassDef,)) and tree.body[i + 1].decorator_list:
                    next_start = tree.body[i + 1].decorator_list[0].lineno - 1
            else:
                next_start = node.end_lineno
            return start, next_start
    raise ValueError(f"function {function_name} not found")


def find_class_lines(text: str, *, class_name: str) -> Tuple[int, int]:
    """Return 0-indexed half-open ``[start, end)`` line range of a module-level class.

    Includes any leading decorators.
    """
    tree = ast.parse(text)
    for i, node in enumerate(tree.body):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            start = node.lineno - 1
            if node.decorator_list:
                start = node.decorator_list[0].lineno - 1
            if i + 1 < len(tree.body):
                next_start = tree.body[i + 1].lineno - 1
                if isinstance(tree.body[i + 1], (ast.FunctionDef, ast.ClassDef)) and tree.body[i + 1].decorator_list:
                    next_start = tree.body[i + 1].decorator_list[0].lineno - 1
            else:
                next_start = node.end_lineno
            return start, next_start
    raise ValueError(f"class {class_name} not found")


def cut_lines(path: Path, start: int, end: int) -> str:
    """Remove lines ``[start, end)`` from ``path``; return the cut text."""
    src = path.read_text().splitlines(keepends=True)
    cut = "".join(src[start:end])
    new_src = src[:start] + src[end:]
    path.write_text("".join(new_src))
    return cut


def insert_after(text: str, *, anchor: str, addition: str) -> str:
    """Insert ``addition`` immediately after ``anchor`` (substring). Asserts anchor exists exactly once.

    ``anchor`` should typically include the trailing ``\\n`` of the line you're
    inserting after; ``addition`` should include its own trailing ``\\n``(s).
    """
    count = text.count(anchor)
    if count != 1:
        raise ValueError(
            f"anchor must appear exactly once (got {count}): {anchor!r}"
        )
    return text.replace(anchor, anchor + addition, 1)


def add_to_grouped_import(text: str, *, anchor_name: str, new_line: str) -> str:
    """Insert ``new_line`` immediately before the line containing ``anchor_name``
    inside a ``from X import (...)`` block. Use for keeping imports
    alphabetically sorted: pass the **next** import name as anchor.

    Example::

        text = add_to_grouped_import(
            text,
            anchor_name="init_custom_process_group",
            new_line="    init_cublas,",
        )

    finds ``    init_custom_process_group,`` and inserts ``    init_cublas,``
    on the line above it.
    """
    anchor = f"    {anchor_name},\n"
    count = text.count(anchor)
    if count != 1:
        raise ValueError(
            f"grouped-import anchor must appear exactly once (got {count}): {anchor!r}"
        )
    return text.replace(anchor, f"{new_line}\n{anchor}", 1)


def replace_call_site(text: str, *, old: str, new: str) -> str:
    """Replace caller code; assert ``old`` exists at least once.

    Same effect as ``text.replace(old, new)`` but fails loudly on a typo /
    drift in ``old`` instead of silently no-op'ing.
    """
    if old not in text:
        raise ValueError(f"call-site anchor not found: {old!r}")
    return text.replace(old, new)


def append_to_file(path: Path, snippet: str, *, separator: str = "\n\n") -> None:
    """Append ``snippet`` to ``path`` with a separator before it. Creates if missing."""
    if path.exists():
        existing = path.read_text().rstrip() + separator
    else:
        existing = ""
    path.write_text(existing + snippet)


def rewrite_method_call_site(text: str, *, method_name: str, target_attr: str) -> str:
    """Robustly rewrite ``self.<method_name>(self.<target_attr>, ...)`` →
    ``self.<target_attr>.<method_name>(...)`` regardless of how black
    formatted the call (single-line or multi-line).

    Matches ``self.<method>(\\s*self.<target_attr>,\\s*`` and replaces with
    ``self.<target_attr>.<method>(``.

    Also handles the zero-arg case (``self.<method>(self.<target_attr>)``) →
    ``self.<target_attr>.<method>()``.

    Raises ``ValueError`` if no matches found (signals a stale anchor).
    """
    import re

    pattern_nargs = (
        rf"self\.{re.escape(method_name)}\(\s*self\.{re.escape(target_attr)},\s*"
    )
    pattern_noargs = (
        rf"self\.{re.escape(method_name)}\(\s*self\.{re.escape(target_attr)}\s*\)"
    )
    new_nargs = f"self.{target_attr}.{method_name}("
    new_noargs = f"self.{target_attr}.{method_name}()"

    count = len(re.findall(pattern_nargs, text)) + len(re.findall(pattern_noargs, text))
    if count == 0:
        raise ValueError(
            f"no call sites found for self.{method_name}(self.{target_attr}, ...)"
        )
    text = re.sub(pattern_noargs, new_noargs, text)
    text = re.sub(pattern_nargs, new_nargs, text)
    return text


def dedent_method_to_function(method_text: str) -> str:
    """Strip 4 leading spaces from each line — converts ``    def foo`` → ``def foo``."""
    out = []
    for line in method_text.splitlines(keepends=True):
        if line.startswith("    "):
            out.append(line[4:])
        else:
            out.append(line)
    return "".join(out)
