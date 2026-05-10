#!/usr/bin/env python3
"""Cut `init_piecewise_cuda_graphs` from ModelRunner; paste as a free function
in `model_executor/device_graphs.py` with explicit kwargs + dataclass return.

Body has 4 self-write writebacks (piecewise_cuda_graph_runner, attention_layers,
moe_layers, moe_fusions) + multiple `self.X` reads + nested attr mutation
``self.model.model = resolve_language_model(self.model)``. Per ≥3 writebacks
rule, return is a frozen/slots/kw_only dataclass.

The two ctor calls ``BreakableCudaGraphRunner(self)`` /
``PiecewiseCudaGraphRunner(self)`` need a ModelRunner ref. To avoid an R4
concession kwarg, the caller closures over `self` in a `make_runner` factory
that selects the class itself based on
`self.server_args.enable_breakable_cuda_graph`.

The 6 early bail paths each return a dataclass with `None`/`None`/`None`/`None`
fields so the caller's writeback unpack still works.

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


_RESULT_DATACLASS = '''\


@dataclass(frozen=True, slots=True, kw_only=True)
class PiecewiseCudaGraphsResult:
    piecewise_cuda_graph_runner: Any
    attention_layers: Optional[list[Any]]
    moe_layers: Optional[list[Any]]
    moe_fusions: Optional[list[Any]]


_PIECEWISE_BAIL = PiecewiseCudaGraphsResult(
    piecewise_cuda_graph_runner=None,
    attention_layers=None,
    moe_layers=None,
    moe_fusions=None,
)
'''


_PIECEWISE_FN = '''\


def init_piecewise_cuda_graphs(
    *,
    server_args: ServerArgs,
    is_draft_worker: bool,
    model: nn.Module,
    model_config: ModelConfig,
    device: str,
    gpu_id: int,
    resolve_language_model: Callable[[nn.Module], nn.Module],
    make_runner: Callable[[], Any],
) -> PiecewiseCudaGraphsResult:
    """Initialize piecewise CUDA graph runner."""
    if server_args.disable_piecewise_cuda_graph:
        logger.info(
            "Disable piecewise CUDA graph because --disable-piecewise-cuda-graph is set"
        )
        return _PIECEWISE_BAIL

    # Draft models use decode CUDA graphs, not PCG
    if is_draft_worker:
        return _PIECEWISE_BAIL

    # Disable piecewise CUDA graph for non-language models
    if not hasattr(model, "model"):
        logger.warning(
            "Disable piecewise CUDA graph because the model is not a language model"
        )
        return _PIECEWISE_BAIL

    # Disable piecewise CUDA graph for non capture size
    if not server_args.piecewise_cuda_graph_tokens:
        logger.warning(
            "Disable piecewise CUDA graph because the capture size is not set"
        )
        return _PIECEWISE_BAIL

    # Collect attention layers and moe layers from the model
    model.model = resolve_language_model(model)
    language_model = getattr(model, "language_model", model)

    # Resolve model with layers: handle CausalLM wrapper (.model.layers) and direct TextModel (.layers)
    if hasattr(language_model, "model") and hasattr(language_model.model, "layers"):
        layer_model = language_model.model
    elif hasattr(language_model, "layers"):
        layer_model = language_model
    else:
        logger.warning(
            "Disable piecewise CUDA graph because the model does not have a 'layers' attribute"
        )
        return _PIECEWISE_BAIL

    attention_layers: list[Any] = []
    moe_layers: list[Any] = []
    moe_fusions: list[Any] = []
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
            attention_layers.append(attn_layer)
        elif hasattr(layer, "mixer"):
            attention_layers.append(None)

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
        moe_layers.append(moe_block)
        moe_fusions.append(moe_fusion)

    if len(attention_layers) < model_config.num_hidden_layers:
        # TODO(yuwei): support Non-Standard GQA
        log_info_on_rank0(
            logger,
            "Disable piecewise CUDA graph because some layers do not apply Standard GQA",
        )
        return PiecewiseCudaGraphsResult(
            piecewise_cuda_graph_runner=None,
            attention_layers=attention_layers,
            moe_layers=moe_layers,
            moe_fusions=moe_fusions,
        )

    tic = time.perf_counter()
    before_mem = get_available_gpu_memory(device, gpu_id)
    logger.info(
        f"Capture piecewise CUDA graph begin. avail mem={before_mem:.2f} GB"
    )

    piecewise_cuda_graph_runner = make_runner()

    after_mem = get_available_gpu_memory(device, gpu_id)
    mem_usage = before_mem - after_mem
    logger.info(
        f"Capture piecewise CUDA graph end. Time elapsed: {time.perf_counter() - tic:.2f} s. "
        f"mem usage={mem_usage:.2f} GB. avail mem={after_mem:.2f} GB."
    )
    return PiecewiseCudaGraphsResult(
        piecewise_cuda_graph_runner=piecewise_cuda_graph_runner,
        attention_layers=attention_layers,
        moe_layers=moe_layers,
        moe_fusions=moe_fusions,
    )
'''


# Caller-side replacement for `self.init_piecewise_cuda_graphs()`. The
# `_make_piecewise_runner` closure owns the BreakableCudaGraphRunner /
# PiecewiseCudaGraphRunner ctor selection (was inline `if/else` in the
# original body); it captures `self` so the ctors get a ModelRunner ref
# without needing an R4 kwarg on the free function.
_CALLER_REPLACEMENT = '''\
        def _make_piecewise_runner():
            if self.server_args.enable_breakable_cuda_graph:
                # Experimental feature
                return BreakableCudaGraphRunner(self)
            return PiecewiseCudaGraphRunner(self)

        _piecewise_result = device_graphs.init_piecewise_cuda_graphs(
            server_args=self.server_args,
            is_draft_worker=self.is_draft_worker,
            model=self.model,
            model_config=self.model_config,
            device=self.device,
            gpu_id=self.gpu_id,
            resolve_language_model=resolve_language_model,
            make_runner=_make_piecewise_runner,
        )
        self.piecewise_cuda_graph_runner = _piecewise_result.piecewise_cuda_graph_runner
        self.attention_layers = _piecewise_result.attention_layers
        self.moe_layers = _piecewise_result.moe_layers
        self.moe_fusions = _piecewise_result.moe_fusions\
'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    dg = wt / "python/sglang/srt/model_executor/device_graphs.py"

    # Cut method (and discard the body — we re-emit it inline).
    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_piecewise_cuda_graphs",
    )
    cut_lines(mr, s, e)

    # device_graphs.py: extend imports + append result dataclass + free fn.
    dg_text = dg.read_text()
    # The model_config / model / Optional / dataclass / log_info_on_rank0 /
    # PiecewiseCudaGraphRunner / BreakableCudaGraphRunner imports are not yet
    # in device_graphs.py — add them. The Any/Callable/ServerArgs/nn imports
    # are already present (added by /init-device-graphs).
    dg_text = replace_call_site(
        dg_text,
        old="from typing import Any, Callable\n",
        new="from dataclasses import dataclass\nfrom typing import Any, Callable, Optional\n",
    )
    dg_text = replace_call_site(
        dg_text,
        old="from sglang.srt.configs.model_config import ModelImpl\n",
        new=(
            "from sglang.srt.configs.model_config import ModelConfig, ModelImpl\n"
            "from sglang.srt.model_executor.breakable_cuda_graph_runner import (\n"
            "    BreakableCudaGraphRunner,\n"
            ")\n"
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
    # Insert torch.nn.Module import (needed for `model: nn.Module` annotation).
    dg_text = insert_after(
        dg_text,
        anchor="from sglang.srt.utils import get_available_gpu_memory, log_info_on_rank0\n",
        addition="from torch import nn\n",
    )
    dg_text = dg_text.rstrip() + "\n" + _RESULT_DATACLASS + _PIECEWISE_FN
    dg.write_text(dg_text)

    # ---- Update model_runner.py call site ----
    text = mr.read_text()
    text = replace_call_site(
        text,
        old="        self.init_piecewise_cuda_graphs()",
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
