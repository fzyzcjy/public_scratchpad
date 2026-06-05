#!/usr/bin/env python3
"""Mechanical move of convert_to_span_attrs (staticmethod form) out of
TokenizerManager to ``managers/tokenizer_manager_components/request_tracing.py`` as free function
``make_span_attrs``. Per MECH_COMMIT_SPLIT: only physical relocation + the
rename ``convert_to_span_attrs`` -> ``make_span_attrs``.

The prep (sig reshape, ``self.X`` -> kwargs, early-return drop, caller to
``TokenizerManager.foo(...)`` form) already landed in
``move-request-tracing-prep``.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "move-request-tracing-move"
SUBJECT = "Move convert_to_span_attrs to managers/tokenizer_manager_components/request_tracing.py as make_span_attrs"
BODY = """\
Physical move only:
  - Cut @staticmethod convert_to_span_attrs from TokenizerManager
  - Drop ``@staticmethod`` decorator; dedent body to module level
  - Rename ``convert_to_span_attrs`` -> ``make_span_attrs`` (clearer name
    at module scope; absorbed per (2) of plan note 2026-05-11)
  - Write managers/tokenizer_manager_components/request_tracing.py with the needed imports
  - Update single caller in _handle_batch_output to ``request_tracing.make_span_attrs(...)``
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import json
from typing import Any, Dict, Union

from sglang.srt.managers.io_struct import (
    BatchEmbeddingOutput,
    BatchStrOutput,
    BatchTokenIDOutput,
)
from sglang.srt.managers.tokenizer_manager_components.request_state import ReqState
from sglang.srt.observability.trace import SpanAttributes


'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/request_tracing.py"

    # Cut staticmethod from TM.
    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="convert_to_span_attrs"
    )
    method_text = cut_lines(tm, s, e)

    # Drop @staticmethod decorator; dedent body 4 spaces.
    lines = method_text.splitlines(keepends=True)
    decorator_idx = next(i for i, l in enumerate(lines) if l.strip() == "@staticmethod")
    lines = lines[:decorator_idx] + lines[decorator_idx + 1 :]
    dedented = []
    for l in lines:
        if l.startswith("    "):
            dedented.append(l[4:])
        else:
            dedented.append(l)
    fn_text = "".join(dedented)
    # Rename
    fn_text = fn_text.replace("def convert_to_span_attrs(", "def make_span_attrs(", 1)

    new.write_text(HEADER + fn_text.rstrip() + "\n")

    # Update tokenizer_manager.py: import + caller
    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition="from sglang.srt.managers.tokenizer_manager_components import request_tracing\n",
    )
    text = replace_call_site(
        text,
        old="TokenizerManager.convert_to_span_attrs(",
        new="request_tracing.make_span_attrs(",
    )
    tm.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
