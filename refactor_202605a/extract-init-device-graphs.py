#!/usr/bin/env python3
"""Cut `init_device_graphs` from ModelRunner; paste as a free function in
`model_executor/device_graphs.py` with explicit kwargs + tuple return.

Body has 2 writebacks (`graph_runner`, `graph_mem_usage`) + reads of
`is_generation`, `server_args`, `device`, `gpu_id`. The
`GraphRunnerCls(self)` / `graph_runners[device](self)` ctors still need a
ModelRunner reference — instead of taking `model_runner_ref` as an R4
concession kwarg, the caller closures over `self` in a `make_graph_runner`
factory callable. Bail returns become `return None, 0` (tuple form).

Usage:
    uv run --python 3.12 extract-init-device-graphs.py run
    uv run --python 3.12 extract-init-device-graphs.py verify
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
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-init-device-graphs"
SUBJECT = "Extract init_device_graphs to free function in model_executor.device_graphs"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-update-expert-location"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_DEVICE_GRAPHS_BODY = '''\
from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Callable

from sglang.srt.configs.model_config import ModelImpl
from sglang.srt.platforms import current_platform
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils import get_available_gpu_memory

logger = logging.getLogger(__name__)


def init_device_graphs(
    *,
    is_generation: bool,
    server_args: ServerArgs,
    device: str,
    gpu_id: int,
    make_graph_runner: Callable[[], Any],
) -> tuple[Any, float]:
    """Capture device graphs.

    Returns (graph_runner, graph_mem_usage). Both are None / 0 on the bail
    paths so the caller's tuple-unpack writeback still works.

    `make_graph_runner` is a 0-arg callable supplied by the caller — it owns
    the ``GraphRunnerCls(self)`` / ``graph_runners[device](self)`` selection
    + ctor (which still need a ModelRunner ref). Keeping it in the caller
    avoids an R4 concession kwarg here.
    """
    if not is_generation:
        # TODO: Currently, cuda graph only captures decode steps, which only exists for generation models
        return None, 0

    if server_args.model_impl.lower() == ModelImpl.MINDSPORE:
        return None, 0

    if device != "cpu" and server_args.disable_cuda_graph:
        return None, 0

    if device == "cpu" and not server_args.enable_torch_compile:
        return None, 0

    tic = time.perf_counter()
    before_mem = get_available_gpu_memory(device, gpu_id)
    graph_backend = defaultdict(
        lambda: f"{current_platform.device_name} graph",
        {
            "cuda": "cuda graph",
            "musa": "cuda graph",
            "cpu": "cpu graph",
            "npu": "npu graph",
        },
    )
    logger.info(
        f"Capture {graph_backend[device]} begin. This can take up to several minutes. avail mem={before_mem:.2f} GB"
    )
    graph_runner = make_graph_runner()

    after_mem = get_available_gpu_memory(device, gpu_id)
    graph_mem_usage = before_mem - after_mem
    logger.info(
        f"Capture {graph_backend[device]} end. Time elapsed: {time.perf_counter() - tic:.2f} s. "
        f"mem usage={graph_mem_usage:.2f} GB. avail mem={after_mem:.2f} GB."
    )
    return graph_runner, graph_mem_usage
'''


# Caller-side replacement for `self.init_device_graphs()`. The closure
# `_make_graph_runner` owns the platform/device → ctor mapping (was the
# inline `if/else` in the original body). It captures `self`, `CudaGraphRunner`,
# `CPUGraphRunner`, `NPUGraphRunner`, `current_platform`.
_CALLER_REPLACEMENT = '''\
        def _make_graph_runner():
            if current_platform.is_out_of_tree():
                GraphRunnerCls = current_platform.get_graph_runner_cls()
                return GraphRunnerCls(self)
            graph_runners = defaultdict(
                lambda: CudaGraphRunner,
                {
                    "cpu": CPUGraphRunner,
                    "npu": NPUGraphRunner,
                },
            )
            return graph_runners[self.device](self)

        self.graph_runner, self.graph_mem_usage = device_graphs.init_device_graphs(
            is_generation=self.is_generation,
            server_args=self.server_args,
            device=self.device,
            gpu_id=self.gpu_id,
            make_graph_runner=_make_graph_runner,
        )\
'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    dg = wt / "python/sglang/srt/model_executor/device_graphs.py"

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_device_graphs",
    )
    cut_lines(mr, s, e)

    dg.write_text(_DEVICE_GRAPHS_BODY)

    text = mr.read_text()
    if "from sglang.srt.model_executor import device_graphs\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
            addition="from sglang.srt.model_executor import device_graphs\n",
        )
    text = replace_call_site(
        text,
        old="        self.init_device_graphs()",
        new=_CALLER_REPLACEMENT,
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
