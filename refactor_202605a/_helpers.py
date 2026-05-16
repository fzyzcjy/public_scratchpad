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


def rewrite_intra_class_calls(
    body: str,
    *,
    source_classes: list[str],
    target_class: str,
    methods: list[str],
) -> str:
    """Collapse intra-class self-dispatch to plain ``self.<m>(...)`` form.

    Prep rewrites every sibling-method call to ``<OldClass>.<m>(self, ...)``
    so the body still type-checks while the methods are still on OldClass
    via ``@staticmethod`` with ``self: "OwnerClass"`` typing. After the move,
    those methods are regular instance methods on ``target_class``, so the
    class-qualified form is dead cruft — fold every variant back to
    ``self.<m>(...)``.

    Handles single-line, multi-line where ``self`` sits with other args,
    multi-line where ``self`` is on its own line, and the zero-arg form.

    ``target_class`` is unused in the output (we always fold to ``self.``) —
    kept in the signature for documentation and to flag which class is the
    final owner.
    """
    del target_class  # documentation only; output is always ``self.<m>(...)``
    import re

    for m in methods:
        m_re = re.escape(m)
        for src in source_classes:
            src_re = re.escape(src)
            # Single-line: ``<src>.<m>(self, ARG, ...)`` → ``self.<m>(ARG, ...)``
            body = re.sub(
                rf"\b{src_re}\.{m_re}\(\s*self\s*,\s*",
                f"self.{m}(",
                body,
            )
            # Multi-line with self+other-arg on same line:
            #   ``<src>.<m>(\n<indent>self, ARG`` → ``self.<m>(\n<indent>ARG``
            body = re.sub(
                rf"\b{src_re}\.{m_re}\(\s*\n(\s+)self,\s+",
                lambda mt: f"self.{m}(\n{mt.group(1)}",
                body,
            )
            # Multi-line with self alone on its line, then next arg on next line:
            #   ``<src>.<m>(\n<indent>self,\n<indent>ARG`` →
            #   ``self.<m>(\n<indent>ARG``
            body = re.sub(
                rf"\b{src_re}\.{m_re}\(\s*\n\s+self,\s*\n(\s+)",
                lambda mt: f"self.{m}(\n{mt.group(1)}",
                body,
            )
            # Zero-arg: ``<src>.<m>(self)`` → ``self.<m>()``
            body = re.sub(
                rf"\b{src_re}\.{m_re}\(\s*self\s*\)",
                f"self.{m}()",
                body,
            )
    return body


def dedent_method_to_function(method_text: str) -> str:
    """Strip 4 leading spaces from each line — converts ``    def foo`` → ``def foo``."""
    out = []
    for line in method_text.splitlines(keepends=True):
        if line.startswith("    "):
            out.append(line[4:])
        else:
            out.append(line)
    return "".join(out)


# ---------------------------------------------------------------------------
# Import-injection helpers (Option C).
#
# Mech-prep commits write the methods/dataclasses into the target file's
# skeleton with only the imports the skeleton itself needs. Then sglang's
# pre-commit ruff (`--select=F401,F821 --fix`) strips any unused imports.
# When the corresponding mech-move commit splices the method *bodies* in,
# those bodies reference names that were never imported into the target
# (because the prep skeleton didn't reference them, so ruff removed them).
#
# Option C: every mech-move script that splices method bodies into a new
# target file calls ``ensure_imports`` (or feeds ``compute_required_imports``
# from the source file's import header) so the names the bodies use are
# imported either at runtime or inside ``if TYPE_CHECKING:``.
# ---------------------------------------------------------------------------


_ImportSpec = dict[str, str | tuple[str, ...] | list[str]]


def _normalize_imports(spec: _ImportSpec | None) -> dict[str, tuple[str, ...]]:
    if not spec:
        return {}
    out: dict[str, tuple[str, ...]] = {}
    for module, names in spec.items():
        if isinstance(names, str):
            normalized = (names,)
        else:
            normalized = tuple(names)
        if not normalized:
            continue
        out[module] = normalized
    return out


