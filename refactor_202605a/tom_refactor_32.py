#!/usr/bin/env python3
"""Reproducible transform: extract `ModelRunner.init_device_graphs` to a free
function `init_device_graphs` in `sglang.srt.model_executor.device_graphs`.

Strict-minimal mechanical extraction:
  - Free function body is byte-identical to the original method body, with
    `self.X` reads replaced by explicit kwargs.
  - The two `self.X = ...` writes (`graph_runner`, `graph_mem_usage`) become
    local variables; the function returns the tuple
    `(graph_runner, graph_mem_usage)`.
  - GraphRunner ctors take `ModelRunner` as their sole arg, so we forward
    `self` as `model_runner_ref` (R4 concession).
  - The original method on `ModelRunner` becomes a 1-line delegate.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/31"
TARGET_COMMIT = "tom_refactor/32"


def transform(dir_root: Path) -> None:
    dg = dir_root / "python/sglang/srt/model_executor/device_graphs.py"
    dg_content = (
        "from __future__ import annotations\n"
        "\n"
        "import logging\n"
        "import time\n"
        "from collections import defaultdict\n"
        "from typing import TYPE_CHECKING, Optional, Tuple\n"
        "\n"
        "from sglang.srt.hardware_backend.npu.graph_runner.npu_graph_runner import NPUGraphRunner\n"
        "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n"
        "from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner\n"
        "from sglang.srt.platforms import current_platform\n"
        "from sglang.srt.server_args import ModelImpl, ServerArgs\n"
        "from sglang.srt.utils import get_available_gpu_memory\n"
        "\n"
        "if TYPE_CHECKING:\n"
        "    from sglang.srt.model_executor.model_runner import ModelRunner\n"
        "\n"
        "logger = logging.getLogger(__name__)\n"
        "\n"
        "\n"
        "def init_device_graphs(\n"
        "    *,\n"
        '    model_runner_ref: "ModelRunner",  # R4 concession: GraphRunner ctors require ModelRunner\n'
        "    is_generation: bool,\n"
        "    server_args: ServerArgs,\n"
        "    device: str,\n"
        "    gpu_id: int,\n"
        ") -> Tuple[Optional[object], float]:\n"
        '    """Capture device graphs."""\n'
        "    graph_runner = None\n"
        "    graph_mem_usage = 0\n"
        "\n"
        "    if not is_generation:\n"
        "        # TODO: Currently, cuda graph only captures decode steps, which only exists for generation models\n"
        "        return graph_runner, graph_mem_usage\n"
        "\n"
        "    if server_args.model_impl.lower() == ModelImpl.MINDSPORE:\n"
        "        return graph_runner, graph_mem_usage\n"
        "\n"
        '    if device != "cpu" and server_args.disable_cuda_graph:\n'
        "        return graph_runner, graph_mem_usage\n"
        "\n"
        '    if device == "cpu" and not server_args.enable_torch_compile:\n'
        "        return graph_runner, graph_mem_usage\n"
        "\n"
        "    tic = time.perf_counter()\n"
        "    before_mem = get_available_gpu_memory(device, gpu_id)\n"
        "    graph_backend = defaultdict(\n"
        '        lambda: f"{current_platform.device_name} graph",\n'
        "        {\n"
        '            "cuda": "cuda graph",\n'
        '            "musa": "cuda graph",\n'
        '            "cpu": "cpu graph",\n'
        '            "npu": "npu graph",\n'
        "        },\n"
        "    )\n"
        "    logger.info(\n"
        '        f"Capture {graph_backend[device]} begin. This can take up to several minutes. avail mem={before_mem:.2f} GB"\n'
        "    )\n"
        "    if current_platform.is_out_of_tree():\n"
        "        GraphRunnerCls = current_platform.get_graph_runner_cls()\n"
        "        graph_runner = GraphRunnerCls(model_runner_ref)\n"
        "    else:\n"
        "        graph_runners = defaultdict(\n"
        "            lambda: CudaGraphRunner,\n"
        "            {\n"
        '                "cpu": CPUGraphRunner,\n'
        '                "npu": NPUGraphRunner,\n'
        "            },\n"
        "        )\n"
        "        graph_runner = graph_runners[device](model_runner_ref)\n"
        "\n"
        "    after_mem = get_available_gpu_memory(device, gpu_id)\n"
        "    graph_mem_usage = before_mem - after_mem\n"
        "    logger.info(\n"
        '        f"Capture {graph_backend[device]} end. Time elapsed: {time.perf_counter() - tic:.2f} s. "\n'
        '        f"mem usage={graph_mem_usage:.2f} GB. avail mem={after_mem:.2f} GB."\n'
        "    )\n"
        "    return graph_runner, graph_mem_usage\n"
    )
    dg.write_text(dg_content)

    # ---- Update model_runner.py ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    old_method = (
        '    def init_device_graphs(self):\n'
        '        """Capture device graphs."""\n'
        "        self.graph_runner = None\n"
        "        self.graph_mem_usage = 0\n"
        "\n"
        "        if not self.is_generation:\n"
        "            # TODO: Currently, cuda graph only captures decode steps, which only exists for generation models\n"
        "            return\n"
        "\n"
        "        if self.server_args.model_impl.lower() == ModelImpl.MINDSPORE:\n"
        "            return\n"
        "\n"
        '        if self.device != "cpu" and self.server_args.disable_cuda_graph:\n'
        "            return\n"
        "\n"
        '        if self.device == "cpu" and not self.server_args.enable_torch_compile:\n'
        "            return\n"
        "\n"
        "        tic = time.perf_counter()\n"
        "        before_mem = get_available_gpu_memory(self.device, self.gpu_id)\n"
        "        graph_backend = defaultdict(\n"
        '            lambda: f"{current_platform.device_name} graph",\n'
        "            {\n"
        '                "cuda": "cuda graph",\n'
        '                "musa": "cuda graph",\n'
        '                "cpu": "cpu graph",\n'
        '                "npu": "npu graph",\n'
        "            },\n"
        "        )\n"
        "        logger.info(\n"
        '            f"Capture {graph_backend[self.device]} begin. This can take up to several minutes. avail mem={before_mem:.2f} GB"\n'
        "        )\n"
        "        if current_platform.is_out_of_tree():\n"
        "            GraphRunnerCls = current_platform.get_graph_runner_cls()\n"
        "            self.graph_runner = GraphRunnerCls(self)\n"
        "        else:\n"
        "            graph_runners = defaultdict(\n"
        "                lambda: CudaGraphRunner,\n"
        "                {\n"
        '                    "cpu": CPUGraphRunner,\n'
        '                    "npu": NPUGraphRunner,\n'
        "                },\n"
        "            )\n"
        "            self.graph_runner = graph_runners[self.device](self)\n"
        "\n"
        "        after_mem = get_available_gpu_memory(self.device, self.gpu_id)\n"
        "        self.graph_mem_usage = before_mem - after_mem\n"
        "        logger.info(\n"
        '            f"Capture {graph_backend[self.device]} end. Time elapsed: {time.perf_counter() - tic:.2f} s. "\n'
        '            f"mem usage={self.graph_mem_usage:.2f} GB. avail mem={after_mem:.2f} GB."\n'
        "        )\n"
    )
    assert old_method in text, "init_device_graphs method not found"

    new_delegate = (
        "    def init_device_graphs(self):\n"
        "        self.graph_runner, self.graph_mem_usage = init_device_graphs(\n"
        "            model_runner_ref=self,\n"
        "            is_generation=self.is_generation,\n"
        "            server_args=self.server_args,\n"
        "            device=self.device,\n"
        "            gpu_id=self.gpu_id,\n"
        "        )\n"
    )
    text = text.replace(old_method, new_delegate)

    # Add import for the free function. Anchor on the existing
    # cuda_graph_runner / piecewise_cuda_graph_runner imports — pick a
    # neighbouring stable import that exists at /31.
    old_import = (
        "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n"
    )
    new_import = (
        "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n"
        "from sglang.srt.model_executor.device_graphs import (\n"
        "    init_device_graphs as _init_device_graphs_impl,\n"
        ")\n"
    )
    assert old_import in text, "CPUGraphRunner import not found"
    text = text.replace(old_import, new_import)

    # The delegate above calls `init_device_graphs(...)` — that name shadows
    # the method itself inside the class. Rebind the call to the alias.
    text = text.replace(
        "        self.graph_runner, self.graph_mem_usage = init_device_graphs(\n",
        "        self.graph_runner, self.graph_mem_usage = _init_device_graphs_impl(\n",
    )

    mr.write_text(text)

    git_add_and_commit(
        "Extract init_device_graphs to free function in model_executor.device_graphs",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
