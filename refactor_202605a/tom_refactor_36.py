#!/usr/bin/env python3
"""Reproducible transform: extract leaf helpers `_should_run_flashinfer_autotune`
and `_flashinfer_autotune_cache_path` from `ModelRunner` to free functions in
`sglang.srt.model_executor.kernel_warmup`.

Strict-minimal mechanical extraction:
  - Free function bodies are byte-identical to the original method bodies, with
    `self.X` reads replaced by explicit kwargs.
  - The original methods on `ModelRunner` become 1-line delegates.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/35"
TARGET_COMMIT = "tom_refactor/36"


def transform(dir_root: Path) -> None:
    kw = dir_root / "python/sglang/srt/model_executor/kernel_warmup.py"
    kw_content = (
        "from __future__ import annotations\n"
        "\n"
        "import hashlib\n"
        "from pathlib import Path\n"
        "from typing import Optional\n"
        "\n"
        "import torch\n"
        "\n"
        "from sglang.srt.configs.model_config import ModelConfig\n"
        "from sglang.srt.environ import envs\n"
        "from sglang.srt.server_args import ServerArgs\n"
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n"
        "\n"
        "\n"
        "def _should_run_flashinfer_autotune(\n"
        "    *,\n"
        "    server_args: ServerArgs,\n"
        "    spec_algorithm: SpeculativeAlgorithm,\n"
        "    is_draft_worker: bool,\n"
        ") -> bool:\n"
        '    """Check if flashinfer autotune should be run."""\n'
        "    if server_args.disable_flashinfer_autotune:\n"
        "        return False\n"
        "\n"
        "    # CuteDSL v1 (cutedsl runner + deepep a2a) bypasses MoeRunner and must not\n"
        "    # be autotuned -- its _dummy_run would dispatch more tokens per rank than\n"
        "    # SGLANG_DEEPEP_NUM_MAX_DISPATCH_TOKENS_PER_RANK, tripping a DeepEP assert.\n"
        "    # Read server_args directly to avoid depending on initialize_moe_config()\n"
        "    # having already populated the MoE backend globals.\n"
        "    if (\n"
        '        server_args.moe_runner_backend == "flashinfer_cutedsl"\n'
        '        and server_args.moe_a2a_backend == "deepep"\n'
        "    ):\n"
        "        return False\n"
        "\n"
        "    backend_str = server_args.moe_runner_backend\n"
        "\n"
        "    # TODO smor- support other cases for flashinfer autotune, such as, mamba backend\n"
        "\n"
        "    if backend_str not in [\n"
        '        "flashinfer_trtllm",\n'
        "        # TODO: Enable for flashinfer_trtllm_routed once https://github.com/flashinfer-ai/flashinfer/issues/2749 is fixed.\n"
        '        # "flashinfer_trtllm_routed",\n'
        '        "flashinfer_mxfp4",\n'
        '        "flashinfer_cutedsl",\n'
        "        # TODO: flashinfer_cutlass will cause some flashinfer compilation errors. To be fixed.\n"
        '        # "flashinfer_cutlass",\n'
        "    ]:\n"
        "        return False\n"
        "\n"
        "    major, _ = torch.cuda.get_device_capability()\n"
        "    if major < 9:\n"
        "        return False\n"
        "\n"
        "    if spec_algorithm.is_speculative():\n"
        "        return not is_draft_worker\n"
        "\n"
        "    return True\n"
        "\n"
        "\n"
        "def _flashinfer_autotune_cache_path(\n"
        "    *,\n"
        "    server_args: ServerArgs,\n"
        "    model_config: ModelConfig,\n"
        "    dtype: torch.dtype,\n"
        "    device: str,\n"
        "    tp_rank: int,\n"
        "    tp_size: int,\n"
        "    pp_rank: int,\n"
        "    pp_size: int,\n"
        "    dp_rank: Optional[int],\n"
        "    dp_size: int,\n"
        "    moe_ep_size: int,\n"
        ") -> Path:\n"
        "    import flashinfer\n"
        "\n"
        "    major, minor = torch.cuda.get_device_capability(device)\n"
        '    arch = f"sm{major}{minor}"\n'
        '    flashinfer_version = getattr(flashinfer, "__version__", "unknown")\n'
        "\n"
        '    model_key = "|".join(\n'
        "        [\n"
        "            str(server_args.model_path),\n"
        "            str(dtype),\n"
        "            str(server_args.quantization),\n"
        "            str(server_args.moe_runner_backend),\n"
        "            str(tp_size),\n"
        "            str(pp_size),\n"
        "            str(dp_size),\n"
        "            str(moe_ep_size),\n"
        "            str(model_config.hf_config.__class__.__name__),\n"
        "        ]\n"
        "    )\n"
        "    cache_key = hashlib.sha256(model_key.encode()).hexdigest()[:16]\n"
        "    cache_dir = (\n"
        "        Path(envs.SGLANG_CACHE_DIR.get())\n"
        '        / "flashinfer"\n'
        '        / "autotune"\n'
        "        / flashinfer_version\n"
        "        / arch\n"
        "        / cache_key\n"
        "    )\n"
        "    cache_dir.mkdir(parents=True, exist_ok=True)\n"
        "    return (\n"
        "        cache_dir\n"
        '        / f"rank_tp{tp_rank}_pp{pp_rank}_dp{dp_rank or 0}.json"\n'
        "    )\n"
    )
    kw.write_text(kw_content)

    # ---- Update model_runner.py ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Replace _should_run_flashinfer_autotune body with a 1-line delegate.
    old_should_run = (
        "    def _should_run_flashinfer_autotune(self) -> bool:\n"
        '        """Check if flashinfer autotune should be run."""\n'
        "        if self.server_args.disable_flashinfer_autotune:\n"
        "            return False\n"
        "\n"
        "        # CuteDSL v1 (cutedsl runner + deepep a2a) bypasses MoeRunner and must not\n"
        "        # be autotuned -- its _dummy_run would dispatch more tokens per rank than\n"
        "        # SGLANG_DEEPEP_NUM_MAX_DISPATCH_TOKENS_PER_RANK, tripping a DeepEP assert.\n"
        "        # Read server_args directly to avoid depending on initialize_moe_config()\n"
        "        # having already populated the MoE backend globals.\n"
        "        if (\n"
        '            self.server_args.moe_runner_backend == "flashinfer_cutedsl"\n'
        '            and self.server_args.moe_a2a_backend == "deepep"\n'
        "        ):\n"
        "            return False\n"
        "\n"
        "        backend_str = self.server_args.moe_runner_backend\n"
        "\n"
        "        # TODO smor- support other cases for flashinfer autotune, such as, mamba backend\n"
        "\n"
        "        if backend_str not in [\n"
        '            "flashinfer_trtllm",\n'
        "            # TODO: Enable for flashinfer_trtllm_routed once https://github.com/flashinfer-ai/flashinfer/issues/2749 is fixed.\n"
        '            # "flashinfer_trtllm_routed",\n'
        '            "flashinfer_mxfp4",\n'
        '            "flashinfer_cutedsl",\n'
        "            # TODO: flashinfer_cutlass will cause some flashinfer compilation errors. To be fixed.\n"
        '            # "flashinfer_cutlass",\n'
        "        ]:\n"
        "            return False\n"
        "\n"
        "        major, _ = torch.cuda.get_device_capability()\n"
        "        if major < 9:\n"
        "            return False\n"
        "\n"
        "        if self.spec_algorithm.is_speculative():\n"
        "            return not self.is_draft_worker\n"
        "\n"
        "        return True\n"
    )
    new_should_run = (
        "    def _should_run_flashinfer_autotune(self) -> bool:\n"
        "        return _should_run_flashinfer_autotune(\n"
        "            server_args=self.server_args,\n"
        "            spec_algorithm=self.spec_algorithm,\n"
        "            is_draft_worker=self.is_draft_worker,\n"
        "        )\n"
    )
    assert old_should_run in text, "_should_run_flashinfer_autotune body not found"
    text = text.replace(old_should_run, new_should_run)

    # Replace _flashinfer_autotune_cache_path body with a 1-line delegate.
    old_cache_path = (
        "    def _flashinfer_autotune_cache_path(self) -> Path:\n"
        "        import flashinfer\n"
        "\n"
        "        major, minor = torch.cuda.get_device_capability(self.device)\n"
        '        arch = f"sm{major}{minor}"\n'
        '        flashinfer_version = getattr(flashinfer, "__version__", "unknown")\n'
        "\n"
        "        server_args = self.server_args\n"
        '        model_key = "|".join(\n'
        "            [\n"
        "                str(server_args.model_path),\n"
        "                str(self.dtype),\n"
        "                str(server_args.quantization),\n"
        "                str(server_args.moe_runner_backend),\n"
        "                str(self.tp_size),\n"
        "                str(self.pp_size),\n"
        "                str(self.dp_size),\n"
        "                str(self.moe_ep_size),\n"
        "                str(self.model_config.hf_config.__class__.__name__),\n"
        "            ]\n"
        "        )\n"
        "        cache_key = hashlib.sha256(model_key.encode()).hexdigest()[:16]\n"
        "        cache_dir = (\n"
        "            Path(envs.SGLANG_CACHE_DIR.get())\n"
        '            / "flashinfer"\n'
        '            / "autotune"\n'
        "            / flashinfer_version\n"
        "            / arch\n"
        "            / cache_key\n"
        "        )\n"
        "        cache_dir.mkdir(parents=True, exist_ok=True)\n"
        "        return (\n"
        "            cache_dir\n"
        '            / f"rank_tp{self.tp_rank}_pp{self.pp_rank}_dp{self.dp_rank or 0}.json"\n'
        "        )\n"
    )
    new_cache_path = (
        "    def _flashinfer_autotune_cache_path(self) -> Path:\n"
        "        return _flashinfer_autotune_cache_path(\n"
        "            server_args=self.server_args,\n"
        "            model_config=self.model_config,\n"
        "            dtype=self.dtype,\n"
        "            device=self.device,\n"
        "            tp_rank=self.tp_rank,\n"
        "            tp_size=self.tp_size,\n"
        "            pp_rank=self.pp_rank,\n"
        "            pp_size=self.pp_size,\n"
        "            dp_rank=self.dp_rank,\n"
        "            dp_size=self.dp_size,\n"
        "            moe_ep_size=self.moe_ep_size,\n"
        "        )\n"
    )
    assert old_cache_path in text, "_flashinfer_autotune_cache_path body not found"
    text = text.replace(old_cache_path, new_cache_path)

    # Add imports for the free helpers (private names; rebind locally).
    # Anchor on a stable existing model_executor import.
    old_import = (
        "from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner\n"
    )
    new_import = (
        "from sglang.srt.model_executor.cuda_graph_runner import CudaGraphRunner\n"
        "from sglang.srt.model_executor.kernel_warmup import (\n"
        "    _flashinfer_autotune_cache_path as _flashinfer_autotune_cache_path_impl,\n"
        "    _should_run_flashinfer_autotune as _should_run_flashinfer_autotune_impl,\n"
        ")\n"
    )
    assert old_import in text, "CudaGraphRunner import not found"
    text = text.replace(old_import, new_import)

    # Rebind delegate calls to the aliases (the method names shadow the imports).
    text = text.replace(
        "        return _should_run_flashinfer_autotune(\n",
        "        return _should_run_flashinfer_autotune_impl(\n",
    )
    text = text.replace(
        "        return _flashinfer_autotune_cache_path(\n",
        "        return _flashinfer_autotune_cache_path_impl(\n",
    )

    mr.write_text(text)

    git_add_and_commit(
        "Extract _should_run_flashinfer_autotune and _flashinfer_autotune_cache_path to free functions",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
