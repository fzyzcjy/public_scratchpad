#!/usr/bin/env python3
"""Move convert_to_span_attrs out of tokenizer_manager.py to a new
``managers/request_tracing.py`` module as free function ``make_span_attrs``.
The two ``self.X`` reads (server_args.enable_trace early-return and
served_model_name) become explicit kwargs; per design (request_tracing.md
ch4) the early-return is removed (caller already gates on tracing_enable).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import (
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "move-request-tracing"
SUBJECT = "Move convert_to_span_attrs to managers/request_tracing.py"
BODY = """\
convert_to_span_attrs becomes free function make_span_attrs in a new
managers/request_tracing.py module. self.served_model_name is replaced
with a served_model_name kwarg; the early-return on
self.server_args.enable_trace is removed because the caller already gates
on state.time_stats.trace_ctx.tracing_enable (per request_tracing.md ch4
'enable_trace 检查由 caller 做'). Single caller in _handle_batch_output
updates accordingly. No behavior change.
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
from sglang.srt.managers.request_state import ReqState
from sglang.srt.observability.trace import SpanAttributes


'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/request_tracing.py"

    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="convert_to_span_attrs"
    )
    method_text = cut_lines(tm, s, e)

    fn_text = dedent_method_to_function(method_text)
    fn_text = fn_text.replace(
        "def convert_to_span_attrs(\n    self,\n    state: ReqState,\n    recv_obj: Union[\n        BatchStrOutput,\n        BatchEmbeddingOutput,\n        BatchTokenIDOutput,\n    ],\n    i: int,\n) -> Dict[str, Any]:",
        "def make_span_attrs(\n    *,\n    state: ReqState,\n    recv_obj: Union[\n        BatchStrOutput,\n        BatchEmbeddingOutput,\n        BatchTokenIDOutput,\n    ],\n    i: int,\n    served_model_name: str,\n) -> Dict[str, Any]:",
    )
    # Drop the early-return guarded by self.server_args.enable_trace
    # (caller already guards on tracing_enable; per design).
    fn_text = fn_text.replace(
        "    if not self.server_args.enable_trace:\n        return span_attrs\n\n",
        "",
    )
    fn_text = fn_text.replace(
        "span_attrs[SpanAttributes.GEN_AI_RESPONSE_MODEL] = self.served_model_name",
        "span_attrs[SpanAttributes.GEN_AI_RESPONSE_MODEL] = served_model_name",
    )

    new.write_text(HEADER + fn_text.rstrip() + "\n")

    # ===== Update tokenizer_manager.py caller =====
    text = tm.read_text()

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition="from sglang.srt.managers import request_tracing\n",
    )

    text = replace_call_site(
        text,
        old="self.convert_to_span_attrs(state, recv_obj, i)",
        new=(
            "request_tracing.make_span_attrs(\n"
            "                            state=state,\n"
            "                            recv_obj=recv_obj,\n"
            "                            i=i,\n"
            "                            served_model_name=self.served_model_name,\n"
            "                        )"
        ),
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
