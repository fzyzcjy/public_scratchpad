#!/usr/bin/env python3
"""Introduce RequestLogManager owner class.

Move 4 dump-related methods (dump_requests / record_request_for_crash_dump /
_dump_data_to_file / dump_requests_before_crash) plus the
init_request_logging_and_dumping body and configure_logging's dump-field
assignments into a new
@dataclass(slots=True, kw_only=True) RequestLogManager (frozen=False;
mutable dump lists + dump_requests_folder etc.).

PR1: method names + field names kept (no observe_finished merge / no rename).
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
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "introduce-request-log-manager"
SUBJECT = "Introduce RequestLogManager and move dump methods"
BODY = """\
Move 4 dump methods (dump_requests, record_request_for_crash_dump,
_dump_data_to_file, dump_requests_before_crash) from TokenizerManager into
a new managers/observability/request_log_manager.py module as a
@dataclass(slots=True, kw_only=True) RequestLogManager (frozen=False
because dump_request_list / crash_dump_request_list / crash_dump_performed
mutate over the lifecycle, and dump_requests_folder / threshold mutate
through configure_logging).

The init_request_logging_and_dumping body becomes a
RequestLogManager.from_server_args classmethod factory.

Owns request_logger / request_metrics_exporter_manager / dump_requests_folder /
dump_requests_threshold / dump_requests_exclude_meta_keys / crash_dump_folder /
dump_request_list / crash_dump_request_list / crash_dump_performed.

Caller updates:
  TokenizerManager generate_request : self.request_logger.log_received_request
    -> self.request_log_manager.request_logger.log_received_request
  TokenizerManager._handle_batch_output: same pattern + request_metrics_exporter_manager
  TokenizerManager.configure_logging   : redirects writes to
    self.request_log_manager.<field>
  Conditional check on dump_requests_folder in _handle_batch_output redirects
    to self.request_log_manager.dump_requests_folder

Per md ch3.1 PR1 form: method/field names retained (no rename to observe_finished
/ metrics_exporter etc.); ch3.2 PR2/PR3 actions deferred to Ch2.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import asyncio
import json
import logging
import os
import pickle
import socket
import sys
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import fastapi

from sglang.srt.managers.io_struct import ConfigureLoggingReq
from sglang.srt.managers.request_state import ReqState
from sglang.srt.observability.req_time_stats import (
    convert_time_to_realtime,
    real_time,
)
from sglang.srt.observability.request_metrics_exporter import (
    RequestMetricsExporterManager,
)
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils.request_logger import RequestLogger

logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True)
class RequestLogManager:
    """Per-request logging + periodic dump + 5-min rolling crash dump."""

    server_args: ServerArgs
    request_logger: RequestLogger
    request_metrics_exporter_manager: RequestMetricsExporterManager
    dump_requests_folder: str = ""
    dump_requests_threshold: int = 1000
    dump_requests_exclude_meta_keys: List[str] = field(
        default_factory=lambda: ["routed_experts", "hidden_states"]
    )
    crash_dump_folder: str = ""
    dump_request_list: List[Tuple] = field(default_factory=list)
    crash_dump_request_list: deque = field(default_factory=deque)
    crash_dump_performed: bool = False

    @classmethod
    def from_server_args(cls, *, server_args: ServerArgs) -> "RequestLogManager":
        request_logger = RequestLogger(
            log_requests=server_args.log_requests,
            log_requests_level=server_args.log_requests_level,
            log_requests_format=server_args.log_requests_format,
            log_requests_target=server_args.log_requests_target,
        )
        _, obj_skip_names, out_skip_names = request_logger.metadata
        request_metrics_exporter_manager = RequestMetricsExporterManager(
            server_args, obj_skip_names, out_skip_names
        )
        return cls(
            server_args=server_args,
            request_logger=request_logger,
            request_metrics_exporter_manager=request_metrics_exporter_manager,
            crash_dump_folder=server_args.crash_dump_folder,
        )

