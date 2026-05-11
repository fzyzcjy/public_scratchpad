#!/usr/bin/env python3
"""Prep: RequestLogManager skeleton + from_server_args factory + composition wiring."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-request-log-manager-prep"
SUBJECT = "Prep RequestLogManager: skeleton + factory + composition wiring"
BODY = "Per MECH_COMMIT_SPLIT: skeleton + composition only. Methods + callers in next commit."
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
    new = wt / "python/sglang/srt/managers/request_log_manager.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.request_log_manager import RequestLogManager\n",
    )
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
