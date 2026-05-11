#!/usr/bin/env python3
"""Cleanup: tokenizer_manager.py 模块顶层三个残留：
  1. 删除 dead const ``_REQUEST_STATE_WAIT_TIMEOUT`` (no longer referenced in TM
     since ``_wait_one_response`` was moved to ResponseEmitter, which carries
     its own copy).
  2. 移走 ``ServerStatus`` Enum 到独立 module ``server_status.py``。caller 改
     import 路径 (http_server.py + TM internal access)。
  3. 移走 ``print_exception_wrapper`` 到独立 module ``print_exception_wrapper.py``。
     避免与 TokenizerManager class 的循环 import：仅在 except 内部 late-import。

Per MECH_COMMIT_SPLIT §"例外：何时不拆": "移动一个已经存在的 module-level free
function | 单 commit（只有 move）"。三项都是机械搬运，合并成单 commit。
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
    find_class_lines,
    find_function_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "cleanup-tm-module-leftovers"
SUBJECT = "Cleanup tokenizer_manager.py module leftovers"
BODY = """\
Drop dead ``_REQUEST_STATE_WAIT_TIMEOUT`` constant from TM (no longer
referenced after ResponseEmitter took ownership of ``_wait_one_response``;
ResponseEmitter carries its own copy).

Move ``ServerStatus`` enum out to ``server_status.py`` and rewire the
http_server import path.

Move ``print_exception_wrapper`` out to ``print_exception_wrapper.py``;
the ``isinstance(func.__self__, TokenizerManager)`` check now uses a
local import inside the except clause to break the circular dependency
with TokenizerManager. The duplicate copy in ``multi_tokenizer_mixin.py``
stays (its cleanup branch is structurally different); dedup is deferred
to a non-mech follow-up.

After this commit, TM module level has only: ``logger``, the
``TokenizerManager`` class, ``SignalHandler`` (a TM-scoped callback
class that strongly depends on TM internals — kept here intentionally),
and the trailing abort-handling comment table.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SERVER_STATUS_MODULE = '''from __future__ import annotations

from enum import Enum


class ServerStatus(Enum):
    Up = "Up"
    Starting = "Starting"
    UnHealthy = "UnHealthy"
'''


PRINT_EXCEPTION_WRAPPER_MODULE = '''from __future__ import annotations

import logging
import os
import sys

from sglang.srt.utils import kill_process_tree
from sglang.utils import get_exception_traceback

logger = logging.getLogger(__name__)


async def print_exception_wrapper(func):
    """
    Sometimes an asyncio function does not print exception.
    We do another wrapper to handle the exception.
    """
    try:
        await func()
    except Exception:
        traceback = get_exception_traceback()
        logger.error(f"TokenizerManager hit an exception: {traceback}")
        # Late import: TokenizerManager imports this module, so resolving the
        # class name eagerly at module top would form a cycle.
        from sglang.srt.managers.tokenizer_manager import TokenizerManager

        if hasattr(func, "__self__") and isinstance(func.__self__, TokenizerManager):
            func.__self__.dump_requests_before_crash()
        kill_process_tree(os.getpid(), include_parent=True)
        sys.exit(1)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"
    server_status_mod = wt / "python/sglang/srt/managers/server_status.py"
    pew_mod = wt / "python/sglang/srt/managers/print_exception_wrapper.py"

    # ---- 1. Write the two new modules.
    server_status_mod.write_text(SERVER_STATUS_MODULE)
    pew_mod.write_text(PRINT_EXCEPTION_WRAPPER_MODULE)

    # ---- 2. Cut ServerStatus + print_exception_wrapper from TM.
    text = tm.read_text()
    s, e = find_class_lines(text, class_name="ServerStatus")
    cut_lines(tm, s, e)

    text = tm.read_text()
    s, e = find_function_lines(text, function_name="print_exception_wrapper")
    cut_lines(tm, s, e)

    # ---- 3. Drop the dead _REQUEST_STATE_WAIT_TIMEOUT line.
    text = tm.read_text()
    text = replace_call_site(
        text,
        old="_REQUEST_STATE_WAIT_TIMEOUT = envs.SGLANG_REQUEST_STATE_WAIT_TIMEOUT.get()\n\n",
        new="",
    )

    # ---- 4. Drop the ``from enum import Enum`` import if it's no longer used
    # (ServerStatus was the only consumer). Safer: leave it; ruff will F401-strip
    # on its per-commit pass if it's truly unused.

    # ---- 5. Add imports for the moved symbols.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_input_blocker import input_blocker_guard_region\n",
        addition=(
            "from sglang.srt.managers.print_exception_wrapper import print_exception_wrapper\n"
            "from sglang.srt.managers.server_status import ServerStatus\n"
        ),
    )
    tm.write_text(text)

    # ---- 6. Update http_server.py: split the combined import so ServerStatus
    # comes from the new module.
    ht = http_server.read_text()
    ht = ht.replace(
        "from sglang.srt.managers.tokenizer_manager import ServerStatus, TokenizerManager\n",
        "from sglang.srt.managers.server_status import ServerStatus\n"
        "from sglang.srt.managers.tokenizer_manager import TokenizerManager\n",
    )
    http_server.write_text(ht)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
