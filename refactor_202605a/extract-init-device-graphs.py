#!/usr/bin/env python3
"""Cut `init_device_graphs` from ModelRunner; paste as a free function in
`model_executor/device_graphs.py` taking `model_runner: ModelRunner`.

Body is a mechanical copy of the original method with `self` →
`model_runner`. Returns `(graph_runner, graph_mem_usage)`. The 4 early
bails return `None, 0` (tuple form) so the caller's tuple-unpack
writeback still works. The 4 call sites (3 in `ModelRunner.initialize` +
1 in `WeightUpdater.update_weights_from_disk`) all become 1-line
replacements; `self.init_device_graphs()` →
`self.graph_runner, self.graph_mem_usage = device_graphs.init_device_graphs(self)`,
and similarly for the `self._mr.init_device_graphs()` case.

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


def init_device_graphs(model_runner: "ModelRunner") -> tuple[Any, float]:
    """Capture device graphs.

    Returns ``(graph_runner, graph_mem_usage)``. Both are ``None`` / ``0``
    on the bail paths so the caller's tuple-unpack writeback still works.
    """
    if not model_runner.is_generation:
        # TODO: Currently, cuda graph only captures decode steps, which only exists for generation models
        return None, 0

    if model_runner.server_args.model_impl.lower() == ModelImpl.MINDSPORE:
        return None, 0

    if model_runner.device != "cpu" and model_runner.server_args.disable_cuda_graph:
        return None, 0

    if model_runner.device == "cpu" and not model_runner.server_args.enable_torch_compile:
        return None, 0

    tic = time.perf_counter()
    before_mem = get_available_gpu_memory(model_runner.device, model_runner.gpu_id)
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
        f"Capture {graph_backend[model_runner.device]} begin. This can take up to several minutes. avail mem={before_mem:.2f} GB"
    )
    if current_platform.is_out_of_tree():
        GraphRunnerCls = current_platform.get_graph_runner_cls()
        graph_runner = GraphRunnerCls(model_runner)
    else:
        graph_runners = defaultdict(
            lambda: CudaGraphRunner,
            {
                "cpu": CPUGraphRunner,
                "npu": NPUGraphRunner,
            },
        )
        graph_runner = graph_runners[model_runner.device](model_runner)

    after_mem = get_available_gpu_memory(model_runner.device, model_runner.gpu_id)
    graph_mem_usage = before_mem - after_mem
    logger.info(
        f"Capture {graph_backend[model_runner.device]} end. Time elapsed: {time.perf_counter() - tic:.2f} s. "
        f"mem usage={graph_mem_usage:.2f} GB. avail mem={after_mem:.2f} GB."
    )
    return graph_runner, graph_mem_usage
'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    dg = wt / "python/sglang/srt/model_executor/device_graphs.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"

    # 1) Cut method def from ModelRunner.
    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_device_graphs",
    )
    cut_lines(mr, s, e)

    # 2) Write the new device_graphs module.
    dg.write_text(_DEVICE_GRAPHS_BODY)

    # 3) Wire up model_runner.py: import + 3 call-site rewrites (all 3 share
    # the same ``self.init_device_graphs()`` substring; one .replace replaces
    # all three at the original indents).
    text = mr.read_text()
    if "from sglang.srt.model_executor import device_graphs\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
            addition="from sglang.srt.model_executor import device_graphs\n",
        )
    text = replace_call_site(
        text,
        old="self.init_device_graphs()",
        new="self.graph_runner, self.graph_mem_usage = device_graphs.init_device_graphs(self)",
    )
    mr.write_text(text)

    # 4) Wire up weight_updater.py recapture-path call site.
    wu_text = wu.read_text()
    if "from sglang.srt.model_executor import device_graphs\n" not in wu_text:
        wu_text = insert_after(
            wu_text,
            anchor="from sglang.srt.platforms import current_platform\n",
            addition="from sglang.srt.model_executor import device_graphs\n",
        )
    wu_text = replace_call_site(
        wu_text,
        old="self._mr.init_device_graphs()",
        new=(
            "self._mr.graph_runner, self._mr.graph_mem_usage = "
            "device_graphs.init_device_graphs(self._mr)"
        ),
    )
    wu.write_text(wu_text)

    # Absorbed from dg-mech-rename: factory functions read truer as ``create_*``.
    for path in [dg, mr, wu]:
        text = path.read_text()
        text = text.replace("init_device_graphs", "create_device_graphs")
        path.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
