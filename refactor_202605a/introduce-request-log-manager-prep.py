#!/usr/bin/env python3
"""Inplace prep for ``introduce-request-log-manager``: build the
``RequestLogManager`` skeleton (dataclass + ``from_server_args`` factory)
in a new ``managers/request_log_manager.py``, wire ``self.request_log_manager``
into ``TokenizerManager.__init__`` (replacing the ``init_request_logging_and_dumping``
call), convert 4 dump methods (``dump_requests`` /
``record_request_for_crash_dump`` / ``_dump_data_to_file`` /
``dump_requests_before_crash``) to ``@staticmethod`` with
``self: RequestLogManager`` type-flip, and redirect field accesses + call
sites (incl. entrypoint ``SignalHandler``, ``print_exception_wrapper``,
``multi_tokenizer_mixin``, and ``entrypoints/openai/serving_base``) to the
class-qualified form ``TokenizerManager.<method>(self.request_log_manager,
...)``.

Bodies of the 4 dump methods stay inside ``TokenizerManager`` in this
commit (byte-identical wrt the post-move state, modulo decorator + the
``self: RequestLogManager`` annotation that ``introduce-request-log-manager-move``
will collapse to bare ``self``). One pragmatic deviation: the
``dump_requests_before_crash`` body still reads ``self.rid_to_state`` —
which is *not* a ``RequestLogManager`` field — so prep additionally adds a
``rid_to_state`` kwarg and rewrites the two ``self.rid_to_state`` reads
to ``rid_to_state`` (the minimal change required to let the body type-check
against ``self: RequestLogManager``).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-request-log-manager-prep"
SUBJECT = "Build RequestLogManager skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-request-log-manager`` mech move.

- Create ``managers/request_log_manager.py`` with a
  ``@dataclass(slots=True, kw_only=True)`` ``RequestLogManager`` that owns
  ``server_args`` / ``request_logger`` /
  ``request_metrics_exporter_manager`` / dump-related fields
  (``dump_requests_folder`` / ``dump_requests_threshold`` /
  ``dump_requests_exclude_meta_keys`` / ``crash_dump_folder`` /
  ``dump_request_list`` / ``crash_dump_request_list`` /
  ``crash_dump_performed``). ``from_server_args`` classmethod replaces the
  ``init_request_logging_and_dumping`` body.
- Wire ``self.request_log_manager = RequestLogManager.from_server_args(...)``
  in ``TokenizerManager.__init__``; drop the now-redundant
  ``init_request_logging_and_dumping`` method and its call.
- Convert 4 dump methods to ``@staticmethod`` with
  ``self: "RequestLogManager"`` annotation. Method bodies stay inside
  ``TokenizerManager`` (move commit will physically relocate them).
  Bodies are byte-identical, except ``dump_requests_before_crash`` adds a
  ``rid_to_state`` kwarg and rewrites the two ``self.rid_to_state`` reads
  to ``rid_to_state`` (RequestLogManager does not own ``rid_to_state``).
- Field-access redirects in ``TokenizerManager``:
    ``self.request_logger.X`` -> ``self.request_log_manager.request_logger.X``
    ``self.request_metrics_exporter_manager.X``
        -> ``self.request_log_manager.request_metrics_exporter_manager.X``
    ``self.dump_requests_folder`` / ``self.dump_requests_threshold`` /
    ``self.dump_requests_exclude_meta_keys`` / ``self.crash_dump_folder``
        -> ``self.request_log_manager.<field>``
- Method-call sites switched to class-qualified form (per
  MECH_COMMIT_SPLIT): ``self.dump_requests(...)``
  -> ``TokenizerManager.dump_requests(self.request_log_manager, ...)`` etc.
  External entrypoint callers (SignalHandler, print_exception_wrapper in
  tokenizer_manager.py, the duplicate print_exception_wrapper in
  multi_tokenizer_mixin.py) likewise switch to
  ``TokenizerManager.dump_requests_before_crash(<obj>.request_log_manager,
  rid_to_state=<obj>.rid_to_state)``.
- ``entrypoints/openai/serving_base.py`` reads
  ``tokenizer_manager.request_logger`` -> ``tokenizer_manager.request_log_manager.request_logger``.

No behavior change.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# The RequestLogManager skeleton — dataclass + factory, no dump methods yet.
# Dump methods are added in the move commit.
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


def _add_staticmethod_and_typeflip(method_text: str) -> str:
    """Prepend @staticmethod decorator (4-space indent) to a method block."""
    # Find the ``    def <name>(`` line and insert ``    @staticmethod\n`` above.
    lines = method_text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("def "):
            lines.insert(i, "    @staticmethod\n")
            return "".join(lines)
    raise RuntimeError("def line not found in method text")


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/request_log_manager.py"

    # 1. Create the RequestLogManager skeleton.
    new.write_text(HEADER)

    # 2. In TokenizerManager: convert each dump method to @staticmethod inplace,
    #    type-flip self -> self: "RequestLogManager".
    text = tm.read_text()

    for name in [
        "dump_requests",
        "record_request_for_crash_dump",
        "_dump_data_to_file",
    ]:
        s, e = find_method_lines(text, class_name="TokenizerManager", method_name=name)
        lines = text.splitlines(keepends=True)
        method_text = "".join(lines[s:e])
        anchor = f"    def {name}(self, "
        anchor_multiline = f"    def {name}(\n        self, "
        if anchor in method_text:
            new_method = method_text.replace(
                anchor,
                f'    @staticmethod\n    def {name}(self: "RequestLogManager", ',
                1,
            )
        elif anchor_multiline in method_text:
            new_method = method_text.replace(
                anchor_multiline,
                f'    @staticmethod\n    def {name}(\n        self: "RequestLogManager", ',
                1,
            )
        else:
            raise RuntimeError(f"signature shape unexpected for {name}")
        text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # dump_requests_before_crash: same staticmethod + typeflip, plus add
    # rid_to_state kwarg and rewrite the two ``self.rid_to_state`` body reads.
    s, e = find_method_lines(
        text, class_name="TokenizerManager", method_name="dump_requests_before_crash"
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    # Signature: ``def dump_requests_before_crash(\n        self, hostname: ...)``.
    anchor = "    def dump_requests_before_crash(\n        self, "
    if anchor not in method_text:
        raise RuntimeError("dump_requests_before_crash signature shape unexpected")
    new_method = method_text.replace(
        anchor,
        (
            "    @staticmethod\n"
            "    def dump_requests_before_crash(\n"
            '        self: "RequestLogManager",\n'
            "        *,\n"
            "        rid_to_state: Dict[str, ReqState],\n"
            "        "
        ),
        1,
    )
    new_method = new_method.replace(
        "for rid, state in self.rid_to_state.items():",
        "for rid, state in rid_to_state.items():",
    )
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # 3. Drop init_request_logging_and_dumping from TokenizerManager entirely
    #    (its body is replaced by the RequestLogManager.from_server_args factory).
    s, e = find_method_lines(
        text, class_name="TokenizerManager", method_name="init_request_logging_and_dumping"
    )
    lines = text.splitlines(keepends=True)
    text = "".join(lines[:s]) + "".join(lines[e:])

    # 4. Add import of RequestLogManager.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.request_log_manager import RequestLogManager\n",
    )

    # 5. Wire RequestLogManager construction + drop init_request_logging_and_dumping() call.
    text = replace_call_site(
        text,
        old=(
            "        # Init logging and dumping\n"
            "        self.init_request_logging_and_dumping()\n"
        ),
        new=(
            "        # Request log manager\n"
            "        self.request_log_manager = RequestLogManager.from_server_args(\n"
            "            server_args=self.server_args,\n"
            "        )\n"
        ),
    )

    # 6. Field-access redirects in TokenizerManager (request_logger,
    #    request_metrics_exporter_manager, dump_requests_folder, etc.).
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

    # configure_logging redirects (request_logger + dump fields).
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

    # Conditional check in _handle_batch_output.
    text = text.replace(
        "if self.dump_requests_folder and state.finished and state.obj.log_metrics:",
        "if self.request_log_manager.dump_requests_folder and state.finished and state.obj.log_metrics:",
    )

    # 7. Method-call sites -> class-qualified form ``TokenizerManager.foo(self.request_log_manager, ...)``.
    text = text.replace(
        "self.dump_requests(state, out_dict)",
        "TokenizerManager.dump_requests(self.request_log_manager, state, out_dict)",
    )
    text = text.replace(
        "self.record_request_for_crash_dump(state, out_dict)",
        "TokenizerManager.record_request_for_crash_dump(self.request_log_manager, state, out_dict)",
    )
    # ``self.dump_requests_before_crash()`` (sigterm_watchdog and one other) ->
    # ``TokenizerManager.dump_requests_before_crash(self.request_log_manager,
    #     rid_to_state=self.rid_to_state)``.
    text = text.replace(
        "self.dump_requests_before_crash()",
        (
            "TokenizerManager.dump_requests_before_crash(\n"
            "                self.request_log_manager,\n"
            "                rid_to_state=self.rid_to_state,\n"
            "            )"
        ),
    )
    # SignalHandler.running_phase_sigquit_handler:
    # ``self.tokenizer_manager.dump_requests_before_crash()``.
    text = text.replace(
        "self.tokenizer_manager.dump_requests_before_crash()",
        (
            "TokenizerManager.dump_requests_before_crash(\n"
            "            self.tokenizer_manager.request_log_manager,\n"
            "            rid_to_state=self.tokenizer_manager.rid_to_state,\n"
            "        )"
        ),
    )
    # print_exception_wrapper:
    # ``func.__self__.dump_requests_before_crash()``.
    text = text.replace(
        "func.__self__.dump_requests_before_crash()",
        (
            "TokenizerManager.dump_requests_before_crash(\n"
            "                func.__self__.request_log_manager,\n"
            "                rid_to_state=func.__self__.rid_to_state,\n"
            "            )"
        ),
    )

    tm.write_text(text)

    # 8. multi_tokenizer_mixin.py also has a print_exception_wrapper duplicate
    #    (TokenizerManager is already imported there).
    multi = wt / "python/sglang/srt/managers/multi_tokenizer_mixin.py"
    if multi.exists():
        t = multi.read_text()
        if "func.__self__.dump_requests_before_crash()" in t:
            t = t.replace(
                "func.__self__.dump_requests_before_crash()",
                (
                    "TokenizerManager.dump_requests_before_crash(\n"
                    "                func.__self__.request_log_manager,\n"
                    "                rid_to_state=func.__self__.rid_to_state,\n"
                    "            )"
                ),
            )
            multi.write_text(t)

    # 9. External entrypoint: tokenizer_manager.request_logger ->
    #    tokenizer_manager.request_log_manager.request_logger (covers
    #    serving_base.py and any other entrypoint reading this attribute).
    import glob
    import re as _re
    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        t = f.read_text()
        new_t = _re.sub(
            r"\btokenizer_manager\.request_logger\b",
            "tokenizer_manager.request_log_manager.request_logger",
            t,
        )
        if new_t != t:
            f.write_text(new_t)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
