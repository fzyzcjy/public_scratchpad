#!/usr/bin/env python3
"""Prep: OutputProcessor skeleton + composition wiring."""

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

ID = "introduce-output-processor-prep"
SUBJECT = "Prep OutputProcessor: skeleton + composition wiring"
BODY = "Per MECH_COMMIT_SPLIT: skeleton + composition only."
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from sglang.srt.managers.lora_controller import LoraController
from sglang.srt.managers.request_log_manager import RequestLogManager
from sglang.srt.managers.request_metrics_recorder import RequestMetricsRecorder
from sglang.srt.managers.request_state import ReqState


@dataclass(slots=True, kw_only=True)
class OutputProcessorConfig:
    weight_version: Optional[str]
    batch_notify_size: int
    incremental_streaming_output: bool
    enable_metrics: bool
    skip_tokenizer_init: bool
    speculative_algorithm: str
    speculative_num_draft_tokens: int
    dp_size: int
    enable_lora: bool
    served_model_name: str


@dataclass(slots=True, kw_only=True)
class OutputProcessor:
    """Consumes BatchStrOutput / BatchTokenIDOutput / BatchEmbeddingOutput from scheduler."""

    rid_to_state: Dict[str, ReqState]
    tokenizer: Optional[Any]
    request_metrics_recorder: RequestMetricsRecorder
    request_log_manager: RequestLogManager
    lora_controller: LoraController
    send_to_scheduler: Any
    config: OutputProcessorConfig
    pending_notify: int = 0
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/output_processor.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.output_processor import (\n"
            "    OutputProcessor,\n"
            "    OutputProcessorConfig,\n"
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
            "        # Output processor\n"
            "        self.output_processor = OutputProcessor(\n"
            "            rid_to_state=self.rid_to_state,\n"
            "            tokenizer=self.raw_tokenizer_wrapper.tokenizer,\n"
            "            request_metrics_recorder=self.request_metrics_recorder,\n"
            "            request_log_manager=self.request_log_manager,\n"
            "            lora_controller=self.lora_controller,\n"
            "            send_to_scheduler=self.send_to_scheduler,\n"
            "            config=OutputProcessorConfig(\n"
            "                weight_version=self.server_args.weight_version,\n"
            "                batch_notify_size=self.server_args.batch_notify_size,\n"
            "                incremental_streaming_output=self.server_args.incremental_streaming_output,\n"
            "                enable_metrics=self.enable_metrics,\n"
            "                skip_tokenizer_init=self.server_args.skip_tokenizer_init,\n"
            "                speculative_algorithm=self.server_args.speculative_algorithm or '',\n"
            "                speculative_num_draft_tokens=self.server_args.speculative_num_draft_tokens,\n"
            "                dp_size=self.server_args.dp_size,\n"
            "                enable_lora=self.server_args.enable_lora,\n"
            "                served_model_name=self.server_args.served_model_name,\n"
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
