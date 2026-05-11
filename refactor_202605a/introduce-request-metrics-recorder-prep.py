#!/usr/bin/env python3
"""Prep: empty RequestMetricsRecorder skeleton + composition wiring."""

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

ID = "introduce-request-metrics-recorder-prep"
SUBJECT = "Prep RequestMetricsRecorder: empty skeleton + composition wiring"
BODY = """\
Per MECH_COMMIT_SPLIT: skeleton + composition wiring only. Methods +
__post_init__ + caller rewrites land in the next commit.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sglang.srt.observability.metrics_collector import TokenizerMetricsCollector
from sglang.srt.server_args import ServerArgs


@dataclass(slots=True, kw_only=True)
class RequestMetricsRecorder:
    """Per-request Prometheus metrics emission."""

    server_args: ServerArgs
    enable_metrics: bool
    enable_priority_scheduling: bool
    metrics_collector: Optional[TokenizerMetricsCollector] = None
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/request_metrics_recorder.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition="from sglang.srt.managers.request_metrics_recorder import RequestMetricsRecorder\n",
    )
    text = replace_call_site(
        text,
        old=(
            "        # Request log manager\n"
            "        self.request_log_manager = RequestLogManager.from_server_args(\n"
        ),
        new=(
            "        # Request metrics recorder\n"
            "        self.request_metrics_recorder = RequestMetricsRecorder(\n"
            "            server_args=self.server_args,\n"
            "            enable_metrics=self.enable_metrics,\n"
            "            enable_priority_scheduling=self.enable_priority_scheduling,\n"
            "        )\n"
            "\n"
            "        # Request log manager\n"
            "        self.request_log_manager = RequestLogManager.from_server_args(\n"
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
