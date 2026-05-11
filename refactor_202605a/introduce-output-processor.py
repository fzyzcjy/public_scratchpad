#!/usr/bin/env python3
"""Introduce OutputProcessor owner class.

Move _handle_batch_output (~247 LOC) from TokenizerManager into a new
@dataclass(slots=True, kw_only=True) OutputProcessor in
managers/output_processor.py. Body internal control flow stays;
only self.X references rewire to fields on OutputProcessor.

PR1 form per md ch3.1: single ``handle_batch_output`` method (privacy
flip allowed); sub-handler split + _BatchedNotifier extraction etc. are
Ch2.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
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

ID = "introduce-output-processor"
SUBJECT = "Introduce OutputProcessor and move _handle_batch_output"
BODY = """\
Move _handle_batch_output (247 LOC) from TokenizerManager into a new
managers/output_processor.py module as a method
``handle_batch_output`` of @dataclass(slots=True, kw_only=True)
OutputProcessor (privacy flip per design — was facade-private, now
new class public API).

Fields:
  rid_to_state, tokenizer (for logprob_ops bindings -- already module-level),
  request_metrics_recorder, request_log_manager, lora_controller,
  send_to_scheduler, enable_metrics, config (OutputProcessorConfig).

Internal body refs largely unchanged thanks to matching field names.
Caller in handle_loop updates: self._handle_batch_output(recv_obj)
-> await self.output_processor.handle_batch_output(recv_obj).

Per md ch3.1: 247 LOC bulk move only. Sub-handler split (handle_str /
handle_token_ids / handle_embedding) + _BatchedNotifier extraction etc.
are deferred to Ch2.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

import pybase64
import torch

from sglang.srt.constants import HEALTH_CHECK_RID_PREFIX
from sglang.srt.managers import logprob_ops, request_tracing, spec_decoding_meta
from sglang.srt.managers.lora_controller import LoraController
from sglang.srt.managers.io_struct import (
    BatchEmbeddingOutput,
    BatchStrOutput,
    BatchTokenIDOutput,
    WatchLoadUpdateReq,
)
from sglang.srt.managers.request_log_manager import RequestLogManager
from sglang.srt.managers.request_metrics_recorder import (
    RequestMetricsRecorder,
)
from sglang.srt.managers.request_state import ReqState

logger = logging.getLogger(__name__)


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

    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="_handle_batch_output"
    )
    body = cut_lines(tm, s, e)

    # Privacy flip + body rewrites (minimal -- field names mostly match).
    body = body.replace(
        "async def _handle_batch_output(",
        "async def handle_batch_output(",
    )
    # Server args -> config substitutions.
    body = body.replace("self.server_args.weight_version", "self.config.weight_version")
    body = body.replace(
        "self.server_args.incremental_streaming_output",
        "self.config.incremental_streaming_output",
    )
    body = body.replace(
        "self.server_args.skip_tokenizer_init",
        "self.config.skip_tokenizer_init",
    )
    body = body.replace(
        "self.server_args.speculative_algorithm",
        "self.config.speculative_algorithm",
    )
    body = body.replace(
        "self.server_args.speculative_num_draft_tokens",
        "self.config.speculative_num_draft_tokens",
    )
    body = body.replace("self.server_args.dp_size", "self.config.dp_size")
    body = body.replace("self.server_args.batch_notify_size", "self.config.batch_notify_size")
    body = body.replace("self.server_args.enable_lora", "self.config.enable_lora")
    body = body.replace("self.enable_metrics", "self.config.enable_metrics")
    # served_model_name lives on facade -- now config.
    body = body.replace(
        "served_model_name=self.served_model_name,",
        "served_model_name=self.config.served_model_name,",
    )
    # raw_tokenizer_wrapper.tokenizer -> self.tokenizer (OutputProcessor's field)
    body = body.replace(
        "self.raw_tokenizer_wrapper.tokenizer", "self.tokenizer"
    )
    # crash_dump_folder lives on request_log_manager
    body = body.replace(
        "self.crash_dump_folder", "self.request_log_manager.crash_dump_folder"
    )

    new.write_text(HEADER + body.rstrip() + "\n")

    # ===== Update facade =====
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

    # Caller update.
    text = text.replace(
        "                await self._handle_batch_output(recv_obj)\n",
        "                await self.output_processor.handle_batch_output(recv_obj)\n",
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
