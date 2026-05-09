#!/usr/bin/env python3
"""Reproducible transform: extract `kernel_warmup` and `_flashinfer_autotune`
from `ModelRunner` to free functions in
`sglang.srt.model_executor.kernel_warmup`.

Strict-minimal mechanical extraction:
  - Free function bodies are byte-identical to the original method bodies, with
    `self.X` reads replaced by explicit kwargs and the only side-effect call
    `self._dummy_run(...)` replaced by a `dummy_run_callable(...)` Callable
    kwarg (R4 compliance).
  - `_should_run_flashinfer_autotune` / `_flashinfer_autotune_cache_path` are
    already free functions (extracted in /36); we call them directly.
  - The original methods on `ModelRunner` become 1-line delegates.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/36"
TARGET_COMMIT = "tom_refactor/37"


def transform(dir_root: Path) -> None:
    kw = dir_root / "python/sglang/srt/model_executor/kernel_warmup.py"
    text = kw.read_text()

    # Add Callable + logging imports needed for the new functions.
    text = text.replace(
        "from typing import Optional\n",
        "import logging\n"
        "from typing import Callable, Optional\n",
    )
    text = text.replace(
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n",
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n"
        "\n"
        "logger = logging.getLogger(__name__)\n",
    )

    # Append the two new functions at the end.
    new_funcs = (
        "\n\n"
        "def kernel_warmup(\n"
        "    *,\n"
        "    device: str,\n"
        "    server_args: ServerArgs,\n"
        "    spec_algorithm: SpeculativeAlgorithm,\n"
        "    is_draft_worker: bool,\n"
        "    model_config: ModelConfig,\n"
        "    dtype: torch.dtype,\n"
        "    forward_stream: torch.cuda.Stream,\n"
        "    req_to_token_pool_size: int,\n"
        "    tp_rank: int,\n"
        "    tp_size: int,\n"
        "    pp_rank: int,\n"
        "    pp_size: int,\n"
        "    dp_rank: Optional[int],\n"
        "    dp_size: int,\n"
        "    moe_ep_size: int,\n"
        "    dummy_run_callable: Callable[..., None],\n"
        ") -> None:\n"
        '    """\n'
        "    Warmup and tune kernels before cuda graph capture.\n"
        "    Currently only doing FlashInfer autotune.\n"
        '    """\n'
        '    if device != "cuda":\n'
        "        return\n"
        "\n"
        "    if _should_run_flashinfer_autotune(\n"
        "        server_args=server_args,\n"
        "        spec_algorithm=spec_algorithm,\n"
        "        is_draft_worker=is_draft_worker,\n"
        "    ):\n"
        "        _flashinfer_autotune(\n"
        "            server_args=server_args,\n"
        "            model_config=model_config,\n"
        "            dtype=dtype,\n"
        "            device=device,\n"
        "            forward_stream=forward_stream,\n"
        "            req_to_token_pool_size=req_to_token_pool_size,\n"
        "            tp_rank=tp_rank,\n"
        "            tp_size=tp_size,\n"
        "            pp_rank=pp_rank,\n"
        "            pp_size=pp_size,\n"
        "            dp_rank=dp_rank,\n"
        "            dp_size=dp_size,\n"
        "            moe_ep_size=moe_ep_size,\n"
        "            dummy_run_callable=dummy_run_callable,\n"
        "        )\n"
        "\n"
        "\n"
        "def _flashinfer_autotune(\n"
        "    *,\n"
        "    server_args: ServerArgs,\n"
        "    model_config: ModelConfig,\n"
        "    dtype: torch.dtype,\n"
        "    device: str,\n"
        "    forward_stream: torch.cuda.Stream,\n"
        "    req_to_token_pool_size: int,\n"
        "    tp_rank: int,\n"
        "    tp_size: int,\n"
        "    pp_rank: int,\n"
        "    pp_size: int,\n"
        "    dp_rank: Optional[int],\n"
        "    dp_size: int,\n"
        "    moe_ep_size: int,\n"
        "    dummy_run_callable: Callable[..., None],\n"
        ") -> None:\n"
        '    """Run flashinfer autotune."""\n'
        "    from flashinfer.autotuner import autotune\n"
        "\n"
        "    cache_path = _flashinfer_autotune_cache_path(\n"
        "        server_args=server_args,\n"
        "        model_config=model_config,\n"
        "        dtype=dtype,\n"
        "        device=device,\n"
        "        tp_rank=tp_rank,\n"
        "        tp_size=tp_size,\n"
        "        pp_rank=pp_rank,\n"
        "        pp_size=pp_size,\n"
        "        dp_rank=dp_rank,\n"
        "        dp_size=dp_size,\n"
        "        moe_ep_size=moe_ep_size,\n"
        "    )\n"
        '    logger.info("Running FlashInfer autotune with cache: %s", cache_path)\n'
        "\n"
        "    # Run warmup on the non-default stream to avoid NCCL 2.29+ cudaMemcpyBatchAsync\n"
        "    # calls on default stream (unsupported by CUDA) when --enable-symm-mem is used.\n"
        "    forward_stream.wait_stream(torch.cuda.current_stream())\n"
        "    with torch.get_device_module(device).stream(forward_stream):\n"
        "        with torch.inference_mode(), autotune(True, cache=str(cache_path)):\n"
        "            dummy_run_callable(batch_size=req_to_token_pool_size)\n"
        "    torch.cuda.current_stream().wait_stream(forward_stream)\n"
        '    logger.info("FlashInfer autotune completed.")\n'
    )
    text = text.rstrip() + new_funcs
    kw.write_text(text)

    # ---- Update model_runner.py ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Replace kernel_warmup body with a 1-line delegate.
    old_kernel_warmup = (
        "    def kernel_warmup(self):\n"
        '        """\n'
        "        Warmup and tune kernels before cuda graph capture.\n"
        "        Currently only doing FlashInfer autotune.\n"
        '        """\n'
        '        if self.device != "cuda":\n'
        "            return\n"
        "\n"
        "        if self._should_run_flashinfer_autotune():\n"
        "            self._flashinfer_autotune()\n"
    )
    new_kernel_warmup = (
        "    def kernel_warmup(self):\n"
        "        kernel_warmup(\n"
        "            device=self.device,\n"
        "            server_args=self.server_args,\n"
        "            spec_algorithm=self.spec_algorithm,\n"
        "            is_draft_worker=self.is_draft_worker,\n"
        "            model_config=self.model_config,\n"
        "            dtype=self.dtype,\n"
        "            forward_stream=self.forward_stream,\n"
        "            req_to_token_pool_size=self.req_to_token_pool.size,\n"
        "            tp_rank=self.tp_rank,\n"
        "            tp_size=self.tp_size,\n"
        "            pp_rank=self.pp_rank,\n"
        "            pp_size=self.pp_size,\n"
        "            dp_rank=self.dp_rank,\n"
        "            dp_size=self.dp_size,\n"
        "            moe_ep_size=self.moe_ep_size,\n"
        "            dummy_run_callable=self._dummy_run,\n"
        "        )\n"
    )
    assert old_kernel_warmup in text, "kernel_warmup method body not found"
    text = text.replace(old_kernel_warmup, new_kernel_warmup)

    # Replace _flashinfer_autotune body with a 1-line delegate.
    old_flashinfer_autotune = (
        "    def _flashinfer_autotune(self):\n"
        '        """Run flashinfer autotune."""\n'
        "        from flashinfer.autotuner import autotune\n"
        "\n"
        "        cache_path = self._flashinfer_autotune_cache_path()\n"
        '        logger.info("Running FlashInfer autotune with cache: %s", cache_path)\n'
        "\n"
        "        # Run warmup on the non-default stream to avoid NCCL 2.29+ cudaMemcpyBatchAsync\n"
        "        # calls on default stream (unsupported by CUDA) when --enable-symm-mem is used.\n"
        "        self.forward_stream.wait_stream(torch.cuda.current_stream())\n"
        "        with torch.get_device_module(self.device).stream(self.forward_stream):\n"
        "            with torch.inference_mode(), autotune(True, cache=str(cache_path)):\n"
        "                self._dummy_run(batch_size=self.req_to_token_pool.size)\n"
        "        torch.cuda.current_stream().wait_stream(self.forward_stream)\n"
        '        logger.info("FlashInfer autotune completed.")\n'
    )
    new_flashinfer_autotune = (
        "    def _flashinfer_autotune(self):\n"
        "        _flashinfer_autotune(\n"
        "            server_args=self.server_args,\n"
        "            model_config=self.model_config,\n"
        "            dtype=self.dtype,\n"
        "            device=self.device,\n"
        "            forward_stream=self.forward_stream,\n"
        "            req_to_token_pool_size=self.req_to_token_pool.size,\n"
        "            tp_rank=self.tp_rank,\n"
        "            tp_size=self.tp_size,\n"
        "            pp_rank=self.pp_rank,\n"
        "            pp_size=self.pp_size,\n"
        "            dp_rank=self.dp_rank,\n"
        "            dp_size=self.dp_size,\n"
        "            moe_ep_size=self.moe_ep_size,\n"
        "            dummy_run_callable=self._dummy_run,\n"
        "        )\n"
    )
    assert old_flashinfer_autotune in text, "_flashinfer_autotune method body not found"
    text = text.replace(old_flashinfer_autotune, new_flashinfer_autotune)

    # Extend the kernel_warmup import to also pull in the two new helpers.
    old_import = (
        "from sglang.srt.model_executor.kernel_warmup import (\n"
        "    _flashinfer_autotune_cache_path as _flashinfer_autotune_cache_path_impl,\n"
        "    _should_run_flashinfer_autotune as _should_run_flashinfer_autotune_impl,\n"
        ")\n"
    )
    new_import = (
        "from sglang.srt.model_executor.kernel_warmup import (\n"
        "    _flashinfer_autotune as _flashinfer_autotune_impl,\n"
        "    _flashinfer_autotune_cache_path as _flashinfer_autotune_cache_path_impl,\n"
        "    _should_run_flashinfer_autotune as _should_run_flashinfer_autotune_impl,\n"
        "    kernel_warmup as _kernel_warmup_impl,\n"
        ")\n"
    )
    assert old_import in text, "kernel_warmup import block not found"
    text = text.replace(old_import, new_import)

    # Rebind delegate calls to the aliases (method names shadow imports).
    text = text.replace(
        "        kernel_warmup(\n",
        "        _kernel_warmup_impl(\n",
    )
    text = text.replace(
        "        _flashinfer_autotune(\n",
        "        _flashinfer_autotune_impl(\n",
    )

    mr.write_text(text)

    git_add_and_commit(
        "Extract kernel_warmup and _flashinfer_autotune to free functions",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