def _parse_grouped_import_block(text: str, start: int) -> tuple[int, list[str]]:
    """Parse a multi-line ``from X import (\\n    A,\\n    B,\\n)`` block starting at ``start``.

    Returns ``(end_index_after_closing_paren_newline, names)``.
    """
    end = text.index(")", start) + 1
    if end < len(text) and text[end] == "\n":
        end += 1
    block = text[start:end]
    names: list[str] = []
    for line in block.splitlines():
        s = line.strip().rstrip(",")
        if not s or s.startswith("from ") or s == "(" or s == ")":
            continue
        if s.endswith("import (") or s.endswith("import("):
            continue
        names.append(s)
    return end, names


def _format_grouped_import(module: str, names: tuple[str, ...]) -> str:
    sorted_names = sorted(set(names))
    if len(sorted_names) == 1:
        return f"from {module} import {sorted_names[0]}\n"
    body = "".join(f"    {n},\n" for n in sorted_names)
    return f"from {module} import (\n{body})\n"


def _merge_import_into_text(
    text: str,
    *,
    module: str,
    names: tuple[str, ...],
    inside_type_checking: bool,
) -> str:
    """Insert/merge a ``from <module> import ...`` statement into ``text``.

    If ``inside_type_checking`` is True, the import is placed inside the
    ``if TYPE_CHECKING:`` block (created if absent). Otherwise it goes
    at module scope below the last existing import line.
    """
    import re

    if inside_type_checking:
        # Find ``if TYPE_CHECKING:`` block. The block contents are exactly
        # the consecutive indented lines after the header.
        tc_match = re.search(r"^if TYPE_CHECKING:\n", text, re.MULTILINE)
        if tc_match is None:
            # Create a new block right before ``logger = `` if present,
            # else at the end of module-level imports.
            new_block = (
                "if TYPE_CHECKING:\n"
                + _indent_grouped_import(module, names)
                + "\n"
            )
            return _insert_at_module_scope(text, new_block)
        body_start = tc_match.end()
        # Walk forward over indented (4-space) lines, blank lines that
        # sit between indented lines, and "    pass" placeholders.
        i = body_start
        last_body_end = body_start
        while i < len(text):
            line_end = text.find("\n", i)
            if line_end == -1:
                line_end = len(text)
            line = text[i:line_end]
            if line.startswith("    ") or (line == "" and i < len(text) - 1 and text[line_end + 1 : line_end + 5] == "    "):
                last_body_end = line_end + 1
                i = line_end + 1
                continue
            break
        body = text[body_start:last_body_end]
        # If body is just ``    pass\n`` (with optional blank line), replace it.
        stripped_body_lines = [ln for ln in body.splitlines() if ln.strip()]
        existing_block_idx_start = body_start
        # Look for existing ``from <module> import ...`` inside this block.
        existing_pattern = re.compile(
            rf"^(    from {re.escape(module)} import [^\n(]+\n)",
            re.MULTILINE,
        )
        existing_grouped_pattern = re.compile(
            rf"^    from {re.escape(module)} import \(\n",
            re.MULTILINE,
        )
        block_text = text[existing_block_idx_start:last_body_end]
        m = existing_pattern.search(block_text)
        m_grouped = existing_grouped_pattern.search(block_text)
        if m_grouped is not None:
            # Merge into existing grouped block.
            grouped_start = existing_block_idx_start + m_grouped.start()
            grouped_end, existing_names = _parse_grouped_import_block(text, grouped_start)
            merged = tuple(sorted(set(existing_names) | set(names)))
            new_grouped = "".join(
                "    " + ln if ln.strip() else ln
                for ln in _format_grouped_import(module, merged).splitlines(keepends=True)
            )
            return text[:grouped_start] + new_grouped + text[grouped_end:]
        if m is not None:
            # Merge into existing single-line ``from X import a, b``.
            line_start = existing_block_idx_start + m.start()
            line_end = existing_block_idx_start + m.end()
            existing_line = text[line_start:line_end]
            existing_names = [
                n.strip()
                for n in existing_line.strip().removeprefix("from ").split(" import ", 1)[1].rstrip(",").split(",")
                if n.strip()
            ]
            merged = tuple(sorted(set(existing_names) | set(names)))
            new_line = "    " + _format_grouped_import(module, merged)
            new_line = new_line.replace("\n    ", "\n    ")
            # Re-indent each line of the formatted import by 4 spaces.
            new_block_lines = []
            for ln in _format_grouped_import(module, merged).splitlines(keepends=True):
                new_block_lines.append("    " + ln if ln.strip() else ln)
            return text[:line_start] + "".join(new_block_lines) + text[line_end:]
        # No existing import for this module — append a new line inside the block.
        # Strip a sole ``    pass`` placeholder if present.
        new_indented = "".join(
            "    " + ln if ln.strip() else ln
            for ln in _format_grouped_import(module, names).splitlines(keepends=True)
        )
        if stripped_body_lines == ["    pass"]:
            # Replace the entire body (including its blank trailing line if any).
            return text[:body_start] + new_indented + text[last_body_end:]
        return text[:last_body_end] + new_indented + text[last_body_end:]

    # Runtime import (module scope, outside any TYPE_CHECKING block).
    grouped_pat = re.compile(
        rf"^from {re.escape(module)} import \(\n", re.MULTILINE
    )
    m_grouped = grouped_pat.search(text)
    if m_grouped is not None:
        grouped_start = m_grouped.start()
        grouped_end, existing_names = _parse_grouped_import_block(text, grouped_start)
        merged = tuple(sorted(set(existing_names) | set(names)))
        new_grouped = _format_grouped_import(module, merged)
        return text[:grouped_start] + new_grouped + text[grouped_end:]
    single_pat = re.compile(
        rf"^from {re.escape(module)} import (?!\()([^\n]+)\n", re.MULTILINE
    )
    m_single = single_pat.search(text)
    if m_single is not None:
        existing_names = [n.strip() for n in m_single.group(1).split(",") if n.strip()]
        merged = tuple(sorted(set(existing_names) | set(names)))
        new_line = _format_grouped_import(module, merged)
        return text[: m_single.start()] + new_line + text[m_single.end() :]
    # No existing import — insert a fresh ``from X import ...`` line at
    # module scope below the last import.
    new_line = _format_grouped_import(module, names)
    return _insert_at_module_scope(text, new_line)


