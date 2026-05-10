#!/usr/bin/env python3
"""Cut `init_device_graphs` from ModelRunner; paste as a free function in
`model_executor/device_graphs.py` with explicit kwargs + tuple return.

Body has 2 writebacks (`graph_runner`, `graph_mem_usage`) + reads of
`is_generation`, `server_args`, `device`, `gpu_id`. The
`GraphRunnerCls(self)` / `graph_runners[device](self)` ctors still need a
ModelRunner reference — instead of taking `model_runner_ref` as an R4
concession kwarg, the caller closures over `self` in a `make_graph_runner`
factory callable. Bail returns become `return None, 0` (tuple form).

There are 4 call sites total: 3 in `ModelRunner.initialize` (cuda/musa,
npu/cpu, out-of-tree branches at indents 12, 12, 16), plus 1 in
`WeightUpdater.update_weights_from_disk` (recapture path, calling via
``self._mr``). Each gets its own closure + unpacked call at the matching
indent.

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


# Closure inserted right above the if/elif chain in `ModelRunner.initialize`.
# Selects the GraphRunner class based on platform/device — captures `self`
# so the device_graphs free function can stay MR-ref-free. Defined once;
# all 3 call sites in the if/elif chain reuse it.
_INITIALIZE_CLOSURE_INSERT = '''\

        def _make_graph_runner():
            if current_platform.is_out_of_tree():
                return current_platform.get_graph_runner_cls()(self)
            graph_runners = defaultdict(
                lambda: CudaGraphRunner,
                {
                    "cpu": CPUGraphRunner,
                    "npu": NPUGraphRunner,
                },
            )
            return graph_runners[self.device](self)
'''


def _unpacked_call(indent: str) -> str:
    """Return the `self.graph_runner, self.graph_mem_usage = device_graphs.init_device_graphs(...)`
    block at the given leading indent (e.g. `"            "` for 12 spaces).
    """
    return (
        f"{indent}self.graph_runner, self.graph_mem_usage = device_graphs.init_device_graphs(\n"
        f"{indent}    is_generation=self.is_generation,\n"
        f"{indent}    server_args=self.server_args,\n"
        f"{indent}    device=self.device,\n"
        f"{indent}    gpu_id=self.gpu_id,\n"
        f"{indent}    make_graph_runner=_make_graph_runner,\n"
        f"{indent})"
    )


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    dg = wt / "python/sglang/srt/model_executor/device_graphs.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"

    # 1) Cut method def (we re-emit body inline via the free function).
    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_device_graphs",
    )
    cut_lines(mr, s, e)

    # 2) Write the new device_graphs module.
    dg.write_text(_DEVICE_GRAPHS_BODY)

    # 3) Wire up model_runner.py.
    text = mr.read_text()
    if "from sglang.srt.model_executor import device_graphs\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
            addition="from sglang.srt.model_executor import device_graphs\n",
        )

    # Insert the `_make_graph_runner` closure right after `init_aux_hidden_state_capture()`,
    # i.e. just above the `if self.device == "cuda" or self.device == "musa":` chain.
    text = replace_call_site(
        text,
        old=(
            "        self.init_aux_hidden_state_capture()\n"
            "\n"
            '        if self.device == "cuda" or self.device == "musa":\n'
        ),
        new=(
            "        self.init_aux_hidden_state_capture()\n"
            f"{_INITIALIZE_CLOSURE_INSERT}"
            "\n"
            '        if self.device == "cuda" or self.device == "musa":\n'
        ),
    )

    # Site 1 — cuda/musa branch (12-space indent). Anchored on the unique
    # ``_pre_initialize_flashinfer_allreduce_workspace`` line that immediately
    # precedes it.
    text = replace_call_site(
        text,
        old=(
            "            self._pre_initialize_flashinfer_allreduce_workspace()\n"
            "            self.init_device_graphs()\n"
        ),
        new=(
            "            self._pre_initialize_flashinfer_allreduce_workspace()\n"
            f"{_unpacked_call('            ')}\n"
        ),
    )

    # Site 2 — npu/cpu branch (12-space indent). Anchored on the unique
    # ``elif self.device in ["npu", "cpu"]`` line that opens this branch.
    text = replace_call_site(
        text,
        old=(
            '        elif self.device in ["npu", "cpu"]:\n'
            "            self.init_attention_backend()\n"
            "            self.init_device_graphs()\n"
        ),
        new=(
            '        elif self.device in ["npu", "cpu"]:\n'
            "            self.init_attention_backend()\n"
            f"{_unpacked_call('            ')}\n"
        ),
    )

    # Site 3 — out-of-tree branch (16-space indent). Anchored on the unique
    # ``if current_platform.support_cuda_graph()`` line just above.
    text = replace_call_site(
        text,
        old=(
            "            if current_platform.support_cuda_graph():\n"
            "                self.init_device_graphs()\n"
        ),
        new=(
            "            if current_platform.support_cuda_graph():\n"
            f"{_unpacked_call('                ')}\n"
        ),
    )

    mr.write_text(text)

    # 4) Wire up weight_updater.py recapture-path call site. WeightUpdater
    # accesses ModelRunner via ``self._mr``, so the closure captures
    # ``self._mr`` instead of ``self`` and the unpacked call writes through
    # ``self._mr.graph_runner`` / ``self._mr.graph_mem_usage``.
    wu_text = wu.read_text()

    # Add device_graphs import (keep grouped with the existing model_executor
    # subpackage imports). Use the import that's already present + a known
    # neighbor as the anchor.
    if "from sglang.srt.model_executor import device_graphs\n" not in wu_text:
        wu_text = insert_after(
            wu_text,
            anchor="from sglang.srt.platforms import current_platform\n",
            addition="from sglang.srt.model_executor import device_graphs\n",
        )

    # Single recapture call site: insert closure right above the
    # ``if recapture_cuda_graph and (...):`` block, then unpack the call.
    wu_text = replace_call_site(
        wu_text,
        old=(
            "        if recapture_cuda_graph and (\n"
            '            self._mr.device == "cuda"\n'
            '            or self._mr.device == "musa"\n'
            "            or (\n"
            "                current_platform.is_out_of_tree()\n"
            "                and current_platform.support_cuda_graph()\n"
            "            )\n"
            "        ):\n"
            "            self._mr.init_device_graphs()\n"
        ),
        new=(
            "        def _make_graph_runner():\n"
            "            if current_platform.is_out_of_tree():\n"
            "                return current_platform.get_graph_runner_cls()(self._mr)\n"
            "            graph_runners = defaultdict(\n"
            "                lambda: CudaGraphRunner,\n"
            "                {\n"
            '                    "cpu": CPUGraphRunner,\n'
            '                    "npu": NPUGraphRunner,\n'
            "                },\n"
            "            )\n"
            "            return graph_runners[self._mr.device](self._mr)\n"
            "\n"
            "        if recapture_cuda_graph and (\n"
            '            self._mr.device == "cuda"\n'
            '            or self._mr.device == "musa"\n'
            "            or (\n"
            "                current_platform.is_out_of_tree()\n"
            "                and current_platform.support_cuda_graph()\n"
            "            )\n"
            "        ):\n"
            "            (\n"
            "                self._mr.graph_runner,\n"
            "                self._mr.graph_mem_usage,\n"
            "            ) = device_graphs.init_device_graphs(\n"
            "                is_generation=self._mr.is_generation,\n"
            "                server_args=self._mr.server_args,\n"
            "                device=self._mr.device,\n"
            "                gpu_id=self._mr.gpu_id,\n"
            "                make_graph_runner=_make_graph_runner,\n"
            "            )\n"
        ),
    )

    # Make sure CudaGraphRunner / CPUGraphRunner / NPUGraphRunner / defaultdict
    # are importable in weight_updater.py for the closure body.
    for symbol_import in (
        "from collections import defaultdict\n",
        "from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner\n",
        "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
        "from sglang.srt.model_executor.npu_graph_runner import NPUGraphRunner\n",
    ):
        if symbol_import not in wu_text:
            wu_text = insert_after(
                wu_text,
                anchor="from sglang.srt.platforms import current_platform\n",
                addition=symbol_import,
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
