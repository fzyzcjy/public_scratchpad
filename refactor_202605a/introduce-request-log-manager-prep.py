#!/usr/bin/env python3
"""Prep: RequestLogManager skeleton + composition + staticmethod conversion + caller rewrites."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-request-log-manager-prep"
SUBJECT = "Stage request dumping for handoff to RequestLogManager"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds RequestLogManager skeleton (+ from_server_args factory); wires
composition in TM.__init__; drops the init_request_logging_and_dumping()
call (factory does the work); converts dump_requests +
record_request_for_crash_dump + _dump_data_to_file +
dump_requests_before_crash to @staticmethod with
self: "RequestLogManager" annotation; applies body rewrites
(dump_requests_before_crash gains rid_to_state kwarg; self.rid_to_state
→ rid_to_state). Rewrites callers in TM, multi_tokenizer_mixin,
configure_logging, and entrypoints. Methods stay on TM in this commit;
the next commit's pure cut/paste + caller prefix replacement completes
the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import List, Tuple

from sglang.srt.observability.request_metrics_exporter import (
    RequestMetricsExporterManager,
)
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils.request_logger import RequestLogger


@dataclass(slots=True, kw_only=True)
class RequestLogManager:
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


def _method_ranges(text: str, class_name: str, method_name: str):
    """Return (start, body_start, end) line indices for a method (incl. decorators)."""
    tree = ast.parse(text)
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for i, node in enumerate(cls.body):
                if isinstance(node, func_types) and node.name == method_name:
                    start = node.lineno - 1
                    if node.decorator_list:
                        start = node.decorator_list[0].lineno - 1
                    body_start = node.body[0].lineno - 1
                    if i + 1 < len(cls.body):
                        end = cls.body[i + 1].lineno - 1
                        nxt = cls.body[i + 1]
                        if isinstance(nxt, func_types + (ast.ClassDef,)) and nxt.decorator_list:
                            end = nxt.decorator_list[0].lineno - 1
                    else:
                        end = node.end_lineno
                    return start, body_start, end
    raise ValueError(f"{class_name}.{method_name} not found")


# Replacement headers: @staticmethod + self: "RequestLogManager" typing. Bodies stay byte-identical
# except for dump_requests_before_crash which gains rid_to_state kwarg + s/self.rid_to_state/rid_to_state/.
NEW_DUMP_REQUESTS_HEADER = '''    @staticmethod
    def dump_requests(self: "RequestLogManager", state: ReqState, out_dict: dict):
'''

NEW_RECORD_CRASH_HEADER = '''    @staticmethod
    def record_request_for_crash_dump(self: "RequestLogManager", state: ReqState, out_dict: dict):
'''

NEW_DUMP_TO_FILE_HEADER = '''    @staticmethod
    def _dump_data_to_file(
        self: "RequestLogManager", data_list: List[Tuple], filename: str, log_message: str
    ):
'''

NEW_DUMP_BEFORE_CRASH_HEADER = '''    @staticmethod
    def dump_requests_before_crash(
        self: "RequestLogManager",
        *,
        rid_to_state: Dict[str, ReqState],
        hostname: str = os.getenv("HOSTNAME", socket.gethostname()),
    ):
'''


def _retag_method(text: str, method_name: str, new_header: str, body_rewrite=None) -> str:
    """Replace a method's def-line + decorators with new_header, keeping body intact.

    body_rewrite (optional): callable(body_text) -> body_text for in-place body edits.
    """
    s, body_s, e = _method_ranges(text, "TokenizerManager", method_name)
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])
    if body_rewrite is not None:
        body_text = body_rewrite(body_text)
    return "".join(lines[:s]) + new_header + body_text + "".join(lines[e:])


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/request_log_manager.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.tokenizer_manager_components.request_log_manager import RequestLogManager\n",
    )

    # Composition wiring (large-class-init-style): route the early
    # init_request_logging_and_dumping() slot through init_request_log_manager().
    text = replace_call_site(
        text,
        old="        # Init logging and dumping\n        self.init_request_logging_and_dumping()\n",
        new="        # Init logging and dumping\n        self.init_request_log_manager()\n",
    )
    text = replace_call_site(
        text,
        old="    def init_weight_update(self):\n",
        new=(
            "    def init_request_log_manager(self):\n"
            "        self.request_log_manager = RequestLogManager.from_server_args(\n"
            "            server_args=self.server_args,\n"
            "        )\n"
            "\n"
            "    def init_weight_update(self):\n"
        ),
    )

    # Convert 4 methods to @staticmethod with self: "RequestLogManager" typing. Bodies unchanged
    # except dump_requests_before_crash gains rid_to_state kwarg + body rewrite.
    text = _retag_method(text, "dump_requests", NEW_DUMP_REQUESTS_HEADER)
    text = _retag_method(text, "record_request_for_crash_dump", NEW_RECORD_CRASH_HEADER)
    text = _retag_method(text, "_dump_data_to_file", NEW_DUMP_TO_FILE_HEADER)

    def _rewrite_before_crash(body: str) -> str:
        body = body.replace("self.rid_to_state.items()", "rid_to_state.items()")
        body = body.replace("self.rid_to_state[", "rid_to_state[")
        return body

    text = _retag_method(
        text,
        "dump_requests_before_crash",
        NEW_DUMP_BEFORE_CRASH_HEADER,
        body_rewrite=_rewrite_before_crash,
    )

    # Caller rewrites — class-qualified calls now that methods are staticmethod-with-target-self.
    # log_received_request / log_finished_request / metrics exporter routed through new attr.
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

    # configure_logging redirects.
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

    # In-TM call sites for the 4 staticmethods → class-qualified form.
    text = text.replace(
        "if self.dump_requests_folder and state.finished and state.obj.log_metrics:",
        "if self.request_log_manager.dump_requests_folder and state.finished and state.obj.log_metrics:",
    )
    text = text.replace(
        "self.dump_requests(state, out_dict)",
        "TokenizerManager.dump_requests(self.request_log_manager, state, out_dict)",
    )
    text = text.replace(
        "self.record_request_for_crash_dump(state, out_dict)",
        "TokenizerManager.record_request_for_crash_dump(self.request_log_manager, state, out_dict)",
    )
    # Internal call _dump_data_to_file inside dump_requests body → class-qualified.
    text = text.replace(
        "            self._dump_data_to_file(\n"
        "                data_list=self.dump_request_list,\n",
        "            TokenizerManager._dump_data_to_file(\n"
        "                self,\n"
        "                data_list=self.dump_request_list,\n",
    )
    # The crash-dump recording gate must follow the same live component attr the
    # configure_logging endpoint now mutates (split-brain otherwise).
    text = replace_call_site(
        text,
        old="            if self.crash_dump_folder and state.finished and state.obj.log_metrics:\n",
        new=(
            "            if (\n"
            "                self.request_log_manager.crash_dump_folder\n"
            "                and state.finished\n"
            "                and state.obj.log_metrics\n"
            "            ):\n"
        ),
    )

    # dump_requests_before_crash callers inside TM (2 sites in sigterm/exception paths).
    text = text.replace(
        "self.dump_requests_before_crash()",
        "TokenizerManager.dump_requests_before_crash(\n"
        "                self.request_log_manager,\n"
        "                rid_to_state=self.rid_to_state,\n"
        "            )",
    )
    # The two remaining TM-file callers outside the class (print_exception_wrapper
    # and SignalHandler) must also follow the staged calling convention at this
    # commit; the move collapses them onto request_log_manager.
    text = text.replace(
        "            func.__self__.dump_requests_before_crash()\n",
        "            TokenizerManager.dump_requests_before_crash(\n"
        "                func.__self__.request_log_manager,\n"
        "                rid_to_state=func.__self__.rid_to_state,\n"
        "            )\n",
    )
    text = text.replace(
        "        self.tokenizer_manager.dump_requests_before_crash()\n",
        "        TokenizerManager.dump_requests_before_crash(\n"
        "            self.tokenizer_manager.request_log_manager,\n"
        "            rid_to_state=self.tokenizer_manager.rid_to_state,\n"
        "        )\n",
    )

    tm.write_text(text)

    # multi_tokenizer_mixin caller rewrite.
    multi = wt / "python/sglang/srt/managers/multi_tokenizer_mixin.py"
    if multi.exists():
        t = multi.read_text()
        t = t.replace(
            "func.__self__.dump_requests_before_crash()",
            "TokenizerManager.dump_requests_before_crash(\n"
            "            func.__self__.request_log_manager,\n"
            "            rid_to_state=func.__self__.rid_to_state,\n"
            "        )",
        )
        multi.write_text(t)

    # Entrypoint rewrites: tokenizer_manager.request_logger → tokenizer_manager.request_log_manager.request_logger.
    import glob
    import re as _re
    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        t = f.read_text()
        t_new = _re.sub(
            r"\btokenizer_manager\.request_logger\b",
            "tokenizer_manager.request_log_manager.request_logger",
            t,
        )
        if t_new != t:
            f.write_text(t_new)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
