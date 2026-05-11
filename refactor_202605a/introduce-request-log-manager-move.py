#!/usr/bin/env python3
"""Move (pure cut/paste): RequestLogManager methods relocate from TM to target class."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines
from _runner import run_pr

ID = "introduce-request-log-manager-move"
SUBJECT = "Move RequestLogManager methods: pure cut/paste + caller prefix replacement"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut @staticmethod dump_requests
+ record_request_for_crash_dump + _dump_data_to_file +
dump_requests_before_crash from TokenizerManager; paste into
RequestLogManager (drop @staticmethod, replace
``self: "RequestLogManager"`` → plain ``self``). Discard the now-dead
init_request_logging_and_dumping (factory does the work). Caller prefix
replacement: ``TokenizerManager.<method>(self.request_log_manager, ...)``
→ ``self.request_log_manager.<method>(...)``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import asyncio
import logging
import os
import pickle
import socket
import sys
from datetime import datetime
from typing import Dict

from sglang.srt.managers.request_state import ReqState
from sglang.srt.observability.req_time_stats import (
    convert_time_to_realtime,
    real_time,
)

logger = logging.getLogger(__name__)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    rlm = wt / "python/sglang/srt/managers/request_log_manager.py"

    # Cut all 5 methods bottom-up so earlier line numbers stay valid.
    # init_request_logging_and_dumping body is discarded (factory replaced it).
    method_names = (
        "init_request_logging_and_dumping",
        "dump_requests",
        "record_request_for_crash_dump",
        "_dump_data_to_file",
        "dump_requests_before_crash",
    )
    name_to_start = {
        n: find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)[0]
        for n in method_names
    }
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_start[nn]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    # Strip @staticmethod + restore plain self for the 4 methods we keep.
    kept = []
    for n in ("dump_requests", "record_request_for_crash_dump", "_dump_data_to_file", "dump_requests_before_crash"):
        body = cut_blocks[n]
        body = body.replace("    @staticmethod\n", "", 1)
        body = body.replace('self: "RequestLogManager", ', "self, ")
        body = body.replace('self: "RequestLogManager",\n', "self,\n")
        kept.append(body.rstrip())

    rlm_text = rlm.read_text()
    rlm_text = rlm_text.replace(
        "from dataclasses import dataclass, field\n",
        "from dataclasses import dataclass, field\n\n" + EXTRA_IMPORTS,
    )
    rlm.write_text(rlm_text.rstrip() + "\n\n" + "\n\n".join(kept) + "\n")

    # Caller prefix replacement in TM:
    # TokenizerManager.<m>(self.request_log_manager, ...) → self.request_log_manager.<m>(...)
    text = tm.read_text()
    text = text.replace(
        "TokenizerManager.dump_requests(self.request_log_manager, state, out_dict)",
        "self.request_log_manager.dump_requests(state, out_dict)",
    )
    text = text.replace(
        "TokenizerManager.record_request_for_crash_dump(self.request_log_manager, state, out_dict)",
        "self.request_log_manager.record_request_for_crash_dump(state, out_dict)",
    )
    text = text.replace(
        "TokenizerManager.dump_requests_before_crash(\n"
        "                self.request_log_manager,\n"
        "                rid_to_state=self.rid_to_state,\n"
        "            )",
        "self.request_log_manager.dump_requests_before_crash(\n"
        "                rid_to_state=self.rid_to_state,\n"
        "            )",
    )
    tm.write_text(text)

    multi = wt / "python/sglang/srt/managers/multi_tokenizer_mixin.py"
    if multi.exists():
        t = multi.read_text()
        t = t.replace(
            "TokenizerManager.dump_requests_before_crash(\n"
            "            func.__self__.request_log_manager,\n"
            "            rid_to_state=func.__self__.rid_to_state,\n"
            "        )",
            "func.__self__.request_log_manager.dump_requests_before_crash(\n"
            "            rid_to_state=func.__self__.rid_to_state,\n"
            "        )",
        )
        multi.write_text(t)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
