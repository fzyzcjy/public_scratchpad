#!/usr/bin/env python3
"""Cut `init_piecewise_cuda_graphs` from ModelRunner; paste as a free function
in the existing `model_executor/device_graphs.py`.

The 4 ``self.X = ...`` writes (``piecewise_cuda_graph_runner``,
``attention_layers``, ``moe_layers``, ``moe_fusions``) become locals; the
function returns the 4-tuple. The single caller in ModelRunner unpacks it
back onto ``self.X``.

PiecewiseCudaGraphRunner / BreakableCudaGraphRunner ctors take ModelRunner,
so we forward ``self`` as ``model_runner_ref`` (R4 concession).
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

BASE_COMMIT = "tom_refactor/32"
TARGET_COMMIT = "tom_refactor/33"


_TUPLE_RETURN = (
    "return piecewise_cuda_graph_runner, attention_layers, moe_layers, moe_fusions"
)


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    dg = dir_root / "python/sglang/srt/model_executor/device_graphs.py"

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_piecewise_cuda_graphs",
    )
    func_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def init_piecewise_cuda_graphs(self):",
            "def init_piecewise_cuda_graphs(\n"
            "    *,\n"
            "    model_runner_ref,\n"
            "    server_args,\n"
            "    device,\n"
            "    gpu_id,\n"
            "    is_draft_worker,\n"
            "    model,\n"
            "    model_config,\n"
            "):",
        )
        .replace("self.server_args", "server_args")
        .replace("self.is_draft_worker", "is_draft_worker")
        .replace("self.model_config", "model_config")
        .replace("self.device", "device")
        .replace("self.gpu_id", "gpu_id")
        .replace("self.piecewise_cuda_graph_runner", "piecewise_cuda_graph_runner")
        .replace("self.attention_layers", "attention_layers")
        .replace("self.moe_layers", "moe_layers")
        .replace("self.moe_fusions", "moe_fusions")
        .replace("self.model", "model")
        # The two ctor calls take `self`; forward as `model_runner_ref`.
        .replace("BreakableCudaGraphRunner(self)", "BreakableCudaGraphRunner(model_runner_ref)")
        .replace("PiecewiseCudaGraphRunner(self)", "PiecewiseCudaGraphRunner(model_runner_ref)")
    )

    # Replace each bare `return\n` (early-return) with the tuple return.
    # Use the full surrounding line to keep matches stable.
    early_return_replacements = [
        (
            '            "Disable piecewise CUDA graph because --disable-piecewise-cuda-graph is set"\n'
            "        )\n"
            "        return\n",
            '            "Disable piecewise CUDA graph because --disable-piecewise-cuda-graph is set"\n'
            "        )\n"
            f"        {_TUPLE_RETURN}\n",
        ),
        (
            "    # Draft models use decode CUDA graphs, not PCG\n"
            "    if is_draft_worker:\n"
            "        return\n",
            "    # Draft models use decode CUDA graphs, not PCG\n"
            "    if is_draft_worker:\n"
            f"        {_TUPLE_RETURN}\n",
        ),
        (
            '            "Disable piecewise CUDA graph because the model is not a language model"\n'
            "        )\n"
            "        return\n",
            '            "Disable piecewise CUDA graph because the model is not a language model"\n'
            "        )\n"
            f"        {_TUPLE_RETURN}\n",
        ),
        (
            '            "Disable piecewise CUDA graph because the capture size is not set"\n'
            "        )\n"
            "        return\n",
            '            "Disable piecewise CUDA graph because the capture size is not set"\n'
            "        )\n"
            f"        {_TUPLE_RETURN}\n",
        ),
        (
            '            "Disable piecewise CUDA graph because the model does not have a \'layers\' attribute"\n'
            "        )\n"
            "        return\n",
            '            "Disable piecewise CUDA graph because the model does not have a \'layers\' attribute"\n'
            "        )\n"
            f"        {_TUPLE_RETURN}\n",
        ),
        (
            '            "Disable piecewise CUDA graph because some layers do not apply Standard GQA",\n'
            "        )\n"
            "        return\n",
            '            "Disable piecewise CUDA graph because some layers do not apply Standard GQA",\n'
            "        )\n"
            f"        {_TUPLE_RETURN}\n",
        ),
    ]
    for old, new in early_return_replacements:
        assert old in func_text, f"early-return anchor not found:\n{old!r}"
        func_text = func_text.replace(old, new)

    # Initialize the four locals at the top so early returns can reference them.
    func_text = func_text.replace(
        "    \"\"\"Initialize piecewise CUDA graph runner.\"\"\"\n"
        "    piecewise_cuda_graph_runner = None\n",
        "    \"\"\"Initialize piecewise CUDA graph runner.\"\"\"\n"
        "    piecewise_cuda_graph_runner = None\n"
        "    attention_layers = None\n"
        "    moe_layers = None\n"
        "    moe_fusions = None\n",
    )

    # Add a final tuple return at the end of the function body.
    func_text = func_text.rstrip() + f"\n    {_TUPLE_RETURN}\n"

    # `resolve_language_model` lives in model_runner.py; import it lazily
    # inside the function to avoid a circular import.
    func_text = func_text.replace(
        "    \"\"\"Initialize piecewise CUDA graph runner.\"\"\"\n",
        "    \"\"\"Initialize piecewise CUDA graph runner.\"\"\"\n"
        "    from sglang.srt.model_executor.model_runner import resolve_language_model\n"
        "\n",
    )

    # Append the function (with required imports) to device_graphs.py.
    dg_text = dg.read_text()
    new_imports = (
        "from sglang.srt.model_executor.breakable_cuda_graph_runner import (\n"
        "    BreakableCudaGraphRunner,\n"
        ")\n"
        "from sglang.srt.model_executor.piecewise_cuda_graph_runner import (\n"
        "    PiecewiseCudaGraphRunner,\n"
        ")\n"
    )
    dg_text = insert_after(
        dg_text,
        anchor="from sglang.srt.hardware_backend.npu.graph_runner.npu_graph_runner import NPUGraphRunner\n",
        addition=new_imports,
    )
    # Add log_info_on_rank0 to existing utils import.
    dg_text = dg_text.replace(
        "from sglang.srt.utils import get_available_gpu_memory\n",
        "from sglang.srt.utils import get_available_gpu_memory, log_info_on_rank0\n",
    )
    dg_text = dg_text.rstrip() + "\n\n\n" + func_text
    dg.write_text(dg_text)

    # ---- Update model_runner.py ----
    text = mr.read_text()
    text = insert_after(
        text,
        anchor=(
            "from sglang.srt.model_executor.device_graphs import (\n"
            "    init_device_graphs as _init_device_graphs_impl,\n"
            ")\n"
        ),
        addition=(
            "from sglang.srt.model_executor.device_graphs import (\n"
            "    init_piecewise_cuda_graphs as _init_piecewise_cuda_graphs_impl,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        self.init_piecewise_cuda_graphs()\n",
        new=(
            "        (\n"
            "            self.piecewise_cuda_graph_runner,\n"
            "            self.attention_layers,\n"
            "            self.moe_layers,\n"
            "            self.moe_fusions,\n"
            "        ) = _init_piecewise_cuda_graphs_impl(\n"
            "            model_runner_ref=self,\n"
            "            server_args=self.server_args,\n"
            "            device=self.device,\n"
            "            gpu_id=self.gpu_id,\n"
            "            is_draft_worker=self.is_draft_worker,\n"
            "            model=self.model,\n"
            "            model_config=self.model_config,\n"
            "        )\n"
        ),
    )
    mr.write_text(text)

    git_add_and_commit(
        "Extract init_piecewise_cuda_graphs to free function in model_executor.device_graphs",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
