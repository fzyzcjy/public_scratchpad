#!/usr/bin/env python3
"""Programmatic byte-equality audit for PR #26271
(sgl-project/sglang `tom/scheduler_init_style`).

The PR claims to be a purely mechanical refactor of
``python/sglang/srt/managers/scheduler.py``: 13 inline component
constructions inside ``Scheduler.__init__`` are extracted into
per-component ``init_<name>()`` methods, with no behavior change.

This script proves the claim by *programmatic* comparison instead of
eyeball review. It works without any prior knowledge of which 13 blocks
were extracted:

  1. Parse ``Scheduler`` from both BASE (= pre-refactor SHA) and VERIFY
     (= post-refactor SHA) via Python's ``ast`` module.
  2. Identify every method present in VERIFY's ``Scheduler`` but absent
     in BASE's ``Scheduler`` whose name starts with ``init_``. These are
     the "new" extraction methods.
  3. For each such method, take its body text (with class-level
     indentation preserved) and grep for it as a substring of BASE's
     ``Scheduler.__init__`` source. A hit proves the body is byte-for-
     byte identical to a block that used to live inside ``__init__``.
  4. The only intentional non-byte-equal change is ``server_args.X``
     → ``self.server_args.X`` inside ``init_lora_drainer`` (the original
     inline referenced the ``__init__`` formal parameter ``server_args``,
     which falls out of scope after extraction). If a method body
     doesn't match BASE as-is, the script retries after applying the
     reverse swap and reports the delta.

Defaults compare:
  BASE   = ``6e8fe176be9cc0dbbebee3e87a841359f4fa5daa``
           (parent of the extraction commit, == sglang main at the time)
  VERIFY = ``b0a410f2a3``
           (the ``server_args`` fix on top of the extraction commit)

Reproduce:

  # 1. Clone (or use an existing checkout of) sgl-project/sglang.
  git clone https://github.com/sgl-project/sglang.git
  cd sglang
  # The script fetches the PR branch if the SHA isn't reachable locally.
  git fetch origin pull/26271/head

  # 2. Run the audit (uv recommended; only stdlib otherwise).
  uv run --python 3.12 verify-scheduler-init-style-mechanical.py
  # or:  python3 verify-scheduler-init-style-mechanical.py

  # Override the comparison range:
  uv run ... -- --base <sha> --verify <sha> --repo /path/to/sglang

Exit code 0 iff every new ``init_<name>`` method is byte-equal to a
block that existed inside BASE's ``Scheduler.__init__`` (modulo the
documented ``server_args`` swap).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Optional

import typer

DEFAULT_BASE = "6e8fe176be9cc0dbbebee3e87a841359f4fa5daa"
DEFAULT_VERIFY = "b0a410f2a3"
DEFAULT_FILE = "python/sglang/srt/managers/scheduler.py"
DEFAULT_CLASS = "Scheduler"


@dataclass(frozen=True)
class MethodSrc:
    name: str
    body: str  # raw class-indented source of the method body (no def header)


def _git_show(repo: Path, ref: str, path: str) -> str:
    try:
        return subprocess.check_output(
            ["git", "show", f"{ref}:{path}"],
            cwd=repo,
            text=True,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as e:
        raise SystemExit(
            f"git show {ref}:{path} failed in {repo}:\n{e.stderr}\n"
            f"Hint: if {ref} is from PR #26271, run "
            f"`git fetch origin pull/26271/head` inside {repo}."
        )


def _find_class(tree: ast.AST, class_name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise SystemExit(f"class {class_name!r} not found")


def _method_body_source(
    cls: ast.ClassDef, method: ast.FunctionDef, src_lines: list[str]
) -> str:
    """Return the method body's raw source with class-level indentation.

    Uses the next sibling's lineno (or class end) as the upper bound so
    trailing inline comments / blank lines inside the body are captured.
    Trailing blank-line padding between methods is trimmed.
    """
    body_start = method.body[0].lineno - 1
    # Locate next sibling within the class to bound the body.
    siblings = cls.body
    idx = siblings.index(method)
    if idx + 1 < len(siblings):
        nxt = siblings[idx + 1]
        next_start = nxt.lineno - 1
        if isinstance(
            nxt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ) and nxt.decorator_list:
            next_start = nxt.decorator_list[0].lineno - 1
    else:
        next_start = method.end_lineno
    body = "".join(src_lines[body_start:next_start])
    while body.endswith("\n\n"):
        body = body[:-1]
    return body


def _extract_methods(
    text: str, class_name: str
) -> dict[str, MethodSrc]:
    tree = ast.parse(text)
    cls = _find_class(tree, class_name)
    src_lines = text.splitlines(keepends=True)
    out: dict[str, MethodSrc] = {}
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = MethodSrc(
                name=node.name,
                body=_method_body_source(cls, node, src_lines),
            )
    return out


def _init_body(text: str, class_name: str) -> str:
    methods = _extract_methods(text, class_name)
    if "__init__" not in methods:
        raise SystemExit(f"{class_name}.__init__ not found")
    return methods["__init__"].body


_REVERSE_FIX = (
    ("                self.server_args.max_loras_per_batch,",
     "                server_args.max_loras_per_batch,"),
    ("                self.server_args.lora_drain_wait_threshold,",
     "                server_args.lora_drain_wait_threshold,"),
)


def _apply_reverse_fix(body: str) -> str:
    """Undo the ``self.server_args`` swap to recover the original inline
    code, so it can be substring-matched against BASE.
    """
    out = body
    for new, old in _REVERSE_FIX:
        out = out.replace(new, old)
    return out


def _run(repo: Path, base: str, verify: str, file: str, class_name: str) -> None:
    base_text = _git_show(repo, base, file)
    verify_text = _git_show(repo, verify, file)

    base_methods = _extract_methods(base_text, class_name)
    verify_methods = _extract_methods(verify_text, class_name)
    base_init_body = _init_body(base_text, class_name)

    new_init_methods = [
        m
        for name, m in verify_methods.items()
        if name.startswith("init_") and name not in base_methods
    ]
    if not new_init_methods:
        raise SystemExit(
            "No new init_<name> methods found between base and verify. "
            "Either the refs are wrong or there's nothing to audit."
        )

    matched: list[tuple[str, str]] = []  # (name, note)
    mismatched: list[tuple[str, str]] = []  # (name, detail)
    base_init_call_count = 0

    for m in new_init_methods:
        # Look for the body as a substring of BASE's __init__.
        if m.body in base_init_body:
            matched.append((m.name, f"byte-equal ({len(m.body)} bytes)"))
            continue
        reversed_body = _apply_reverse_fix(m.body)
        if reversed_body != m.body and reversed_body in base_init_body:
            # Compute the number of lines swapped to label the note.
            n_lines = sum(1 for a, _ in _REVERSE_FIX if a in m.body)
            matched.append(
                (
                    m.name,
                    f"byte-equal modulo the documented "
                    f"server_args → self.server_args fix ({n_lines} lines)",
                )
            )
            continue
        # Show a short diff hint: first 3 lines that differ between m.body
        # and the closest substring of base_init_body. We don't try to
        # locate the closest match — just dump the body so the user can
        # eyeball it.
        snippet = "".join(m.body.splitlines(keepends=True)[:5])
        mismatched.append(
            (
                m.name,
                f"method body not found in BASE.__init__ (first 5 lines):\n"
                f"{snippet}",
            )
        )

    # Sanity check: every new init_<name>() called in VERIFY's __init__
    # should correspond to a new method we just verified.
    verify_init_body = verify_methods["__init__"].body
    for m in new_init_methods:
        call = f"        self.{m.name}()\n"
        if call in verify_init_body:
            base_init_call_count += 1

    width = max(len(n) for n, _ in matched + mismatched)
    for name, note in matched:
        print(f"  [{name:<{width}}] {note}")
    for name, detail in mismatched:
        print(f"  [{name:<{width}}] MISMATCH — {detail}")

    print()
    print(f"  base   = {base}")
    print(f"  verify = {verify}")
    print(f"  file   = {file}")
    print(f"  class  = {class_name}")
    print(f"  new init_<name> methods discovered: {len(new_init_methods)}")
    print(f"  callsites in VERIFY.__init__ that invoke a new method: "
          f"{base_init_call_count}")

    if mismatched:
        print()
        print(f"FAIL: {len(mismatched)} method(s) did not match BASE.")
        sys.exit(1)
    print()
    print(
        f"PASS: all {len(matched)} extracted methods are byte-equal to "
        f"the inline code that lived in BASE's {class_name}.__init__ "
        f"(modulo the documented server_args fix)."
    )


app = typer.Typer(add_completion=False, no_args_is_help=False)


@app.command()
def main(
    repo: Annotated[
        Path,
        typer.Option(help="Path to a sgl-project/sglang checkout."),
    ] = Path("."),
    base: Annotated[
        str,
        typer.Option(help="SHA / ref to use as the pre-refactor baseline."),
    ] = DEFAULT_BASE,
    verify: Annotated[
        str,
        typer.Option(help="SHA / ref to audit (post-refactor)."),
    ] = DEFAULT_VERIFY,
    file: Annotated[
        str,
        typer.Option(help="Path inside the repo to audit."),
    ] = DEFAULT_FILE,
    class_name: Annotated[
        str,
        typer.Option("--class", help="Class whose __init__ is being audited."),
    ] = DEFAULT_CLASS,
) -> None:
    repo = repo.resolve()
    if not (repo / ".git").exists():
        raise SystemExit(f"not a git checkout: {repo}")
    _run(repo, base, verify, file, class_name)


if __name__ == "__main__":
    app()
