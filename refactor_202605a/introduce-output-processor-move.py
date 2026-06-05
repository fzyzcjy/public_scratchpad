#!/usr/bin/env python3
"""Move (pure cut/paste): _handle_batch_output relocates from TM to OutputProcessor."""

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
SUBJECT = "Hand batch-output handling over to OutputProcessor"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut @staticmethod
_handle_batch_output from TokenizerManager; paste into OutputProcessor
(drop @staticmethod, replace ``self: "OutputProcessor"`` -> plain
``self``). Privacy flip rename: _handle_batch_output -> handle_batch_output
(method is now public API of new class). Caller prefix replacement:
``TokenizerManager._handle_batch_output(self.output_processor, ...)`` ->
``self.output_processor.handle_batch_output(...)``.
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
from sglang.srt.managers.tokenizer_manager_components import (
    logprob_ops,
    request_tracing,
    spec_decoding_meta,
)
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
    op = wt / "python/sglang/srt/managers/tokenizer_manager_components/output_processor.py"

    s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name="_handle_batch_output")
    handle_text = cut_lines(tm, s, e)

    # Strip @staticmethod + restore plain self. Privacy flip rename: _handle_batch_output -> handle_batch_output.
    handle_text = handle_text.replace("    @staticmethod\n", "", 1)
    handle_text = handle_text.replace('self: "OutputProcessor",', "self,")
    handle_text = handle_text.replace("async def _handle_batch_output(", "async def handle_batch_output(", 1)

    op_text = op.read_text()
    op_text = op_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    op.write_text(op_text.rstrip() + "\n" + handle_text.rstrip() + "\n")

    # Caller prefix replacement:
    #   TokenizerManager._handle_batch_output(self.output_processor, recv_obj)
    # -> self.output_processor.handle_batch_output(recv_obj)
    text = tm.read_text()
    text = text.replace(
        "                await TokenizerManager._handle_batch_output(\n"
        "                    self.output_processor, recv_obj\n"
        "                )\n",
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
