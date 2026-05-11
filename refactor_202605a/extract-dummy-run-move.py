#!/usr/bin/env python3
"""Move stage for extract-dummy-run (MECH_COMMIT_SPLIT §"二段式"):

Pure cut+paste of the prep'd ``dummy_run`` staticmethod to a new file
``model_executor/dummy_run.py``. Body byte-equivalent. The lambda callback
in ``initialize()`` collapses its ``ModelRunner.dummy_run(`` prefix to
``dummy_run(``; model_runner.py picks up the corresponding import.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import (
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-dummy-run-move"
SUBJECT = "Move dummy_run to model_executor.dummy_run (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-dummy-run-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_HEADER = '''from __future__ import annotations

import inspect
import logging

import torch

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.layers.dp_attention import (
    DpPaddingMode,
    get_attention_tp_size,
    set_dp_buffer_len,
    set_is_extend_in_batch,
)
from sglang.srt.model_executor.cuda_graph_runner import (
    DecodeInputBuffers,
    set_torch_compile_config,
)
from sglang.srt.model_executor.forward_batch_info import (
    CaptureHiddenMode,
    ForwardBatch,
    ForwardMode,
    PPProxyTensors,
)
from sglang.srt.server_args import ServerArgs
from sglang.srt.speculative.spec_info import SpeculativeAlgorithm
from sglang.srt.utils import (
    empty_context,
    log_info_on_rank0,
    require_attn_tp_gather,
    require_gathered_buffer,
    require_mlp_tp_gather,
)

logger = logging.getLogger(__name__)


'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    dr = wt / "python/sglang/srt/model_executor/dummy_run.py"

    start, end = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="dummy_run")
    method_text = cut_lines(mr, start, end)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    function_text = dedent_method_to_function("".join(lines[1:]))

    dr.write_text(_HEADER + function_text)

    text = mr.read_text()
    # Collapse the lambda's qualified call: ``ModelRunner.dummy_run(`` → ``dummy_run(``.
    text = replace_call_site(text, old="ModelRunner.dummy_run(", new="dummy_run(")
    # Import the free function (insert after the kernel_warmup import, which
    # at this point in the chain has only ``kernel_warmup``; the flashinfer
    # workspace helper is added later by ``extract-flashinfer-allreduce-workspace-move``).
    text = insert_after(
        text,
        anchor=(
            "from sglang.srt.model_executor.kernel_warmup import (\n"
            "    kernel_warmup,\n"
            ")\n"
        ),
        addition="from sglang.srt.model_executor.dummy_run import dummy_run\n",
    )
    mr.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
