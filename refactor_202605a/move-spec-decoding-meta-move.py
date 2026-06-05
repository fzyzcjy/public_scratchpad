#!/usr/bin/env python3
"""Mechanical move of _calculate_spec_decoding_metrics (staticmethod form)
out of TokenizerManager into ``managers/tokenizer_manager_components/spec_decoding_meta.py`` as free
function ``fill_spec_decoding_meta``. Prep landed in
``move-spec-decoding-meta-prep``.
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

ID = "move-spec-decoding-meta-move"
SUBJECT = "Move _calculate_spec_decoding_metrics to managers/tokenizer_manager_components/spec_decoding_meta.py as fill_spec_decoding_meta"
BODY = """\
Physical move only:
  - Cut staticmethod from TM
  - Drop @staticmethod, dedent
  - Rename _calculate_spec_decoding_metrics -> fill_spec_decoding_meta
  - Write managers/tokenizer_manager_components/spec_decoding_meta.py
  - Caller: TokenizerManager._calculate_spec_decoding_metrics(...) ->
    spec_decoding_meta.fill_spec_decoding_meta(...)
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

from typing import Any, Dict, Union

from sglang.srt.managers.io_struct import (
    BatchEmbeddingOutput,
    BatchStrOutput,
    BatchTokenIDOutput,
)


'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/spec_decoding_meta.py"

    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="_calculate_spec_decoding_metrics"
    )
    method_text = cut_lines(tm, s, e)

    lines = method_text.splitlines(keepends=True)
    decorator_idx = next(i for i, l in enumerate(lines) if l.strip() == "@staticmethod")
    lines = lines[:decorator_idx] + lines[decorator_idx + 1 :]
    dedented = [l[4:] if l.startswith("    ") else l for l in lines]
    fn_text = "".join(dedented).replace(
        "def _calculate_spec_decoding_metrics(", "def fill_spec_decoding_meta(", 1
    )

    new.write_text(HEADER + fn_text.rstrip() + "\n")

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition="from sglang.srt.managers.tokenizer_manager_components import spec_decoding_meta\n",
    )
    text = replace_call_site(
        text,
        old="TokenizerManager._calculate_spec_decoding_metrics(",
        new="spec_decoding_meta.fill_spec_decoding_meta(",
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