def _indent_grouped_import(module: str, names: tuple[str, ...]) -> str:
    return "".join(
        "    " + ln if ln.strip() else ln
        for ln in _format_grouped_import(module, names).splitlines(keepends=True)
    )


def _insert_at_module_scope(text: str, snippet: str) -> str:
    """Insert ``snippet`` after the last module-level ``from``/``import`` line.

    Falls back to placing it just before the first non-import statement,
    or at the top of the file (after ``from __future__`` and the module
    docstring) if there are no imports.
    """
    import re

    last_import_end = 0
    # Find a clean module-level import line — not indented, starts with
    # ``import `` or ``from ... import``.
    pat = re.compile(
        r"^(?:from\s+[\w.]+\s+import\s*\([^)]*\)\n|from\s+[\w.]+\s+import\s+[^\n]+\n|import\s+[^\n]+\n)",
        re.MULTILINE,
    )
    for m in pat.finditer(text):
        # Skip imports that sit inside an indented block — pat is MULTILINE
        # but ``^`` anchors to a non-indented start, so this is already safe.
        last_import_end = m.end()
    if last_import_end == 0:
        # No imports — place after the module docstring / __future__ if present.
        return snippet + text
    return text[:last_import_end] + snippet + text[last_import_end:]


def ensure_imports(
    text: str,
    *,
    runtime: _ImportSpec | None = None,
    type_checking: _ImportSpec | None = None,
) -> str:
    """Ensure the given imports are present in ``text``.

    Args:
      text: file contents.
      runtime: ``{module: name | (names, ...)}`` — imports placed at module
        scope (real runtime imports).
      type_checking: ``{module: name | (names, ...)}`` — imports placed
        inside the ``if TYPE_CHECKING:`` block (created if absent).

    Behavior:
      * If a ``from <module> import ...`` already exists in the matching
        scope, merge the new names (sorted, deduped, grouped on >=2 names).
      * Otherwise insert a fresh import line in the matching scope.
      * Existing imports are never removed; only added.
      * If type_checking is provided and the file has no ``if TYPE_CHECKING:``
        block, a new one is created at module-scope below the existing imports.
    """
    runtime_norm = _normalize_imports(runtime)
    tc_norm = _normalize_imports(type_checking)

    if tc_norm and "TYPE_CHECKING" not in text:
        # Need to ensure TYPE_CHECKING itself is imported from typing.
        text = ensure_imports(
            text, runtime={"typing": ("TYPE_CHECKING",)}
        )

    for module, names in runtime_norm.items():
        text = _merge_import_into_text(
            text, module=module, names=names, inside_type_checking=False
        )
    for module, names in tc_norm.items():
        text = _merge_import_into_text(
            text, module=module, names=names, inside_type_checking=True
        )
    return text


