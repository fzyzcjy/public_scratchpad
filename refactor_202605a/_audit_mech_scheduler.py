#!/usr/bin/env python3
"""Read-only audit of the mech_scheduler refactor chain transform scripts.

For each `<id>` in `_build_mech_scheduler.py::ORDER`, parse the corresponding
`<id>.py`, collect string literals + commit body + `transform()` body, then
run 7 heuristic checks (A1, A2, B, C1, C2, D, E, F) per
`audit-mech-scheduler` plan. Emit a human-readable `audit.md` and a
structured `audit.json` under
``/Users/tom/main/lab/docs/pkgs/sglang/notes/audit-mech-scheduler/``.

Pure text-scan; never executes the transform, never touches the worktree
or sglang repo. Source files referenced as "src" come from
``git show upstream/main:<path>``.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

HERE = Path(__file__).parent
BUILD = HERE / "_build_mech_scheduler.py"
SGLANG_REPO = Path("/Users/tom/main/workspaces/ws-main/worktrees/sglang-dev-a")
OUT_DIR = Path("/Users/tom/main/lab/docs/pkgs/sglang/notes/audit-mech-scheduler")


# --------------------------------------------------------------------------
# ORDER extraction
# --------------------------------------------------------------------------

def load_order() -> list[str]:
    tree = ast.parse(BUILD.read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "ORDER"
        ):
            return [el.value for el in node.value.elts]  # type: ignore[union-attr]
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "ORDER"
        ):
            return [el.value for el in node.value.elts]  # type: ignore[union-attr]
    raise RuntimeError("ORDER not found in _build_mech_scheduler.py")


# --------------------------------------------------------------------------
# AST utilities for one script
# --------------------------------------------------------------------------

def parse_script(path: Path) -> ast.Module:
    return ast.parse(path.read_text(), filename=str(path))


def extract_assign(tree: ast.Module, name: str) -> Optional[str]:
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    return None


def all_string_literals(tree: ast.Module) -> list[tuple[int, str]]:
    """Return [(lineno, str-value)] for every `ast.Constant(str)` in the file.

    Includes docstrings, triple-quoted assignments, raw kwargs, etc.
    """
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append((node.lineno, node.value))
    return out


def find_transform_node(tree: ast.Module) -> Optional[ast.FunctionDef]:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "transform":
            return node
    return None


def transform_literals(tree: ast.Module) -> list[tuple[int, str]]:
    """Strings inside `transform()` only (not the module-level BODY etc)."""
    tnode = find_transform_node(tree)
    if not tnode:
        return []
    out: list[tuple[int, str]] = []
    for node in ast.walk(tnode):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.append((node.lineno, node.value))
    return out


# Module-level "infrastructure" constants we exclude from semantic checks.
_INFRA_NAMES = {
    "ID", "SUBJECT", "BODY", "AREA", "BASE", "AREA_BRANCH",
}


def script_payload_literals(tree: ast.Module) -> list[tuple[int, str]]:
    """All string literals that participate in payload composition.

    Combines:
      - every string literal inside ``transform()``
      - every module-level string constant (except infra names + docstring)
        that ``transform()`` references via Name.

    Many scripts stash large code blocks in module-level constants
    (``PREP_METHOD_BLOCKS``, ``SKELETON_CLASS``, ``HEADER``) and merely Name-load
    them inside transform(). Restricting to transform()-scope literals misses
    those, so we follow the Name references.
    """
    tnode = find_transform_node(tree)
    out: list[tuple[int, str]] = []

    # 1. transform()-scope.
    if tnode:
        for node in ast.walk(tnode):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append((node.lineno, node.value))

    # 2. Names referenced from transform().
    referenced: set[str] = set()
    if tnode:
        for node in ast.walk(tnode):
            if isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                referenced.add(node.value.id)

    # Find module-level assignments matching those Names; collect string
    # literals reachable from the RHS.
    for stmt in tree.body:
        if not isinstance(stmt, ast.Assign):
            continue
        target_names = {
            t.id for t in stmt.targets if isinstance(t, ast.Name)
        }
        if not (target_names & referenced):
            continue
        if target_names <= _INFRA_NAMES:
            continue
        for sub in ast.walk(stmt.value):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                out.append((sub.lineno, sub.value))
    return out


def transform_calls(tree: ast.Module) -> list[ast.Call]:
    tnode = find_transform_node(tree)
    if not tnode:
        return []
    return [n for n in ast.walk(tnode) if isinstance(n, ast.Call)]


# --------------------------------------------------------------------------
# Dimension A1 — hardcoded code blocks in literals
# --------------------------------------------------------------------------

CODE_LINE_PATTERNS = [
    re.compile(r"^\s{4,}def "),
    re.compile(r"^\s*def "),
    re.compile(r"^\s*class "),
    re.compile(r"^\s*@(staticmethod|classmethod|dataclass|property)"),
    re.compile(r"^\s+self\."),
    re.compile(r"^\s+return\b"),
    re.compile(r"^\s+if\b"),
    re.compile(r"^\s+for\b"),
    re.compile(r"^\s+while\b"),
    re.compile(r"^\s+raise\b"),
]


def looks_like_code_block(literal: str) -> bool:
    """≥ 3 code-shape lines in a single literal."""
    lines = literal.splitlines()
    hits = 0
    for line in lines:
        for pat in CODE_LINE_PATTERNS:
            if pat.match(line):
                hits += 1
                break
    return hits >= 3


def check_a1(
    *, tlits: list[tuple[int, str]], body: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    body_norm = body.strip()
    for lineno, lit in tlits:
        lit_norm = lit.strip()
        if not lit_norm:
            continue
        if body_norm and lit_norm in body_norm:
            continue
        if not looks_like_code_block(lit):
            continue
        # Filter docstrings: tlits already restricts to transform() so module
        # docstring is excluded. transform() rarely has its own docstring; if
        # it does, it'll typically be plain prose (no code patterns).
        snippet = lit if len(lit) <= 400 else lit[:400] + "…"
        out.append({"location": f"line {lineno}", "snippet": snippet})
    return out


# --------------------------------------------------------------------------
# Dimension A2 — multiple string rewrites on same text variable
# --------------------------------------------------------------------------

REWRITE_METHODS = {"replace", "sub"}


def check_a2(tree: ast.Module) -> list[dict[str, Any]]:
    """≥ 3 .replace()/re.sub() calls inside transform()."""
    tnode = find_transform_node(tree)
    if not tnode:
        return []
    rewrite_count = 0
    locations: list[int] = []
    for node in ast.walk(tnode):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Attribute) and f.attr in REWRITE_METHODS:
            rewrite_count += 1
            locations.append(node.lineno)
        elif (
            isinstance(f, ast.Attribute)
            and isinstance(f.value, ast.Name)
            and f.value.id == "re"
            and f.attr == "sub"
        ):
            rewrite_count += 1
            locations.append(node.lineno)
    if rewrite_count >= 3:
        return [{
            "count": rewrite_count,
            "locations": locations,
            "note": (
                ".replace()/re.sub() calls inside transform() — heavy string "
                "patching suggests the script is recomposing rather than "
                "cutting + pasting."
            ),
        }]
    return []


# --------------------------------------------------------------------------
# Dimension B — insert anchors (informational)
# --------------------------------------------------------------------------

def check_b(tree: ast.Module) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for call in transform_calls(tree):
        fn = call.func
        # insert_after / insert_before (helper module) — match by attribute or name
        fname = None
        if isinstance(fn, ast.Name) and fn.id in {"insert_after", "insert_before"}:
            fname = fn.id
        elif isinstance(fn, ast.Attribute) and fn.attr in {"insert_after", "insert_before"}:
            fname = fn.attr
        if not fname:
            continue
        anchor = None
        for kw in call.keywords:
            if kw.arg == "anchor" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                anchor = kw.value.value
                break
        out.append({
            "fn": fname,
            "line": call.lineno,
            "anchor": (anchor or "<non-literal>")[:160],
        })
    return out


# --------------------------------------------------------------------------
# Dimension C1 — new comment lines in literals
# --------------------------------------------------------------------------

COMMENT_RE = re.compile(r"^\s*#")
SHEBANG_RE = re.compile(r"^\s*#!")
CODING_RE = re.compile(r"^\s*#.*coding[:=]")


def check_c1(tlits: list[tuple[int, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for lineno, lit in tlits:
        for ln in lit.splitlines():
            if not COMMENT_RE.match(ln):
                continue
            if SHEBANG_RE.match(ln) or CODING_RE.match(ln):
                continue
            # noqa lines are mostly imports — skip as not "new prose comments"
            if "noqa" in ln:
                continue
            # type: ignore — also mostly mechanical
            if "type: ignore" in ln:
                continue
            out.append({"location": f"line {lineno}", "comment": ln.strip()})
    return out


# --------------------------------------------------------------------------
# Dimension C2 — only for -move scripts: comments lost vs source method body
# --------------------------------------------------------------------------

def _git_show_upstream(path_in_repo: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "show", f"upstream/main:{path_in_repo}"],
            cwd=SGLANG_REPO,
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return None


def _comments_in_text(text: str) -> set[str]:
    return {
        ln.strip()
        for ln in text.splitlines()
        if COMMENT_RE.match(ln) and not SHEBANG_RE.match(ln) and "noqa" not in ln
    }


def check_c2(*, id: str, tree: ast.Module, tlits: list[tuple[int, str]]) -> list[dict[str, Any]]:
    """For -move scripts: list comments present in source method body but not
    in any transform() literal. Indicative of dropped comments.

    This is a coarse heuristic — we just check whether each unique
    source-side comment line appears as a substring of *any* transform
    literal.
    """
    if not id.endswith("-move"):
        return []

    # Find find_method_lines() calls — pull (method_name, class_name) pairs
    method_targets: list[tuple[str, Optional[str]]] = []
    for call in transform_calls(tree):
        fn = call.func
        fname = None
        if isinstance(fn, ast.Name) and fn.id == "find_method_lines":
            fname = "find_method_lines"
        elif isinstance(fn, ast.Attribute) and fn.attr == "find_method_lines":
            fname = "find_method_lines"
        if not fname:
            continue
        cls_name: Optional[str] = None
        method_name: Optional[str] = None
        for kw in call.keywords:
            if kw.arg == "class_name" and isinstance(kw.value, ast.Constant):
                cls_name = kw.value.value
            elif kw.arg == "method_name" and isinstance(kw.value, ast.Constant):
                method_name = kw.value.value
        if method_name:
            method_targets.append((method_name, cls_name))

    if not method_targets:
        return []

    # Try to locate the source file used in transform(): scan literals for
    # paths like "python/sglang/..." used in `wt / "..."`.
    candidate_paths = []
    for _, lit in tlits:
        if lit.startswith("python/sglang/") and lit.endswith(".py"):
            candidate_paths.append(lit)

    all_src_text = ""
    for p in candidate_paths:
        txt = _git_show_upstream(p)
        if txt:
            all_src_text += "\n" + txt

    if not all_src_text:
        return []

    # Concat all transform literals for substring matching.
    target_blob = "\n".join(lit for _, lit in tlits)

    out: list[dict[str, Any]] = []
    src_comments_seen: set[str] = set()

    for method_name, cls_name in method_targets:
        # crude regex grab of method body: from `def <name>(` until next
        # ``    def `` / ``class ``.
        pat = re.compile(
            rf"^(\s*)def {re.escape(method_name)}\b.*?(?=^\1def |^class |\Z)",
            re.MULTILINE | re.DOTALL,
        )
        m = pat.search(all_src_text)
        if not m:
            continue
        body_text = m.group(0)
        for c in _comments_in_text(body_text):
            if c in src_comments_seen:
                continue
            src_comments_seen.add(c)
            if c not in target_blob:
                out.append({
                    "method": f"{cls_name or '?'}.{method_name}",
                    "comment": c[:200],
                })
    return out


# --------------------------------------------------------------------------
# Dimension D — drift numbers in BODY
# --------------------------------------------------------------------------

WHITELIST_AFTER = re.compile(r"\b(the|a|one)\s+(\d+)\b", re.IGNORECASE)
WHITELIST_ENUM_NEIGHBOR = re.compile(
    r"\b(\d+)\s+(free items|mode-conditional fields|methods?|mixins?)\b",
    re.IGNORECASE,
)


def check_d(body: str) -> list[dict[str, Any]]:
    if not body:
        return []
    # collect whitelisted spans
    whitelisted_spans: list[tuple[int, int]] = []
    for m in WHITELIST_AFTER.finditer(body):
        # span of the digit group
        whitelisted_spans.append(m.span(2))
    for m in WHITELIST_ENUM_NEIGHBOR.finditer(body):
        whitelisted_spans.append(m.span(1))

    def is_whitelisted(span: tuple[int, int]) -> bool:
        return any(ws == span for ws in whitelisted_spans)

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in re.finditer(r"\b\d+\b", body):
        digit = m.group(0)
        if digit in {"0", "1"}:
            continue
        if is_whitelisted(m.span()):
            continue
        # Pull surrounding context (40 chars each side).
        start = max(0, m.start() - 40)
        end = min(len(body), m.end() + 40)
        ctx = body[start:end].replace("\n", " ")
        key = f"{digit}|{ctx.strip()[:80]}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"number": digit, "context": ctx.strip()[:200]})
    return out


# --------------------------------------------------------------------------
# Dimension E — untyped kwarg in `def` signatures inside literals
# --------------------------------------------------------------------------

DEF_LINE_RE = re.compile(r"^\s*def\s+\w+\s*\(.*", re.MULTILINE)


def _parse_signature_line(sig_text: str) -> Optional[tuple[str, list[str]]]:
    """Best-effort: extract function name + untyped param names from a
    possibly-multiline `def ... (...)` block.

    Returns (function_name, [untyped_param_names]) or None on parse failure.
    """
    # Try to capture from "def NAME(" through the first balanced ")":"
    # We use a simple bracket scanner.
    name_m = re.search(r"def\s+(\w+)\s*\(", sig_text)
    if not name_m:
        return None
    fname = name_m.group(1)
    start = name_m.end()
    depth = 1
    i = start
    while i < len(sig_text) and depth > 0:
        ch = sig_text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    params_blob = sig_text[start:i - 1]
    # Strip default values and whitespace, split on top-level commas
    params: list[str] = []
    buf = ""
    depth2 = 0
    for ch in params_blob:
        if ch in "([{":
            depth2 += 1
        elif ch in ")]}":
            depth2 -= 1
        if ch == "," and depth2 == 0:
            params.append(buf)
            buf = ""
        else:
            buf += ch
    if buf.strip():
        params.append(buf)

    untyped: list[str] = []
    for raw in params:
        p = raw.strip()
        if not p:
            continue
        if p in {"self", "cls", "*", "/"}:
            continue
        if p.startswith("*"):
            continue
        # Remove default value
        if "=" in p:
            p = p.split("=", 1)[0].strip()
        # Type annotation?
        if ":" in p:
            continue
        untyped.append(p)
    return fname, untyped


def check_e(tlits: list[tuple[int, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for lineno, lit in tlits:
        # Find each ``def ...`` start and try to scan it as a signature
        for m in re.finditer(r"(^|\n)(\s*def\s+\w+\s*\()", lit):
            start = m.start(2)
            parsed = _parse_signature_line(lit[start:])
            if not parsed:
                continue
            fname, untyped = parsed
            if not untyped:
                continue
            sig_preview = lit[start:start + 200].splitlines()[0]
            key = f"{fname}|{','.join(untyped)}"
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "location": f"line {lineno}",
                "function": fname,
                "signature": sig_preview,
                "missing_types": untyped,
            })
    return out


# --------------------------------------------------------------------------
# Dimension F — file-deletion calls inside transform()
# --------------------------------------------------------------------------

DELETE_FUNCS = {"unlink", "remove", "rmtree"}


def check_f(tree: ast.Module) -> list[dict[str, Any]]:
    tnode = find_transform_node(tree)
    if not tnode:
        return []
    out: list[dict[str, Any]] = []
    for node in ast.walk(tnode):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        fname = None
        if isinstance(f, ast.Attribute):
            fname = f.attr
        elif isinstance(f, ast.Name):
            fname = f.id
        if fname not in DELETE_FUNCS:
            continue
        # Try to resolve a string-literal path arg (positional or keyword)
        path_repr = "<dynamic>"
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                path_repr = arg.value
                break
        out.append({
            "call": fname,
            "line": node.lineno,
            "path": path_repr,
        })
    return out


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def audit_one(id: str) -> dict[str, Any]:
    script = HERE / f"{id}.py"
    if not script.exists():
        return {
            "script_path": str(script),
            "issues": {},
            "error": "script not found",
        }
    tree = parse_script(script)
    body = extract_assign(tree, "BODY") or ""
    tlits = script_payload_literals(tree)

    return {
        "script_path": str(script),
        "issues": {
            "A1": check_a1(tlits=tlits, body=body),
            "A2": check_a2(tree),
            "B": check_b(tree),
            "C1": check_c1(tlits),
            "C2": check_c2(id=id, tree=tree, tlits=tlits),
            "D": check_d(body),
            "E": check_e(tlits),
            "F": check_f(tree),
        },
    }


def render_md(audit: dict[str, dict[str, Any]]) -> str:
    out_lines: list[str] = []
    out_lines.append("# mech_scheduler audit — phase 1\n")
    out_lines.append(
        "Read-only audit of every transform script in the "
        "`tom_refactor_202605a/primary/mech_scheduler` chain. Each section "
        "lists hits per dimension. "
        "Generated by "
        "`refactor_202605a/_audit_mech_scheduler.py`.\n"
    )
    out_lines.append("## Dimensions\n")
    out_lines.append(
        "- **A1** hardcoded code blocks in transform()-scope string literals\n"
        "- **A2** ≥3 .replace()/re.sub() calls inside transform()\n"
        "- **B** insert_after/insert_before anchor strings (informational)\n"
        "- **C1** prose comment lines (`# ...`) embedded in literals\n"
        "- **C2** comments present in source method body but missing from the "
        "transform literal blob (move scripts only)\n"
        "- **D** numbers in commit BODY that aren't in the structural-enum "
        "whitelist (e.g. `2 callsites`, `13 dispatch tuples`)\n"
        "- **E** `def ...` signatures inside literals with untyped params\n"
        "- **F** file-deletion calls inside transform()\n"
    )

    # Summary counts.
    out_lines.append("\n## Summary\n")
    dim_counts: dict[str, int] = {d: 0 for d in "A1 A2 B C1 C2 D E F".split()}
    for entry in audit.values():
        for d, hits in entry["issues"].items():
            if hits:
                dim_counts[d] += 1
    out_lines.append("Scripts hit per dimension (out of "
                     f"{len(audit)}):\n")
    for d, n in dim_counts.items():
        out_lines.append(f"- **{d}**: {n}")
    out_lines.append("")

    # Per-script.
    for id, entry in audit.items():
        out_lines.append(f"\n## `{id}`\n")
        out_lines.append(f"Script: `{entry['script_path']}`\n")
        any_hit = False
        for d in ["A1", "A2", "B", "C1", "C2", "D", "E", "F"]:
            hits = entry["issues"].get(d) or []
            if not hits:
                continue
            any_hit = True
            out_lines.append(f"### {d} ({len(hits)} hits)\n")
            for h in hits[:20]:
                out_lines.append(f"- `{json.dumps(h, ensure_ascii=False)}`")
            if len(hits) > 20:
                out_lines.append(f"- … {len(hits) - 20} more elided")
            out_lines.append("")
        if not any_hit:
            out_lines.append("_no hits across A1–F._\n")

    return "\n".join(out_lines) + "\n"


def main() -> None:
    order = load_order()
    print(f"audit: {len(order)} scripts in ORDER", file=sys.stderr)

    audit: dict[str, dict[str, Any]] = {}
    for id in order:
        print(f"  - {id}", file=sys.stderr)
        audit[id] = audit_one(id)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    )
    (OUT_DIR / "audit.md").write_text(render_md(audit))
    print(f"wrote {OUT_DIR / 'audit.md'}", file=sys.stderr)
    print(f"wrote {OUT_DIR / 'audit.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
