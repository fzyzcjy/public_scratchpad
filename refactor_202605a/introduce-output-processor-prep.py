#!/usr/bin/env python3
"""Inplace prep for ``introduce-output-processor``: build the
``OutputProcessor`` + ``OutputProcessorConfig`` skeletons in
``managers/output_processor.py``, instantiate ``self.output_processor`` in
``TokenizerManager.__init__``, convert ``_handle_batch_output`` to
``@staticmethod`` with ``self: OutputProcessor`` type annotation, rewrite the
caller in ``handle_loop`` to the class-qualified form
``TokenizerManager._handle_batch_output(self.output_processor, recv_obj)``.

Body of ``_handle_batch_output`` stays inside TokenizerManager; physical cut
into ``OutputProcessor`` body happens in ``introduce-output-processor-move``.

Per MECH_COMMIT_SPLIT §"拆 class 场景": ``self`` parameter name is preserved,
only its type flips, so body references like ``self.config.X`` /
``self.tokenizer`` / ``self.request_log_manager.crash_dump_folder`` already
resolve against ``OutputProcessor`` fields (static check + runtime both OK).
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

ID = "introduce-output-processor-prep"
SUBJECT = "Build OutputProcessor skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-output-processor`` mech move.

- Create ``managers/output_processor.py`` with
  ``OutputProcessorConfig`` (dataclass) and ``OutputProcessor`` (dataclass)
  skeletons. No methods yet.
- Instantiate ``self.output_processor = OutputProcessor(...)`` in
  ``TokenizerManager.__init__`` just before the existing
  ``# Session controller`` block, with ``OutputProcessorConfig`` populated
  from ``self.server_args`` / ``self.enable_metrics``.
- In TokenizerManager, convert ``_handle_batch_output`` to ``@staticmethod``
  with ``self: OutputProcessor`` type annotation. Body bytes are rewritten
  to address ``OutputProcessor`` fields:
  - ``self.server_args.<X>``  -> ``self.config.<X>``
  - ``self.enable_metrics``   -> ``self.config.enable_metrics``
  - ``self.raw_tokenizer_wrapper.tokenizer`` -> ``self.tokenizer``
  - ``self.crash_dump_folder`` -> ``self.request_log_manager.crash_dump_folder``
- Caller in ``handle_loop`` rewritten to
  ``TokenizerManager._handle_batch_output(self.output_processor, recv_obj)``
  (class-qualified call, byte-symmetric with the move-commit prefix swap).

The method stays inside TokenizerManager in this commit; physical cut +
paste into ``OutputProcessor`` body happens in
``introduce-output-processor-move``.
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


INIT_INSERT = '''        # Output processor
        self.output_processor = OutputProcessor(
            rid_to_state=self.rid_to_state,
            tokenizer=self.raw_tokenizer_wrapper.tokenizer,
            request_metrics_recorder=self.request_metrics_recorder,
            request_log_manager=self.request_log_manager,
            lora_controller=self.lora_controller,
            send_to_scheduler=self.send_to_scheduler,
            config=OutputProcessorConfig(
                weight_version=self.server_args.weight_version,
                batch_notify_size=self.server_args.batch_notify_size,
                incremental_streaming_output=self.server_args.incremental_streaming_output,
                enable_metrics=self.enable_metrics,
                skip_tokenizer_init=self.server_args.skip_tokenizer_init,
                speculative_algorithm=self.server_args.speculative_algorithm or '',
                speculative_num_draft_tokens=self.server_args.speculative_num_draft_tokens,
                dp_size=self.server_args.dp_size,
                enable_lora=self.server_args.enable_lora,
                served_model_name=self.server_args.served_model_name,
            ),
        )

'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/output_processor.py"

    # 1. Create new file with class skeletons (no methods yet).
    new.parent.mkdir(parents=True, exist_ok=True)
    new.write_text(HEADER)

    # 2. In TokenizerManager, retype _handle_batch_output to @staticmethod with
    # ``self: OutputProcessor``. Body stays in TM; field-rewrites happen here so
    # body is already addressing OutputProcessor's fields (per
    # MECH_COMMIT_SPLIT §"拆 class 场景": type-flip the param, not the name).
    text = tm.read_text()
    s, e = find_method_lines(
        text, class_name="TokenizerManager", method_name="_handle_batch_output"
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])

    # Add @staticmethod decorator + ``self: "OutputProcessor"`` type annotation.
    if '    async def _handle_batch_output(\n        self,\n' not in method_text:
        raise RuntimeError("_handle_batch_output signature shape unexpected")
    method_text = method_text.replace(
        '    async def _handle_batch_output(\n        self,\n',
        '    @staticmethod\n'
        '    async def _handle_batch_output(\n'
        '        self: "OutputProcessor",\n',
        1,
    )

    # Server-args / facade-field rewrites so the body addresses OutputProcessor
    # fields (matches HEADER + INIT_INSERT shape).
    method_text = method_text.replace(
        "self.server_args.weight_version", "self.config.weight_version"
    )
    method_text = method_text.replace(
        "self.server_args.incremental_streaming_output",
        "self.config.incremental_streaming_output",
    )
    method_text = method_text.replace(
        "self.server_args.skip_tokenizer_init",
        "self.config.skip_tokenizer_init",
    )
    method_text = method_text.replace(
        "self.server_args.speculative_algorithm",
        "self.config.speculative_algorithm",
    )
    method_text = method_text.replace(
        "self.server_args.speculative_num_draft_tokens",
        "self.config.speculative_num_draft_tokens",
    )
    method_text = method_text.replace("self.server_args.dp_size", "self.config.dp_size")
    method_text = method_text.replace(
        "self.server_args.batch_notify_size", "self.config.batch_notify_size"
    )
    method_text = method_text.replace(
        "self.server_args.enable_lora", "self.config.enable_lora"
    )
    method_text = method_text.replace("self.enable_metrics", "self.config.enable_metrics")
    method_text = method_text.replace(
        "served_model_name=self.served_model_name,",
        "served_model_name=self.config.served_model_name,",
    )
    method_text = method_text.replace(
        "self.raw_tokenizer_wrapper.tokenizer", "self.tokenizer"
    )
    method_text = method_text.replace(
        "self.crash_dump_folder", "self.request_log_manager.crash_dump_folder"
    )

    text = "".join(lines[:s]) + method_text + "".join(lines[e:])

    # 3. Add import for OutputProcessor / OutputProcessorConfig.
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

    # 4. Instantiate self.output_processor in __init__, just before the
    # Session controller block (same anchor as the original combined script).
    text = replace_call_site(
        text,
        old=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
        new=(
            INIT_INSERT
            + "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
    )

    # 5. Caller in handle_loop: class-qualified call form.
    text = replace_call_site(
        text,
        old="                await self._handle_batch_output(recv_obj)\n",
        new="                await TokenizerManager._handle_batch_output(self.output_processor, recv_obj)\n",
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