def _collect_referenced_names(method_blocks: list[str]) -> set[str]:
    """Walk the AST of each block; return the set of Name node ids referenced."""
    names: set[str] = set()
    for block in method_blocks:
        # Methods are indented; dedent before parsing standalone.
        dedented = dedent_method_to_function(block)
        try:
            tree = ast.parse(dedented)
        except SyntaxError:
            # Some blocks are dataclass bodies / multi-statement spans —
            # wrap them as a class body for parsability.
            try:
                tree = ast.parse("class _T:\n" + "".join(
                    "    " + ln for ln in block.splitlines(keepends=True)
                ))
            except SyntaxError:
                continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                # The base of an attribute chain is the only Name we care about;
                # walk picks it up via the Name node, so nothing extra to do.
                pass
    return names


def _module_import_map(source_text: str) -> tuple[dict[str, tuple[str, str]], set[str]]:
    """Parse ``source_text``; return (name → (module, kind), tc_only_names).

    ``kind`` is one of:
      * ``"from"`` — ``from <module> import <name>``
      * ``"import"`` — ``import <module>`` (name == module's leaf)
      * ``"import_as"`` — ``import <module> as <name>``

    ``tc_only_names`` is the subset of names that appeared only inside an
    ``if TYPE_CHECKING:`` block.
    """
    tree = ast.parse(source_text)
    name_map: dict[str, tuple[str, str]] = {}
    tc_only: set[str] = set()

    def _collect(nodes, *, inside_tc: bool) -> None:
        for node in nodes:
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    name = alias.asname or alias.name
                    key = name
                    if alias.name == "*":
                        continue
                    name_map[key] = (module, "from")
                    if inside_tc:
                        tc_only.add(key)
                    elif key in tc_only:
                        tc_only.discard(key)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        name_map[alias.asname] = (alias.name, "import_as")
                        if inside_tc:
                            tc_only.add(alias.asname)
                        elif alias.asname in tc_only:
                            tc_only.discard(alias.asname)
                    else:
                        leaf = alias.name.split(".")[0]
                        name_map[leaf] = (alias.name, "import")
                        if inside_tc:
                            tc_only.add(leaf)
                        elif leaf in tc_only:
                            tc_only.discard(leaf)
            elif isinstance(node, ast.If):
                cond = node.test
                is_tc = (
                    isinstance(cond, ast.Name) and cond.id == "TYPE_CHECKING"
                )
                _collect(node.body, inside_tc=inside_tc or is_tc)
                _collect(node.orelse, inside_tc=inside_tc)

    _collect(tree.body, inside_tc=False)
    return name_map, tc_only


