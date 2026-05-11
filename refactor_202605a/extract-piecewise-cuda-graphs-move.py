#!/usr/bin/env python3
"""Move stage for extract-piecewise-cuda-graphs (MECH_COMMIT_SPLIT §"二段式"):

Pure cut+paste to ``model_executor/device_graphs.py``. Body byte-equivalent.
Call site prefix-strip. Adds the missing imports the body needs and breaks
the import cycle on ``resolve_language_model`` with a local-import form.
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
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-piecewise-cuda-graphs-move"
SUBJECT = "Move create_piecewise_cuda_graphs to model_executor.device_graphs (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-piecewise-cuda-graphs-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    dg = wt / "python/sglang/srt/model_executor/device_graphs.py"

    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="create_piecewise_cuda_graphs"
    )
    method_text = cut_lines(mr, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    function_text = dedent_method_to_function("".join(lines[1:]))

    # Expand imports in device_graphs.py for the new body needs.
    dg_text = dg.read_text()
    dg_text = replace_call_site(
        dg_text,
        old="from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
        new=(
            "from sglang.srt.model_executor.breakable_cuda_graph_runner import (\n"
            "    BreakableCudaGraphRunner,\n"
            ")\n"
            "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n"
        ),
    )
    dg_text = replace_call_site(
        dg_text,
        old=(
            "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n"
            "from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner\n"
        ),
        new=(
            "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n"
            "from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner\n"
            "from sglang.srt.model_executor.piecewise_cuda_graph_runner import (\n"
            "    PiecewiseCudaGraphRunner,\n"
            ")\n"
        ),
    )
    dg_text = replace_call_site(
        dg_text,
        old="from sglang.srt.utils import get_available_gpu_memory\n",
        new="from sglang.srt.utils import get_available_gpu_memory, log_info_on_rank0\n",
    )
    dg.write_text(dg_text)
    append_to_file(dg, function_text)

    # Break the resolve_language_model cycle with a local import.
    dg_text = dg.read_text()
    dg_text = replace_call_site(
        dg_text,
        old="    model_runner.model.model = resolve_language_model(model_runner.model)\n",
        new=(
            "    from sglang.srt.model_executor.model_runner import resolve_language_model\n"
            "\n"
            "    model_runner.model.model = resolve_language_model(model_runner.model)\n"
        ),
    )
    dg.write_text(dg_text)

    text = mr.read_text()
    text = replace_call_site(
        text,
        old="ModelRunner.create_piecewise_cuda_graphs(",
        new="device_graphs.create_piecewise_cuda_graphs(",
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
