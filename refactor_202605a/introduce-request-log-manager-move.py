#!/usr/bin/env python3
"""Move dump methods to RequestLogManager + drop init_request_logging_and_dumping."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, replace_call_site
from _runner import run_pr

ID = "introduce-request-log-manager-move"
SUBJECT = "Move dump methods to RequestLogManager"
BODY = """\
Cut 4 dump methods + init_request_logging_and_dumping from TM into
RequestLogManager. Drop init_request_logging_and_dumping() call (factory
does the work). Update callers + entrypoints + multi_tokenizer_mixin.

Sig change for dump_requests_before_crash: takes rid_to_state as kwarg.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import asyncio
import json
import logging
import os
import pickle
import socket
import sys
from datetime import datetime
from typing import Any, Dict, Optional

import fastapi

from sglang.srt.managers.io_struct import ConfigureLoggingReq
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

    # Cut bottom-up.
    method_names = (
        "init_request_logging_and_dumping",
        "dump_requests",
        "record_request_for_crash_dump",
        "_dump_data_to_file",
        "dump_requests_before_crash",
    )
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    # init_request_logging_and_dumping body discarded (factory does it).
    method_bodies = [
        cut_blocks["dump_requests"],
        cut_blocks["record_request_for_crash_dump"],
        cut_blocks["_dump_data_to_file"],
        cut_blocks["dump_requests_before_crash"],
    ]

    def rewrite(body: str) -> str:
        body = body.replace("self.rid_to_state.items()", "rid_to_state.items()")
        body = body.replace("self.rid_to_state[", "rid_to_state[")
        return body

    # Convert dump_requests_before_crash signature to take rid_to_state as kwarg.
    method_bodies[3] = method_bodies[3].replace(
        "def dump_requests_before_crash(\n        self,",
        "def dump_requests_before_crash(\n        self,\n        *,\n        rid_to_state: Dict[str, ReqState],",
    )
    rewritten = [rewrite(b).rstrip() for b in method_bodies]

    rlm_text = rlm.read_text()
    rlm_text = rlm_text.replace(
        "from dataclasses import dataclass, field\n",
        "from dataclasses import dataclass, field\n\n" + EXTRA_IMPORTS,
    )
    rlm.write_text(rlm_text.rstrip() + "\n\n" + "\n\n".join(rewritten) + "\n")

    # Drop init_request_logging_and_dumping() call.
    text = tm.read_text()
    text = replace_call_site(
        text,
        old="        # Init logging and dumping\n        self.init_request_logging_and_dumping()\n",
        new="",
    )

    # Caller updates.
    text = text.replace(
        "self.request_logger.log_received_request(",
        "self.request_log_manager.request_logger.log_received_request(",
    )
    text = text.replace(
        "self.request_logger.log_finished_request(",
        "self.request_log_manager.request_logger.log_finished_request(",
    )
    text = text.replace(
        "self.request_metrics_exporter_manager.exporter_enabled()",
        "self.request_log_manager.request_metrics_exporter_manager.exporter_enabled()",
    )
    text = text.replace(
        "self.request_metrics_exporter_manager.write_record(",
        "self.request_log_manager.request_metrics_exporter_manager.write_record(",
    )
    text = replace_call_site(
        text,
        old=(
            "        self.request_logger.configure(\n"
            "            log_requests=obj.log_requests,\n"
            "            log_requests_level=obj.log_requests_level,\n"
            "            log_requests_format=obj.log_requests_format,\n"
            "        )\n"
            "        if obj.dump_requests_folder is not None:\n"
            "            self.dump_requests_folder = obj.dump_requests_folder\n"
            "        if obj.dump_requests_threshold is not None:\n"
            "            self.dump_requests_threshold = obj.dump_requests_threshold\n"
            "        if obj.dump_requests_exclude_meta_keys is not None:\n"
            "            self.dump_requests_exclude_meta_keys = list(\n"
            "                obj.dump_requests_exclude_meta_keys\n"
            "            )\n"
            "        if obj.crash_dump_folder is not None:\n"
            "            self.crash_dump_folder = obj.crash_dump_folder\n"
        ),
        new=(
            "        self.request_log_manager.request_logger.configure(\n"
            "            log_requests=obj.log_requests,\n"
            "            log_requests_level=obj.log_requests_level,\n"
            "            log_requests_format=obj.log_requests_format,\n"
            "        )\n"
            "        if obj.dump_requests_folder is not None:\n"
            "            self.request_log_manager.dump_requests_folder = obj.dump_requests_folder\n"
            "        if obj.dump_requests_threshold is not None:\n"
            "            self.request_log_manager.dump_requests_threshold = obj.dump_requests_threshold\n"
            "        if obj.dump_requests_exclude_meta_keys is not None:\n"
            "            self.request_log_manager.dump_requests_exclude_meta_keys = list(\n"
            "                obj.dump_requests_exclude_meta_keys\n"
            "            )\n"
            "        if obj.crash_dump_folder is not None:\n"
            "            self.request_log_manager.crash_dump_folder = obj.crash_dump_folder\n"
        ),
    )
    text = text.replace(
        "if self.dump_requests_folder and state.finished and state.obj.log_metrics:",
        "if self.request_log_manager.dump_requests_folder and state.finished and state.obj.log_metrics:",
    )
    text = text.replace(
        "self.dump_requests(state, out_dict)",
        "self.request_log_manager.dump_requests(state, out_dict)",
    )
    text = text.replace(
        "self.record_request_for_crash_dump(state, out_dict)",
        "self.request_log_manager.record_request_for_crash_dump(state, out_dict)",
    )
    text = text.replace(
        "self.tokenizer_manager.dump_requests_before_crash()",
        "self.tokenizer_manager.request_log_manager.dump_requests_before_crash(\n"
        "            rid_to_state=self.tokenizer_manager.rid_to_state,\n"
        "        )",
    )
    text = text.replace(
        "self.dump_requests_before_crash()",
        "self.request_log_manager.dump_requests_before_crash(rid_to_state=self.rid_to_state)",
    )
    text = text.replace(
        "func.__self__.dump_requests_before_crash()",
        "func.__self__.request_log_manager.dump_requests_before_crash(\n"
        "            rid_to_state=func.__self__.rid_to_state,\n"
        "        )",
    )
    tm.write_text(text)

    multi = wt / "python/sglang/srt/managers/multi_tokenizer_mixin.py"
    if multi.exists():
        t = multi.read_text()
        t = t.replace(
            "func.__self__.dump_requests_before_crash()",
            "func.__self__.request_log_manager.dump_requests_before_crash(\n"
            "            rid_to_state=func.__self__.rid_to_state,\n"
            "        )",
        )
        multi.write_text(t)

    # Entrypoint rewrites.
    import glob
    import re as _re
    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        t = f.read_text()
        t = _re.sub(
            r"\btokenizer_manager\.request_logger\b",
            "tokenizer_manager.request_log_manager.request_logger",
            t,
        )
        f.write_text(t)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
