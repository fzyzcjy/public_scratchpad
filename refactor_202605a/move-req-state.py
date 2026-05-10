#!/usr/bin/env python3
"""Move ReqState dataclass + _init_req_state method out of tokenizer_manager.py
into a new ``managers/request_state.py`` module. The method becomes a free
function ``init_req(rid_to_state, *, obj, request=None, enable_trace, disagg_mode)``
with the three ``self.X`` reads turned into explicit kwargs.
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
    find_class_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "move-req-state"
SUBJECT = "Move ReqState and init_req to managers/request_state.py"
BODY = """\
ReqState dataclass moves verbatim. _init_req_state becomes a free function
init_req(rid_to_state, *, obj, request, enable_trace, disagg_mode); the three
self.X reads (server_args.enable_trace, rid_to_state, disaggregation_mode)
become explicit kwargs/positional. Three callers in tokenizer_manager.py
update accordingly. No behavior change.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import asyncio
import dataclasses
from typing import Any, Dict, List, Optional, Union

import fastapi

from sglang.srt.disaggregation.utils import DisaggregationMode
from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput
from sglang.srt.observability.req_time_stats import APIServerReqTimeStats
from sglang.srt.observability.trace import extract_trace_headers


'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/request_state.py"

    # Cut bottom-up so earlier line ranges stay valid.
    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="_init_req_state"
    )
    method_text = cut_lines(tm, s, e)

    s, e = find_class_lines(tm.read_text(), class_name="ReqState")
    class_text = cut_lines(tm, s, e)

    # ReqState moves byte-identical (including the @dataclasses.dataclass decorator
    # and trailing blank line).
    # _init_req_state -> init_req (free function): drop self, add explicit kwargs.
    fn_text = dedent_method_to_function(method_text)
    fn_text = fn_text.replace(
        "def _init_req_state(\n    self,\n    obj: Union[GenerateReqInput, EmbeddingReqInput],\n    request: Optional[fastapi.Request] = None,\n):",
        "def init_req(\n    rid_to_state: Dict[str, ReqState],\n    *,\n    obj: Union[GenerateReqInput, EmbeddingReqInput],\n    request: Optional[fastapi.Request] = None,\n    enable_trace: bool,\n    disagg_mode: DisaggregationMode,\n) -> None:",
    )
    fn_text = fn_text.replace(
        "        if self.server_args.enable_trace:",
        "        if enable_trace:",
    )
    fn_text = fn_text.replace(
        "    if self.server_args.enable_trace:",
        "    if enable_trace:",
    )
    fn_text = fn_text.replace(
        "if rid in self.rid_to_state:",
        "if rid in rid_to_state:",
    )
    fn_text = fn_text.replace(
        "time_stats = APIServerReqTimeStats(disagg_mode=self.disaggregation_mode)",
        "time_stats = APIServerReqTimeStats(disagg_mode=disagg_mode)",
    )
    fn_text = fn_text.replace(
        "self.rid_to_state[rid] = state",
        "rid_to_state[rid] = state",
    )

    new.write_text(HEADER + class_text.rstrip() + "\n\n\n" + fn_text.rstrip() + "\n")

    # Update tokenizer_manager.py: callers + import.
    text = tm.read_text()
    # Caller 1: generate_request — full kwargs (request passed)
    text = replace_call_site(
        text,
        old="        self._init_req_state(obj, request)",
        new=(
            "        init_req(\n"
            "            self.rid_to_state,\n"
            "            obj=obj,\n"
            "            request=request,\n"
            "            enable_trace=self.server_args.enable_trace,\n"
            "            disagg_mode=self.disaggregation_mode,\n"
            "        )"
        ),
    )
    # Caller 2 & 3: _handle_batch_request — without request (use replace_all by count)
    text = text.replace(
        "                self._init_req_state(tmp_obj)\n",
        (
            "                init_req(\n"
            "                    self.rid_to_state,\n"
            "                    obj=tmp_obj,\n"
            "                    enable_trace=self.server_args.enable_trace,\n"
            "                    disagg_mode=self.disaggregation_mode,\n"
            "                )\n"
        ),
    )
    text = text.replace(
        "                    self._init_req_state(tmp_obj)\n",
        (
            "                    init_req(\n"
            "                        self.rid_to_state,\n"
            "                        obj=tmp_obj,\n"
            "                        enable_trace=self.server_args.enable_trace,\n"
            "                        disagg_mode=self.disaggregation_mode,\n"
            "                    )\n"
        ),
    )
    # Add import (after async_dynamic_batch_tokenizer line).
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition="from sglang.srt.managers.request_state import ReqState, init_req\n",
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
