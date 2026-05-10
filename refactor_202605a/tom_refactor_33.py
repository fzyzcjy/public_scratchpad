#!/usr/bin/env python3
"""Cut `init_piecewise_cuda_graphs` from ModelRunner; paste as a free function
in the existing `model_executor/device_graphs.py`.

R4 concession: 6 early `return` statements + writes to 4 `self.X` fields
interleaved with reads, plus `BreakableCudaGraphRunner(self)` /
`PiecewiseCudaGraphRunner(self)` ctors that take ModelRunner. Body byte-identical
modulo ``self`` -> ``model_runner_ref``.

`resolve_language_model` is a module-level free function in `model_runner.py`
(circular import target) — we forward it as a kwarg from the caller so the body
doesn't need a new top-level import or local import statement.
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

BASE = "tom_refactor/32"
TARGET = "tom_refactor/33"


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    dg = wt / "python/sglang/srt/model_executor/device_graphs.py"

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_piecewise_cuda_graphs",
    )
    func_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def init_piecewise_cuda_graphs(self):\n",
            "def init_piecewise_cuda_graphs(*, model_runner_ref, resolve_language_model):\n",
        )
        .replace("self.", "model_runner_ref.")
        # Bare `self` ctor args (e.g., `BreakableCudaGraphRunner(self)`).
        .replace("(self)", "(model_runner_ref)")
    )

    # Append the function (with required imports) to device_graphs.py.
    dg_text = dg.read_text()
    dg_text = insert_after(
        dg_text,
        anchor="from sglang.srt.hardware_backend.npu.graph_runner.npu_graph_runner import NPUGraphRunner\n",
        addition=(
            "from sglang.srt.model_executor.breakable_cuda_graph_runner import (\n"
            "    BreakableCudaGraphRunner,\n"
            ")\n"
            "from sglang.srt.model_executor.piecewise_cuda_graph_runner import (\n"
            "    PiecewiseCudaGraphRunner,\n"
            ")\n"
        ),
    )
    dg_text = dg_text.replace(
        "from sglang.srt.utils import get_available_gpu_memory\n",
        "from sglang.srt.utils import get_available_gpu_memory, log_info_on_rank0\n",
    )
    dg_text = dg_text.rstrip() + "\n\n\n" + func_text
    dg.write_text(dg_text)

    # ---- Update model_runner.py ----
    text = mr.read_text()
    if "from sglang.srt.model_executor import device_graphs\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
            addition="from sglang.srt.model_executor import device_graphs\n",
        )
    text = text.replace(
        "self.init_piecewise_cuda_graphs()",
        (
            "device_graphs.init_piecewise_cuda_graphs(\n"
            "            model_runner_ref=self,\n"
            "            resolve_language_model=resolve_language_model,\n"
            "        )"
        ),
    )
    mr.write_text(text)

    git_add_and_commit(
        "Extract init_piecewise_cuda_graphs to free function in model_executor.device_graphs",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
