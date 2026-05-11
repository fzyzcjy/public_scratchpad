#!/usr/bin/env python3
"""Move _handle_batch_output (~247 LOC) to OutputProcessor."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines
from _runner import run_pr

ID = "introduce-output-processor-move"
SUBJECT = "Move _handle_batch_output to OutputProcessor (renamed handle_batch_output)"
BODY = """\
Cut _handle_batch_output from TM. Body rewrites self.server_args.X -> self.config.X
etc. Privacy flip: _handle_batch_output -> handle_batch_output. Caller in
handle_loop updated.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import asyncio
import logging
from typing import Union

import pybase64
import torch

from sglang.srt.constants import HEALTH_CHECK_RID_PREFIX
from sglang.srt.managers import logprob_ops, request_tracing, spec_decoding_meta
from sglang.srt.managers.io_struct import (
    BatchEmbeddingOutput,
    BatchStrOutput,
    BatchTokenIDOutput,
    WatchLoadUpdateReq,
)

logger = logging.getLogger(__name__)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    op = wt / "python/sglang/srt/managers/output_processor.py"

    s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name="_handle_batch_output")
    body = cut_lines(tm, s, e)

    body = body.replace("async def _handle_batch_output(", "async def handle_batch_output(")
    body = body.replace("self.server_args.weight_version", "self.config.weight_version")
    body = body.replace("self.server_args.incremental_streaming_output", "self.config.incremental_streaming_output")
    body = body.replace("self.server_args.skip_tokenizer_init", "self.config.skip_tokenizer_init")
    body = body.replace("self.server_args.speculative_algorithm", "self.config.speculative_algorithm")
    body = body.replace("self.server_args.speculative_num_draft_tokens", "self.config.speculative_num_draft_tokens")
    body = body.replace("self.server_args.dp_size", "self.config.dp_size")
    body = body.replace("self.server_args.batch_notify_size", "self.config.batch_notify_size")
    body = body.replace("self.server_args.enable_lora", "self.config.enable_lora")
    body = body.replace("self.enable_metrics", "self.config.enable_metrics")
    body = body.replace(
        "served_model_name=self.served_model_name,",
        "served_model_name=self.config.served_model_name,",
    )
    body = body.replace("self.raw_tokenizer_wrapper.tokenizer", "self.tokenizer")
    body = body.replace("self.crash_dump_folder", "self.request_log_manager.crash_dump_folder")

    op_text = op.read_text()
    op_text = op_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    op.write_text(op_text.rstrip() + "\n\n" + body.rstrip() + "\n")

    # Caller update.
    text = tm.read_text()
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