'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    obs_dir = wt / "python/sglang/srt/managers/observability"
    obs_dir.mkdir(exist_ok=True)
    (obs_dir / "__init__.py").write_text("")
    new = obs_dir / "request_log_manager.py"

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

    # init_request_logging_and_dumping body is replaced by factory in HEADER; discard.
    # Build the class body from the 4 dump methods (in original file order).
    method_bodies = [
        cut_blocks["dump_requests"],
        cut_blocks["record_request_for_crash_dump"],
        cut_blocks["_dump_data_to_file"],
        cut_blocks["dump_requests_before_crash"],
    ]

    def rewrite(body: str) -> str:
        # self.server_args.X stays (RequestLogManager owns server_args).
        # self.rid_to_state -> rid_to_state (for dump_requests_before_crash, which now
        # takes rid_to_state as kwarg per design md L74).
        body = body.replace("self.rid_to_state.items()", "rid_to_state.items()")
        body = body.replace("self.rid_to_state[", "rid_to_state[")
        return body

    # Convert dump_requests_before_crash signature to take rid_to_state as kwarg.
    method_bodies[3] = method_bodies[3].replace(
        "def dump_requests_before_crash(\n        self,",
        "def dump_requests_before_crash(\n        self,\n        *,\n        rid_to_state: Dict[str, ReqState],",
    )
    rewritten = [rewrite(b).rstrip() for b in method_bodies]
    new.write_text(HEADER + "\n\n".join(rewritten) + "\n")

    # ===== tokenizer_manager.py: caller updates + ctor wiring + import =====
    text = tm.read_text()

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.observability.request_log_manager import RequestLogManager\n",
    )

    # Wire construction in __init__: insert before request_validator block.
    text = replace_call_site(
        text,
        old=(
            "        # Request validator\n"
            "        self.request_validator = RequestValidator(\n"
        ),
        new=(
            "        # Request log manager\n"
            "        self.request_log_manager = RequestLogManager.from_server_args(\n"
            "            server_args=self.server_args,\n"
            "        )\n"
            "\n"
            "        # Request validator\n"
            "        self.request_validator = RequestValidator(\n"
        ),
    )

    # Replace the init_request_logging_and_dumping() call (now no longer needed
    # since RequestLogManager.from_server_args does the work in its factory).
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

    # configure_logging redirects: log level -> request_log_manager.request_logger,
    # dump fields -> request_log_manager.<field>.
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

    # Conditional check in _handle_batch_output: `if self.dump_requests_folder and ...`
    text = text.replace(
        "if self.dump_requests_folder and state.finished and state.obj.log_metrics:",
        "if self.request_log_manager.dump_requests_folder and state.finished and state.obj.log_metrics:",
    )

    # External callers of dump methods (dump_requests / record_request_for_crash_dump
    # / dump_requests_before_crash). Find them in facade.
    text = text.replace(
        "self.dump_requests(state, out_dict)",
        "self.request_log_manager.dump_requests(state, out_dict)",
    )
    text = text.replace(
        "self.record_request_for_crash_dump(state, out_dict)",
        "self.request_log_manager.record_request_for_crash_dump(state, out_dict)",
    )
    # dump_requests_before_crash callers: now requires rid_to_state kwarg.
    # 1. SignalHandler.running_phase_sigquit_handler call: tokenizer_manager.dump_requests_before_crash() ->
    #    tokenizer_manager.request_log_manager.dump_requests_before_crash(rid_to_state=tokenizer_manager.rid_to_state)
    text = text.replace(
        "self.tokenizer_manager.dump_requests_before_crash()",
        "self.tokenizer_manager.request_log_manager.dump_requests_before_crash(\n"
        "            rid_to_state=self.tokenizer_manager.rid_to_state,\n"
        "        )",
    )
    # 2. print_exception_wrapper / other facade-internal callers (without args):
    text = text.replace(
        "self.dump_requests_before_crash()",
        "self.request_log_manager.dump_requests_before_crash(rid_to_state=self.rid_to_state)",
    )
    # 3. print_exception_wrapper closure: func.__self__.dump_requests_before_crash() ->
    #    func.__self__.request_log_manager.dump_requests_before_crash(rid_to_state=...)
    text = text.replace(
        "func.__self__.dump_requests_before_crash()",
        "func.__self__.request_log_manager.dump_requests_before_crash(\n"
        "            rid_to_state=func.__self__.rid_to_state,\n"
        "        )",
    )

    tm.write_text(text)

    # multi_tokenizer_mixin.py also has print_exception_wrapper duplicated.
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


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
