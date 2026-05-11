#!/usr/bin/env python3
"""Prep: ResponseEmitter skeleton + composition wiring."""

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

ID = "introduce-response-emitter-prep"
SUBJECT = "Prep ResponseEmitter: skeleton + composition wiring"
BODY = "Per MECH_COMMIT_SPLIT: skeleton + composition only."
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from sglang.srt.managers.lora_controller import LoraController
from sglang.srt.managers.pause_controller import PauseController
from sglang.srt.managers.request_log_manager import RequestLogManager
from sglang.srt.managers.request_metrics_recorder import RequestMetricsRecorder
from sglang.srt.managers.request_state import ReqState


@dataclass(slots=True, kw_only=True)
class ResponseEmitterConfig:
    incremental_streaming_output: bool
    enable_lora: bool


@dataclass(slots=True, kw_only=True)
class ResponseEmitter:
    """Drains rid_to_state[rid].out_list and yields per-request dicts to HTTP clients."""

    rid_to_state: Dict[str, ReqState]
    pause_controller: PauseController
    lora_controller: LoraController
    request_log_manager: RequestLogManager
    request_metrics_recorder: RequestMetricsRecorder
    config: ResponseEmitterConfig
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/response_emitter.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.response_emitter import (\n"
            "    ResponseEmitter,\n"
            "    ResponseEmitterConfig,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
        new=(
            "        # Response emitter\n"
            "        self.response_emitter = ResponseEmitter(\n"
            "            rid_to_state=self.rid_to_state,\n"
            "            pause_controller=self.pause_controller,\n"
            "            lora_controller=self.lora_controller,\n"
            "            request_log_manager=self.request_log_manager,\n"
            "            request_metrics_recorder=self.request_metrics_recorder,\n"
            "            config=ResponseEmitterConfig(\n"
            "                incremental_streaming_output=self.server_args.incremental_streaming_output,\n"
            "                enable_lora=self.server_args.enable_lora,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
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
