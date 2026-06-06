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

    # Adapt the unit test that drove ``tm._handle_batch_output`` directly: the
    # logic now lives on OutputProcessor.handle_batch_output, so build an
    # OutputProcessor in the test's mock factory (sharing rid_to_state, all the
    # metrics/lora/dump paths gated off so only the rid lifecycle runs) and route
    # the calls through it.
    test_file = wt / "test/registered/unit/managers/test_tokenizer_manager_rid_cleanup.py"
    if test_file.exists():
        t = test_file.read_text()
        t = t.replace(
            "from sglang.srt.managers.tokenizer_manager import ReqState, TokenizerManager\n",
            "from sglang.srt.managers.tokenizer_manager import ReqState, TokenizerManager\n"
            "from sglang.srt.managers.tokenizer_manager_components.output_processor import (\n"
            "    OutputProcessor,\n"
            "    OutputProcessorConfig,\n"
            ")\n",
        )
        t = t.replace(
            "    tm.send_to_scheduler = MagicMock()\n    return tm\n",
            "    tm.send_to_scheduler = MagicMock()\n"
            "    request_log_manager = MagicMock()\n"
            "    request_log_manager.dump_requests_folder = \"\"\n"
            "    request_log_manager.crash_dump_folder = \"\"\n"
            "    tm.output_processor = OutputProcessor(\n"
            "        rid_to_state=tm.rid_to_state,\n"
            "        tokenizer=MagicMock(),\n"
            "        request_metrics_recorder=MagicMock(),\n"
            "        request_log_manager=request_log_manager,\n"
            "        lora_controller=MagicMock(),\n"
            "        send_to_scheduler=tm.send_to_scheduler,\n"
            "        get_weight_version=lambda: \"1\",\n"
            "        get_served_model_name=lambda: \"\",\n"
            "        config=OutputProcessorConfig(\n"
            "            batch_notify_size=1,\n"
            "            incremental_streaming_output=False,\n"
            "            enable_metrics=False,\n"
            "            skip_tokenizer_init=False,\n"
            "            speculative_algorithm=\"\",\n"
            "            speculative_num_draft_tokens=0,\n"
            "            dp_size=1,\n"
            "            enable_lora=False,\n"
            "        ),\n"
            "    )\n"
            "    return tm\n",
        )
        t = t.replace("tm._handle_batch_output(", "tm.output_processor.handle_batch_output(")
        test_file.write_text(t)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
