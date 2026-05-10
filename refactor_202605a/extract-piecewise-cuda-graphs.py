#!/usr/bin/env python3
"""Cut `init_piecewise_cuda_graphs` from ModelRunner; paste as a free
function in `model_executor/device_graphs.py` taking
`model_runner: ModelRunner`.

Body is a mechanical copy of the original method with `self` →
`model_runner`. Writebacks (``piecewise_cuda_graph_runner``,
``attention_layers``, ``moe_layers``, ``moe_fusions``) happen in-place
via the ref, so the function returns ``None`` and the bail paths become
bare ``return``. Caller side becomes a single line:
``self.init_piecewise_cuda_graphs()`` →
``device_graphs.init_piecewise_cuda_graphs(self)``.

Usage:
    uv run --python 3.12 extract-piecewise-cuda-graphs.py run
    uv run --python 3.12 extract-piecewise-cuda-graphs.py verify
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

ID = "extract-piecewise-cuda-graphs"
SUBJECT = "Extract init_piecewise_cuda_graphs to free function in model_executor.device_graphs"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-init-device-graphs"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_PIECEWISE_FN = '''\


def init_piecewise_cuda_graphs(model_runner: "ModelRunner") -> None:
    """Initialize piecewise CUDA graph runner."""
    model_runner.piecewise_cuda_graph_runner = None

    if model_runner.server_args.disable_piecewise_cuda_graph:
        logger.info(
            "Disable piecewise CUDA graph because --disable-piecewise-cuda-graph is set"
        )
        return

    # Draft models use decode CUDA graphs, not PCG
    if model_runner.is_draft_worker:
        return

    # Disable piecewise CUDA graph for non-language models
    if not hasattr(model_runner.model, "model"):
        logger.warning(
            "Disable piecewise CUDA graph because the model is not a language model"
        )
        return

    # Disable piecewise CUDA graph for non capture size
    if not model_runner.server_args.piecewise_cuda_graph_tokens:
        logger.warning(
            "Disable piecewise CUDA graph because the capture size is not set"
        )
        return

    # Collect attention layers and moe layers from the model
    model_runner.model.model = resolve_language_model(model_runner.model)
    language_model = getattr(model_runner.model, "language_model", model_runner.model)

    # Resolve model with layers: handle CausalLM wrapper (.model.layers) and direct TextModel (.layers)
    if hasattr(language_model, "model") and hasattr(language_model.model, "layers"):
        layer_model = language_model.model
    elif hasattr(language_model, "layers"):
        layer_model = language_model
    else:
        logger.warning(
            "Disable piecewise CUDA graph because the model does not have a 'layers' attribute"
        )
        return

    model_runner.attention_layers = []
    model_runner.moe_layers = []
    model_runner.moe_fusions = []
    for layer in layer_model.layers:
        attn_layer = None
        if hasattr(layer, "self_attn"):
            if hasattr(layer.self_attn, "attn"):
                attn_layer = layer.self_attn.attn
            elif hasattr(layer.self_attn, "attn_mqa"):
                # For DeepSeek model
                attn_layer = layer.self_attn.attn_mqa
        # For hybrid model
        elif hasattr(layer, "attn"):
            attn_layer = layer.attn
        elif hasattr(layer, "linear_attn"):
            if hasattr(layer.linear_attn, "attn"):
                attn_layer = layer.linear_attn.attn
            else:
                attn_layer = layer.linear_attn
        # For InternVL model
        elif hasattr(layer, "attention"):
            if hasattr(layer.attention, "attn"):
                attn_layer = layer.attention.attn
        # For NemotronH and similar hybrid models using 'mixer' attribute
        elif hasattr(layer, "mixer"):
            if hasattr(layer.mixer, "attn"):
                attn_layer = layer.mixer.attn
            elif hasattr(layer, "_forward_mamba"):
                # Mamba layer with split op support - store the layer itself
                attn_layer = layer

        if attn_layer is not None:
            model_runner.attention_layers.append(attn_layer)
        elif hasattr(layer, "mixer"):
            model_runner.attention_layers.append(None)

        moe_block = None
        moe_fusion = None
        if hasattr(layer, "mlp") and hasattr(layer.mlp, "experts"):
            moe_block = layer.mlp.experts
            moe_fusion = layer.mlp
        if hasattr(layer, "block_sparse_moe") and hasattr(
            layer.block_sparse_moe, "experts"
        ):
            moe_block = layer.block_sparse_moe.experts
            moe_fusion = layer.block_sparse_moe
        if hasattr(layer, "moe") and hasattr(layer.moe, "experts"):
            moe_block = layer.moe.experts
            moe_fusion = layer.moe
        # For NemotronH MoE layers using 'mixer' attribute
        if hasattr(layer, "mixer") and hasattr(layer.mixer, "experts"):
            moe_block = layer.mixer.experts
            moe_fusion = layer.mixer
        model_runner.moe_layers.append(moe_block)
        model_runner.moe_fusions.append(moe_fusion)

    if len(model_runner.attention_layers) < model_runner.model_config.num_hidden_layers:
        # TODO(yuwei): support Non-Standard GQA
        log_info_on_rank0(
            logger,
            "Disable piecewise CUDA graph because some layers do not apply Standard GQA",
        )
        return

    tic = time.perf_counter()
    before_mem = get_available_gpu_memory(model_runner.device, model_runner.gpu_id)
    logger.info(
        f"Capture piecewise CUDA graph begin. avail mem={before_mem:.2f} GB"
    )

    if model_runner.server_args.enable_breakable_cuda_graph:
        # Experimental feature
        model_runner.piecewise_cuda_graph_runner = BreakableCudaGraphRunner(model_runner)
    else:
        model_runner.piecewise_cuda_graph_runner = PiecewiseCudaGraphRunner(model_runner)

    after_mem = get_available_gpu_memory(model_runner.device, model_runner.gpu_id)
    mem_usage = before_mem - after_mem
    logger.info(
        f"Capture piecewise CUDA graph end. Time elapsed: {time.perf_counter() - tic:.2f} s. "
        f"mem usage={mem_usage:.2f} GB. avail mem={after_mem:.2f} GB."
    )
'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    dg = wt / "python/sglang/srt/model_executor/device_graphs.py"

    # 1) Cut method def from ModelRunner.
    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_piecewise_cuda_graphs",
    )
    cut_lines(mr, s, e)

    # 2) Append the free function to device_graphs.py. The
    # ``BreakableCudaGraphRunner`` / ``PiecewiseCudaGraphRunner`` ctors,
    # ``log_info_on_rank0``, and ``resolve_language_model`` need imports;
    # add them. The Any/TYPE_CHECKING/ModelRunner forward-ref/time/etc. are
    # already in place from extract-init-device-graphs.
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
        old="from sglang.srt.model_executor.npu_graph_runner import NPUGraphRunner\n",
        new=(
            "from sglang.srt.model_executor.npu_graph_runner import NPUGraphRunner\n"
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
    # `resolve_language_model` lives in model_runner.py at this point; the
    # later `move-resolve-language-model` commit will move it to
    # `model_loader.utils`. For now import it from model_runner via a local
    # import inside the function to avoid a circular dependency (device_graphs
    # is imported from model_runner; importing back at module level would
    # loop).
    dg_text = dg_text.rstrip() + "\n" + _PIECEWISE_FN
    # Replace top-level `resolve_language_model(...)` call with a local-import
    # form so the device_graphs module doesn't cycle through model_runner.
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

    # 3) Wire up model_runner.py call-site (single occurrence).
    text = mr.read_text()
    if "from sglang.srt.model_executor import device_graphs\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n",
            addition="from sglang.srt.model_executor import device_graphs\n",
        )
    text = replace_call_site(
        text,
        old="self.init_piecewise_cuda_graphs()",
        new="device_graphs.init_piecewise_cuda_graphs(self)",
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
