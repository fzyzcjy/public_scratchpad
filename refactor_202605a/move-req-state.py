#!/usr/bin/env python3
"""Move ReqState dataclass from tokenizer_manager.py into a new
``managers/request_state.py`` module. The ``_init_req_state`` method stays
on TokenizerManager in this commit (it still references ``ReqState`` via
the new import). Per MECH_COMMIT_SPLIT, the method's prep+move land in
two subsequent commits.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_class_lines, insert_after
from _runner import run_pr

ID = "move-req-state"
SUBJECT = "Move ReqState dataclass to managers/request_state.py"
BODY = """\
ReqState dataclass moves byte-identical to new module. _init_req_state
method stays on TokenizerManager in this commit; its body still
constructs ``ReqState(...)`` which now resolves via the new import.

Per MECH_COMMIT_SPLIT: prep+move for the method itself land in
``move-init-req-prep`` and ``move-init-req-move``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, Dict, List, Union

from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput
from sglang.srt.observability.req_time_stats import APIServerReqTimeStats


'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/request_state.py"

    s, e = find_class_lines(tm.read_text(), class_name="ReqState")
    class_text = cut_lines(tm, s, e)
    new.write_text(HEADER + class_text.rstrip() + "\n")

    # Add ReqState import to tokenizer_manager.py.
    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition="from sglang.srt.managers.request_state import ReqState\n",
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
