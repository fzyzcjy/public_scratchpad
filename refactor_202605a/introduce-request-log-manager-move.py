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
from _helpers import cut_lines, find_method_lines, rewrite_intra_class_calls
from _runner import run_pr

ID = "introduce-request-log-manager-move"
SUBJECT = "Hand request dumping over to RequestLogManager"
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
import time
from datetime import datetime
from typing import Dict

from sglang.srt.environ import envs
from sglang.srt.managers.tokenizer_manager_components.request_state import ReqState
from sglang.srt.observability.req_time_stats import (
    convert_time_to_realtime,
    real_time,
)
from sglang.srt.utils.cudacore_pyspy_dump_utils import (
    collect_scheduler_processes,
    pyspy_dump_schedulers,
    trigger_cuda_user_coredump,
)

logger = logging.getLogger(__name__)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    rlm = wt / "python/sglang/srt/managers/tokenizer_manager_components/request_log_manager.py"

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

    # Strip @staticmethod + restore plain self for the 4 methods we keep,
    # then flip intra-class qualifier on cross-method calls.
    kept = []
    for n in ("dump_requests", "record_request_for_crash_dump", "_dump_data_to_file", "dump_requests_before_crash"):
        body = cut_blocks[n]
        body = body.replace("    @staticmethod\n", "", 1)
        body = body.replace('self: "RequestLogManager", ', "self, ")
        body = body.replace('self: "RequestLogManager",\n', "self,\n")
        body = rewrite_intra_class_calls(
            body,
            source_classes=["TokenizerManager"],
            target_class="RequestLogManager",
            methods=list(method_names),
        )
        kept.append(body.rstrip())

    rlm_text = rlm.read_text()
    rlm_text = rlm_text.replace(
        "from dataclasses import dataclass, field\n",
        "from dataclasses import dataclass, field\n\n" + EXTRA_IMPORTS,
    )
    rlm.write_text(rlm_text.rstrip() + "\n\n" + "\n\n".join(kept) + "\n")

    # Caller prefix replacement in TM:
    # TokenizerManager.<m>(self.request_log_manager, ...) → self.request_log_manager.<m>(...)
    # Use regex to absorb both single-line and black-wrapped multi-line forms.
    import re as _re

    text = tm.read_text()

    def _rewrite_call(text: str, method: str) -> str:
        # Match TokenizerManager.<method>(\s* self.request_log_manager ,\s* ARGS )
        # where ARGS may span multiple lines (no nested parens in our call sites).
        pat = _re.compile(
            rf"TokenizerManager\.{_re.escape(method)}"
            rf"\(\s*self\.request_log_manager\s*,\s*([^()]*?)\s*\)",
            _re.DOTALL,
        )
        return pat.sub(
            lambda m: f"self.request_log_manager.{method}({_re.sub(r'\\s+', ' ', m.group(1)).strip()})",
            text,
        )

    text = _rewrite_call(text, "dump_requests")
    text = _rewrite_call(text, "record_request_for_crash_dump")
    text = _rewrite_call(text, "dump_requests_before_crash")
    tm.write_text(text)

    multi = wt / "python/sglang/srt/managers/multi_tokenizer_mixin.py"
    if multi.exists():
        t = multi.read_text()
        # Regex variant of the same rewrite — tolerates any indent on the
        # ``func.__self__.request_log_manager,`` line. The previous literal
        # hardcoded 12-space indent but black actually emits 16 sp inside the
        # surrounding ``if isinstance(...)`` block, so the literal was a no-op.
        t = _re.sub(
            r"TokenizerManager\.dump_requests_before_crash\(\s*func\.__self__\.request_log_manager,\s*",
            "func.__self__.request_log_manager.dump_requests_before_crash(",
            t,
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
