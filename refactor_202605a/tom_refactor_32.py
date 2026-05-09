#!/usr/bin/env python3
"""Cut `init_device_graphs` from ModelRunner; paste as a free function in a
new file `model_executor/device_graphs.py`. The 2 ``self.X = ...`` writes
become locals; the function returns the tuple ``(graph_runner, graph_mem_usage)``.

GraphRunner ctors take ModelRunner as their sole argument, so we forward
``self`` as ``model_runner_ref`` (R4 concession). Callers in ModelRunner
unpack the returned tuple back onto ``self.graph_runner`` /
``self.graph_mem_usage``.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import (
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/31"
TARGET_COMMIT = "tom_refactor/32"


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


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    dg = dir_root / "python/sglang/srt/model_executor/device_graphs.py"

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_device_graphs",
    )
    func_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def init_device_graphs(self):",
            "def init_device_graphs(\n"
            "    *,\n"
            "    model_runner_ref,\n"
            "    is_generation,\n"
            "    server_args,\n"
            "    device,\n"
            "    gpu_id,\n"
            "):",
        )
        .replace("self.is_generation", "is_generation")
        .replace("self.server_args", "server_args")
        .replace("self.device", "device")
        .replace("self.gpu_id", "gpu_id")
        .replace("self.graph_runner", "graph_runner")
        .replace("self.graph_mem_usage", "graph_mem_usage")
        .replace("GraphRunnerCls(self)", "GraphRunnerCls(model_runner_ref)")
        .replace("graph_runners[device](self)", "graph_runners[device](model_runner_ref)")
    )
    # Replace the bare `return` (no value) inside the function with
    # `return graph_runner, graph_mem_usage` and append the same return at
    # the end (originally implicit None).
    func_text = func_text.replace(
        "    if not is_generation:\n"
        "        # TODO: Currently, cuda graph only captures decode steps, which only exists for generation models\n"
        "        return\n",
        "    if not is_generation:\n"
        "        # TODO: Currently, cuda graph only captures decode steps, which only exists for generation models\n"
        "        return graph_runner, graph_mem_usage\n",
    )
    func_text = func_text.replace(
        "    if server_args.model_impl.lower() == ModelImpl.MINDSPORE:\n"
        "        return\n",
        "    if server_args.model_impl.lower() == ModelImpl.MINDSPORE:\n"
        "        return graph_runner, graph_mem_usage\n",
    )
    func_text = func_text.replace(
        '    if device != "cpu" and server_args.disable_cuda_graph:\n'
        "        return\n",
        '    if device != "cpu" and server_args.disable_cuda_graph:\n'
        "        return graph_runner, graph_mem_usage\n",
    )
    func_text = func_text.replace(
        '    if device == "cpu" and not server_args.enable_torch_compile:\n'
        "        return\n",
        '    if device == "cpu" and not server_args.enable_torch_compile:\n'
        "        return graph_runner, graph_mem_usage\n",
    )
    # Append final return (no trailing newline tweak — function ends with logger.info call).
    if not func_text.rstrip().endswith("return graph_runner, graph_mem_usage"):
        func_text = func_text.rstrip() + "\n    return graph_runner, graph_mem_usage\n"

    dg.write_text(_DEVICE_GRAPHS_HEADER + func_text)

    # ---- Update model_runner.py: add import + replace each call site ----
    text = mr.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
        addition=(
            "from sglang.srt.model_executor.device_graphs import (\n"
            "    init_device_graphs as _init_device_graphs_impl,\n"
            ")\n"
        ),
    )

    def _expanded_call(leading_indent: str) -> str:
        return (
            "self.graph_runner, self.graph_mem_usage = _init_device_graphs_impl(\n"
            f"{leading_indent}    model_runner_ref=self,\n"
            f"{leading_indent}    is_generation=self.is_generation,\n"
            f"{leading_indent}    server_args=self.server_args,\n"
            f"{leading_indent}    device=self.device,\n"
            f"{leading_indent}    gpu_id=self.gpu_id,\n"
            f"{leading_indent})"
        )

    # Replace each call site, distinguishing by leading indent. Use the full
    # line (with indent) as the anchor so each replacement is unique.
    while "self.init_device_graphs()" in text:
        idx = text.index("self.init_device_graphs()")
        line_start = text.rfind("\n", 0, idx) + 1
        leading = text[line_start:idx]
        assert leading.strip() == "", f"unexpected non-whitespace leading: {leading!r}"
        old = leading + "self.init_device_graphs()"
        new = leading + _expanded_call(leading)
        text = text.replace(old, new, 1)

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
