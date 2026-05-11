#!/usr/bin/env python3
"""Move stage for extract-init-device-graphs (MECH_COMMIT_SPLIT §"二段式"):

Pure cut+paste to new file ``model_executor/device_graphs.py``. Body
byte-equivalent. Call sites prefix-rewrite.
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

ID = "extract-init-device-graphs-move"
SUBJECT = "Move create_device_graphs to model_executor.device_graphs (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-init-device-graphs-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_HEADER = '''from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from sglang.srt.configs.model_config import ModelImpl
from sglang.srt.hardware_backend.npu.graph_runner.npu_graph_runner import (
    NPUGraphRunner,
)
from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner
from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner
from sglang.srt.platforms import current_platform
from sglang.srt.utils import get_available_gpu_memory

if TYPE_CHECKING:
    from sglang.srt.model_executor.model_runner import ModelRunner

logger = logging.getLogger(__name__)


'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    dg = wt / "python/sglang/srt/model_executor/device_graphs.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"

    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="create_device_graphs"
    )
    method_text = cut_lines(mr, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    function_text = dedent_method_to_function("".join(lines[1:]))

    dg.write_text(_HEADER + function_text)

    # ModelRunner: prefix-strip call sites + add import. The free function
    # mutates ``model_runner.graph_runner`` / ``.graph_mem_usage`` in place
    # (same semantics as the original method), so call sites stay assignment-free.
    text = mr.read_text()
    text = replace_call_site(
        text,
        old="ModelRunner.create_device_graphs(",
        new="device_graphs.create_device_graphs(",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
        addition="from sglang.srt.model_executor import device_graphs\n",
    )
    mr.write_text(text)

    # WeightUpdater: drop temp ModelRunner import, switch to free fn.
    wu_text = wu.read_text()
    wu_text = replace_call_site(
        wu_text,
        old="from sglang.srt.model_executor.model_runner import ModelRunner\n",
        new="",
    )
    wu_text = replace_call_site(
        wu_text,
        old="ModelRunner.create_device_graphs(",
        new="device_graphs.create_device_graphs(",
    )
    wu_text = insert_after(
        wu_text,
        anchor="from sglang.srt.platforms import current_platform\n",
        addition="from sglang.srt.model_executor import device_graphs\n",
    )
    wu.write_text(wu_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
