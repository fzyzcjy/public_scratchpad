#!/usr/bin/env python3
"""Reproducible transform: extract `ModelRunner.init_piecewise_cuda_graphs` to
a free function `init_piecewise_cuda_graphs` in
`sglang.srt.model_executor.device_graphs`.

Strict-minimal mechanical extraction:
  - PiecewiseCudaGraphRunner / BreakableCudaGraphRunner ctors take `ModelRunner`,
    so we forward `self` as `model_runner_ref` (R4 concession). The 70-line
    model-walking loop also writes back several fields on `ModelRunner`
    (`attention_layers`, `moe_layers`, `moe_fusions`, `model.model`); these
    writes go through `model_runner_ref` for byte-identical bodies.
  - The original method on `ModelRunner` becomes a 1-line delegate.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/32"
TARGET_COMMIT = "tom_refactor/33"


def transform(dir_root: Path) -> None:
    dg = dir_root / "python/sglang/srt/model_executor/device_graphs.py"
    text = dg.read_text()

    # Append imports needed for the new function (only those not already
    # imported by /32). `BreakableCudaGraphRunner`, `PiecewiseCudaGraphRunner`,
    # `resolve_language_model`, `log_info_on_rank0` are new.
    old_imports_block = (
        "from sglang.srt.hardware_backend.npu.graph_runner.npu_graph_runner import NPUGraphRunner\n"
        "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n"
        "from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner\n"
    )
    new_imports_block = (
        "from sglang.srt.hardware_backend.npu.graph_runner.npu_graph_runner import NPUGraphRunner\n"
        "from sglang.srt.model_executor.breakable_cuda_graph_runner import (\n"
        "    BreakableCudaGraphRunner,\n"
        ")\n"
        "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n"
        "from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner\n"
        "from sglang.srt.model_executor.piecewise_cuda_graph_runner import (\n"
        "    PiecewiseCudaGraphRunner,\n"
        ")\n"
    )
    assert old_imports_block in text, "device_graphs.py imports anchor not found"
    text = text.replace(old_imports_block, new_imports_block)

    # `resolve_language_model` is currently a free function in model_runner.py;
    # we import it from there.
    text = text.replace(
        "from sglang.srt.utils import get_available_gpu_memory\n",
        "from sglang.srt.utils import get_available_gpu_memory, log_info_on_rank0\n",
    )

    # Forward-import `resolve_language_model` from model_runner. It already
    # lives at module scope there. Add as a local import inside the function
    # to avoid a circular import at module load time.
    free_func = (
        "\n\n"
        "def init_piecewise_cuda_graphs(\n"
        "    *,\n"
        '    model_runner_ref: "ModelRunner",  # R4 concession: PiecewiseCudaGraphRunner ctor requires ModelRunner\n'
        "    server_args: ServerArgs,\n"
        "    device: str,\n"
        "    gpu_id: int,\n"
        "    is_draft_worker: bool,\n"
        "    model,\n"
        "    model_config,\n"
        ") -> None:\n"
        '    """Initialize piecewise CUDA graph runner."""\n'
        "    from sglang.srt.model_executor.model_runner import resolve_language_model\n"
        "\n"
        "    model_runner_ref.piecewise_cuda_graph_runner = None\n"
        "\n"
        "    if server_args.disable_piecewise_cuda_graph:\n"
        "        logger.info(\n"
        '            "Disable piecewise CUDA graph because --disable-piecewise-cuda-graph is set"\n'
        "        )\n"
        "        return\n"
        "\n"
        "    # Draft models use decode CUDA graphs, not PCG\n"
        "    if is_draft_worker:\n"
        "        return\n"
        "\n"
        "    # Disable piecewise CUDA graph for non-language models\n"
        '    if not hasattr(model, "model"):\n'
        "        logger.warning(\n"
        '            "Disable piecewise CUDA graph because the model is not a language model"\n'
        "        )\n"
        "        return\n"
        "\n"
        "    # Disable piecewise CUDA graph for non capture size\n"
        "    if not server_args.piecewise_cuda_graph_tokens:\n"
        "        logger.warning(\n"
        '            "Disable piecewise CUDA graph because the capture size is not set"\n'
        "        )\n"
        "        return\n"
        "\n"
        "    # Collect attention layers and moe layers from the model\n"
        "    model.model = resolve_language_model(model)\n"
        '    language_model = getattr(model, "language_model", model)\n'
        "\n"
        "    # Resolve model with layers: handle CausalLM wrapper (.model.layers) and direct TextModel (.layers)\n"
        '    if hasattr(language_model, "model") and hasattr(language_model.model, "layers"):\n'
        "        layer_model = language_model.model\n"
        '    elif hasattr(language_model, "layers"):\n'
        "        layer_model = language_model\n"
        "    else:\n"
        "        logger.warning(\n"
        '            "Disable piecewise CUDA graph because the model does not have a \'layers\' attribute"\n'
        "        )\n"
        "        return\n"
        "\n"
        "    model_runner_ref.attention_layers = []\n"
        "    model_runner_ref.moe_layers = []\n"
        "    model_runner_ref.moe_fusions = []\n"
        "    for layer in layer_model.layers:\n"
        "        attn_layer = None\n"
        '        if hasattr(layer, "self_attn"):\n'
        '            if hasattr(layer.self_attn, "attn"):\n'
        "                attn_layer = layer.self_attn.attn\n"
        '            elif hasattr(layer.self_attn, "attn_mqa"):\n'
        "                # For DeepSeek model\n"
        "                attn_layer = layer.self_attn.attn_mqa\n"
        "        # For hybrid model\n"
        '        elif hasattr(layer, "attn"):\n'
        "            attn_layer = layer.attn\n"
        '        elif hasattr(layer, "linear_attn"):\n'
        '            if hasattr(layer.linear_attn, "attn"):\n'
        "                attn_layer = layer.linear_attn.attn\n"
        "            else:\n"
        "                attn_layer = layer.linear_attn\n"
        "        # For InternVL model\n"
        '        elif hasattr(layer, "attention"):\n'
        '            if hasattr(layer.attention, "attn"):\n'
        "                attn_layer = layer.attention.attn\n"
        "        # For NemotronH and similar hybrid models using 'mixer' attribute\n"
        '        elif hasattr(layer, "mixer"):\n'
        '            if hasattr(layer.mixer, "attn"):\n'
        "                attn_layer = layer.mixer.attn\n"
        '            elif hasattr(layer, "_forward_mamba"):\n'
        "                # Mamba layer with split op support - store the layer itself\n"
        "                attn_layer = layer\n"
        "\n"
        "        if attn_layer is not None:\n"
        "            model_runner_ref.attention_layers.append(attn_layer)\n"
        '        elif hasattr(layer, "mixer"):\n'
        "            model_runner_ref.attention_layers.append(None)\n"
        "\n"
        "        moe_block = None\n"
        "        moe_fusion = None\n"
        '        if hasattr(layer, "mlp") and hasattr(layer.mlp, "experts"):\n'
        "            moe_block = layer.mlp.experts\n"
        "            moe_fusion = layer.mlp\n"
        '        if hasattr(layer, "block_sparse_moe") and hasattr(\n'
        "            layer.block_sparse_moe, \"experts\"\n"
        "        ):\n"
        "            moe_block = layer.block_sparse_moe.experts\n"
        "            moe_fusion = layer.block_sparse_moe\n"
        '        if hasattr(layer, "moe") and hasattr(layer.moe, "experts"):\n'
        "            moe_block = layer.moe.experts\n"
        "            moe_fusion = layer.moe\n"
        "        # For NemotronH MoE layers using 'mixer' attribute\n"
        '        if hasattr(layer, "mixer") and hasattr(layer.mixer, "experts"):\n'
        "            moe_block = layer.mixer.experts\n"
        "            moe_fusion = layer.mixer\n"
        "        model_runner_ref.moe_layers.append(moe_block)\n"
        "        model_runner_ref.moe_fusions.append(moe_fusion)\n"
        "\n"
        "    if len(model_runner_ref.attention_layers) < model_config.num_hidden_layers:\n"
        "        # TODO(yuwei): support Non-Standard GQA\n"
        "        log_info_on_rank0(\n"
        "            logger,\n"
        '            "Disable piecewise CUDA graph because some layers do not apply Standard GQA",\n'
        "        )\n"
        "        return\n"
        "\n"
        "    tic = time.perf_counter()\n"
        "    before_mem = get_available_gpu_memory(device, gpu_id)\n"
        "    logger.info(\n"
        '        f"Capture piecewise CUDA graph begin. avail mem={before_mem:.2f} GB"\n'
        "    )\n"
        "\n"
        "    if server_args.enable_breakable_cuda_graph:\n"
        "        # Experimental feature\n"
        "        model_runner_ref.piecewise_cuda_graph_runner = BreakableCudaGraphRunner(model_runner_ref)\n"
        "    else:\n"
        "        model_runner_ref.piecewise_cuda_graph_runner = PiecewiseCudaGraphRunner(model_runner_ref)\n"
        "\n"
        "    after_mem = get_available_gpu_memory(device, gpu_id)\n"
        "    mem_usage = before_mem - after_mem\n"
        "    logger.info(\n"
        '        f"Capture piecewise CUDA graph end. Time elapsed: {time.perf_counter() - tic:.2f} s. "\n'
        '        f"mem usage={mem_usage:.2f} GB. avail mem={after_mem:.2f} GB."\n'
        "    )\n"
    )
    text = text.rstrip() + free_func
    dg.write_text(text)

    # ---- Update model_runner.py ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    old_method = (
        '    def init_piecewise_cuda_graphs(self):\n'
        '        """Initialize piecewise CUDA graph runner."""\n'
        "        self.piecewise_cuda_graph_runner = None\n"
        "\n"
        "        if self.server_args.disable_piecewise_cuda_graph:\n"
        "            logger.info(\n"
        '                "Disable piecewise CUDA graph because --disable-piecewise-cuda-graph is set"\n'
        "            )\n"
        "            return\n"
        "\n"
        "        # Draft models use decode CUDA graphs, not PCG\n"
        "        if self.is_draft_worker:\n"
        "            return\n"
        "\n"
        "        # Disable piecewise CUDA graph for non-language models\n"
        '        if not hasattr(self.model, "model"):\n'
        "            logger.warning(\n"
        '                "Disable piecewise CUDA graph because the model is not a language model"\n'
        "            )\n"
        "            return\n"
        "\n"
        "        # Disable piecewise CUDA graph for non capture size\n"
        "        if not self.server_args.piecewise_cuda_graph_tokens:\n"
        "            logger.warning(\n"
        '                "Disable piecewise CUDA graph because the capture size is not set"\n'
        "            )\n"
        "            return\n"
        "\n"
        "        # Collect attention layers and moe layers from the model\n"
        "        self.model.model = resolve_language_model(self.model)\n"
        '        language_model = getattr(self.model, "language_model", self.model)\n'
        "\n"
        "        # Resolve model with layers: handle CausalLM wrapper (.model.layers) and direct TextModel (.layers)\n"
        '        if hasattr(language_model, "model") and hasattr(language_model.model, "layers"):\n'
        "            layer_model = language_model.model\n"
        '        elif hasattr(language_model, "layers"):\n'
        "            layer_model = language_model\n"
        "        else:\n"
        "            logger.warning(\n"
        '                "Disable piecewise CUDA graph because the model does not have a \'layers\' attribute"\n'
        "            )\n"
        "            return\n"
        "\n"
        "        self.attention_layers = []\n"
        "        self.moe_layers = []\n"
        "        self.moe_fusions = []\n"
        "        for layer in layer_model.layers:\n"
        "            attn_layer = None\n"
        '            if hasattr(layer, "self_attn"):\n'
        '                if hasattr(layer.self_attn, "attn"):\n'
        "                    attn_layer = layer.self_attn.attn\n"
        '                elif hasattr(layer.self_attn, "attn_mqa"):\n'
        "                    # For DeepSeek model\n"
        "                    attn_layer = layer.self_attn.attn_mqa\n"
        "            # For hybrid model\n"
        '            elif hasattr(layer, "attn"):\n'
        "                attn_layer = layer.attn\n"
        '            elif hasattr(layer, "linear_attn"):\n'
        '                if hasattr(layer.linear_attn, "attn"):\n'
        "                    attn_layer = layer.linear_attn.attn\n"
        "                else:\n"
        "                    attn_layer = layer.linear_attn\n"
        "            # For InternVL model\n"
        '            elif hasattr(layer, "attention"):\n'
        '                if hasattr(layer.attention, "attn"):\n'
        "                    attn_layer = layer.attention.attn\n"
        "            # For NemotronH and similar hybrid models using 'mixer' attribute\n"
        '            elif hasattr(layer, "mixer"):\n'
        '                if hasattr(layer.mixer, "attn"):\n'
        "                    attn_layer = layer.mixer.attn\n"
        '                elif hasattr(layer, "_forward_mamba"):\n'
        "                    # Mamba layer with split op support - store the layer itself\n"
        "                    attn_layer = layer\n"
        "\n"
        "            if attn_layer is not None:\n"
        "                self.attention_layers.append(attn_layer)\n"
        '            elif hasattr(layer, "mixer"):\n'
        "                self.attention_layers.append(None)\n"
        "\n"
        "            moe_block = None\n"
        "            moe_fusion = None\n"
        '            if hasattr(layer, "mlp") and hasattr(layer.mlp, "experts"):\n'
        "                moe_block = layer.mlp.experts\n"
        "                moe_fusion = layer.mlp\n"
        '            if hasattr(layer, "block_sparse_moe") and hasattr(\n'
        "                layer.block_sparse_moe, \"experts\"\n"
        "            ):\n"
        "                moe_block = layer.block_sparse_moe.experts\n"
        "                moe_fusion = layer.block_sparse_moe\n"
        '            if hasattr(layer, "moe") and hasattr(layer.moe, "experts"):\n'
        "                moe_block = layer.moe.experts\n"
        "                moe_fusion = layer.moe\n"
        "            # For NemotronH MoE layers using 'mixer' attribute\n"
        '            if hasattr(layer, "mixer") and hasattr(layer.mixer, "experts"):\n'
        "                moe_block = layer.mixer.experts\n"
        "                moe_fusion = layer.mixer\n"
        "            self.moe_layers.append(moe_block)\n"
        "            self.moe_fusions.append(moe_fusion)\n"
        "\n"
        "        if len(self.attention_layers) < self.model_config.num_hidden_layers:\n"
        "            # TODO(yuwei): support Non-Standard GQA\n"
        "            log_info_on_rank0(\n"
        "                logger,\n"
        '                "Disable piecewise CUDA graph because some layers do not apply Standard GQA",\n'
        "            )\n"
        "            return\n"
        "\n"
        "        tic = time.perf_counter()\n"
        "        before_mem = get_available_gpu_memory(self.device, self.gpu_id)\n"
        "        logger.info(\n"
        '            f"Capture piecewise CUDA graph begin. avail mem={before_mem:.2f} GB"\n'
        "        )\n"
        "\n"
        "        if self.server_args.enable_breakable_cuda_graph:\n"
        "            # Experimental feature\n"
        "            self.piecewise_cuda_graph_runner = BreakableCudaGraphRunner(self)\n"
        "        else:\n"
        "            self.piecewise_cuda_graph_runner = PiecewiseCudaGraphRunner(self)\n"
        "\n"
        "        after_mem = get_available_gpu_memory(self.device, self.gpu_id)\n"
        "        mem_usage = before_mem - after_mem\n"
        "        logger.info(\n"
        '            f"Capture piecewise CUDA graph end. Time elapsed: {time.perf_counter() - tic:.2f} s. "\n'
        '            f"mem usage={mem_usage:.2f} GB. avail mem={after_mem:.2f} GB."\n'
        "        )\n"
    )
    assert old_method in text, "init_piecewise_cuda_graphs method not found"

    new_delegate = (
        "    def init_piecewise_cuda_graphs(self):\n"
        "        _init_piecewise_cuda_graphs_impl(\n"
        "            model_runner_ref=self,\n"
        "            server_args=self.server_args,\n"
        "            device=self.device,\n"
        "            gpu_id=self.gpu_id,\n"
        "            is_draft_worker=self.is_draft_worker,\n"
        "            model=self.model,\n"
        "            model_config=self.model_config,\n"
        "        )\n"
    )
    text = text.replace(old_method, new_delegate)

    # Extend the device_graphs import to also pull in init_piecewise_cuda_graphs.
    old_import = (
        "from sglang.srt.model_executor.device_graphs import (\n"
        "    init_device_graphs as _init_device_graphs_impl,\n"
        ")\n"
    )
    new_import = (
        "from sglang.srt.model_executor.device_graphs import (\n"
        "    init_device_graphs as _init_device_graphs_impl,\n"
        "    init_piecewise_cuda_graphs as _init_piecewise_cuda_graphs_impl,\n"
        ")\n"
    )
    assert old_import in text, "device_graphs import block not found"
    text = text.replace(old_import, new_import)

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
