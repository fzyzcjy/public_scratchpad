#!/usr/bin/env python3
"""Cut `init_device_graphs` from ModelRunner; paste as a free function in a
new file `model_executor/device_graphs.py`.

R4 concession: the body has 4 early `return` statements and writes to
`self.graph_runner` / `self.graph_mem_usage` interleaved with reads from
several other `self.X` fields, plus `GraphRunnerCls(self)` / `graph_runners[...](self)`
ctors that take ModelRunner. To keep the body byte-identical we only swap
``self`` -> ``model_runner_ref`` (R4 kwarg). All ``self.X = Y`` writes and bare
``return`` statements stay as-is.
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
)
from _runner import run_pr

BASE = "tom_refactor/31"
TARGET = "tom_refactor/32"


_DEVICE_GRAPHS_HEADER = '''\
from __future__ import annotations

import logging
import time
from collections import defaultdict

from sglang.srt.hardware_backend.npu.graph_runner.npu_graph_runner import NPUGraphRunner
from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner
from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner
from sglang.srt.platforms import current_platform
from sglang.srt.server_args import ModelImpl
from sglang.srt.utils import get_available_gpu_memory

logger = logging.getLogger(__name__)


'''


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    dg = wt / "python/sglang/srt/model_executor/device_graphs.py"

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_device_graphs",
    )
    func_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def init_device_graphs(self):\n",
            "def init_device_graphs(*, model_runner_ref):\n",
        )
        .replace("self.", "model_runner_ref.")
    )

    dg.write_text(_DEVICE_GRAPHS_HEADER + func_text)

    text = mr.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
        addition=(
            "from sglang.srt.model_executor.device_graphs import (\n"
            "    init_device_graphs as _free_init_device_graphs,\n"
            ")\n"
        ),
    )
    text = text.replace(
        "self.init_device_graphs()",
        "_free_init_device_graphs(model_runner_ref=self)",
    )
    mr.write_text(text)

    git_add_and_commit(
        "Extract init_device_graphs to free function in model_executor.device_graphs",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