def compute_required_imports(
    source_text: str,
    method_blocks: list[str],
    *,
    target_text: str | None = None,
    extra_names: list[str] | None = None,
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    """Derive (runtime_imports, type_checking_imports) needed by ``method_blocks``.

    Args:
      source_text: full text of the file the methods were cut from. Its
        module-level (and TYPE_CHECKING) imports define name → module
        mapping.
      method_blocks: list of method-body texts (as ``cut_lines`` returns).
      target_text: optional. If given, names already imported in the
        target are dropped from the returned dicts (avoids redundant
        merges).
      extra_names: additional names to look up (e.g. names that appear
        only in dataclass body / decorator arg lists that the AST walk
        might miss).

    Returns ``(runtime_dict, tc_dict)`` suitable for ``ensure_imports``.

    Names with no matching import in ``source_text`` are silently skipped
    (they may be locals / builtins / params).
    """
    name_map, tc_only = _module_import_map(source_text)
    referenced = _collect_referenced_names(method_blocks)
    if extra_names:
        referenced.update(extra_names)

    already_imported: set[str] = set()
    if target_text is not None:
        target_map, _ = _module_import_map(target_text)
        already_imported = set(target_map.keys())

    runtime: dict[str, list[str]] = {}
    tc: dict[str, list[str]] = {}
    for name in sorted(referenced):
        if name in already_imported:
            continue
        if name not in name_map:
            continue
        module, kind = name_map[name]
        if kind != "from":
            # Bare ``import X`` or ``import X as Y`` — let it fall through
            # via a single-name from-import is wrong; instead inject the
            # raw import statement. We model this by inserting under a
            # synthetic module key prefixed with ``__import__:`` so the
            # caller / helper can special-case it. For simplicity here we
            # treat ``import torch`` as ``from <empty> import torch`` which
            # is wrong; instead skip and surface via a separate dict.
            continue
        bucket = tc if name in tc_only else runtime
        bucket.setdefault(module, []).append(name)

    runtime_out = {k: tuple(sorted(set(v))) for k, v in runtime.items()}
    tc_out = {k: tuple(sorted(set(v))) for k, v in tc.items()}
    return runtime_out, tc_out


def collect_required_bare_imports(
    source_text: str,
    method_blocks: list[str],
    *,
    target_text: str | None = None,
) -> list[str]:
    """Return raw ``import X`` / ``import X as Y`` statements that ``method_blocks`` need.

    Complementary to ``compute_required_imports`` (which only handles
    ``from X import ...`` form). Returns each missing statement with a
    trailing newline; caller decides where to splice them in.
    """
    name_map, _ = _module_import_map(source_text)
    referenced = _collect_referenced_names(method_blocks)

    already_imported: set[str] = set()
    if target_text is not None:
        target_map, _ = _module_import_map(target_text)
        already_imported = set(target_map.keys())

    out: list[str] = []
    for name in sorted(referenced):
        if name in already_imported:
            continue
        if name not in name_map:
            continue
        module, kind = name_map[name]
        if kind == "import":
            out.append(f"import {module}\n")
        elif kind == "import_as":
            out.append(f"import {module} as {name}\n")
    return out


def ensure_bare_imports(text: str, statements: list[str]) -> str:
    """Ensure each ``import X`` statement in ``statements`` exists in ``text``.

    Inserts missing statements at module-scope below the last import.
    Existing identical lines are skipped.
    """
    out = text
    for stmt in statements:
        if stmt in out:
            continue
        out = _insert_at_module_scope(out, stmt)
    return out
