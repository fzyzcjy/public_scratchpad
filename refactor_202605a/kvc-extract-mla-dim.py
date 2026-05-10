#!/usr/bin/env python3
"""Extract `ModelRunnerKVCacheMixin.calculate_mla_kv_cache_dim` to a free
function in new file `python/sglang/srt/mem_cache/kv_cache_dim.py`.

Per ch3.2 spec — narrow kwargs (`model_config`, `kv_cache_dtype`,
`server_args`), independently reusable, no configurator state.

Two internal callers in the mixin (`init_memory_pool` /
`_apply_memory_pool_config` paths) switch from
``self.calculate_mla_kv_cache_dim()`` to module-qualified
``kv_cache_dim.calculate_mla_kv_cache_dim(...)``. Mixin keeps the method
for now (deletion happens in `kvc-migrate-method-bodies` along with the
other mixin methods).

Usage:
    uv run --python 3.12 kvc-extract-mla-dim.py run
    uv run --python 3.12 kvc-extract-mla-dim.py verify
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

ID = "kvc-extract-mla-dim"
SUBJECT = "Extract calculate_mla_kv_cache_dim to free function in mem_cache.kv_cache_dim"
BODY = ""
AREA = "nonmech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_KV_CACHE_DIM_BODY = '''\
from __future__ import annotations

import torch

from sglang.srt.configs.model_config import ModelConfig, is_deepseek_nsa
from sglang.srt.mem_cache.memory_pool import NSATokenToKVPool
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils.common import is_hip

_is_hip = is_hip()


def calculate_mla_kv_cache_dim(
    *,
    model_config: ModelConfig,
    kv_cache_dtype: torch.dtype,
    server_args: ServerArgs,
) -> int:
    is_nsa_model = is_deepseek_nsa(model_config.hf_config)
    kv_lora_rank = model_config.kv_lora_rank
    qk_rope_head_dim = model_config.qk_rope_head_dim
    kv_cache_dim = kv_lora_rank + qk_rope_head_dim  # default mla kv cache dim

    # For non-NSA models, MLA kv cache dim is simply kv_lora_rank + qk_rope_head_dim
    if not is_nsa_model:
        return kv_cache_dim

    # TRTLLM backend does not override kv_cache_dim for MLA kv cache
    # Assuming nsa prefill and decode backends are the same when using trtllm MLA backend,
    # since it is not compatible for trtllm and other mla attn backend due to the different
    # kv cache layout.
    if (
        server_args.nsa_prefill_backend == "trtllm"
        or server_args.nsa_decode_backend == "trtllm"
    ):
        return kv_cache_dim

    # On HIP with TileLang backend, keep the default MLA KV cache dimension.
    # FP8 attention uses the nope(512 fp8) + rope(64 fp8) layout, without extra per-block scales.
    if _is_hip and (
        server_args.nsa_prefill_backend == "tilelang"
        or server_args.nsa_decode_backend == "tilelang"
    ):
        return kv_cache_dim

    quant_block_size = NSATokenToKVPool.quant_block_size
    rope_storage_dtype = NSATokenToKVPool.rope_storage_dtype
    # Calculate override_kv_cache_dim for FP8 storage in backends that use scaled KV layout (excluding TRTLLM and HIP+TileLang).
    # kv_lora_rank + scale storage (kv_lora_rank // quant_block_size * 4 bytes) + rope dimension storage
    # Note: rope dimension is stored in original dtype (bf16), not quantized to fp8
    if kv_cache_dtype == torch.float8_e4m3fn:
        assert (
            kv_lora_rank % quant_block_size == 0
        ), f"kv_lora_rank {kv_lora_rank} must be multiple of quant_block_size {quant_block_size}"

        return (
            kv_lora_rank
            + kv_lora_rank // quant_block_size * 4
            + qk_rope_head_dim * rope_storage_dtype.itemsize
        )

    return kv_cache_dim
'''


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py"
    target = wt / "python/sglang/srt/mem_cache/kv_cache_dim.py"

    # 1) Write the new free function module.
    target.write_text(_KV_CACHE_DIM_BODY)

    # 2) Wire up the mixin's two internal callers — module-qualified per
    # ch3.2 spec.
    text = mixin.read_text()
    if "from sglang.srt.mem_cache import kv_cache_dim\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.environ import envs\n",
            addition="from sglang.srt.mem_cache import kv_cache_dim\n",
        )
    text = replace_call_site(
        text,
        old="                    kv_cache_dim=self.calculate_mla_kv_cache_dim(),\n",
        new=(
            "                    kv_cache_dim=kv_cache_dim.calculate_mla_kv_cache_dim(\n"
            "                        model_config=self.model_config,\n"
            "                        kv_cache_dtype=self.kv_cache_dtype,\n"
            "                        server_args=self.server_args,\n"
            "                    ),\n"
        ),
    )
    text = replace_call_site(
        text,
        old="                kv_cache_dim=self.calculate_mla_kv_cache_dim(),\n",
        new=(
            "                kv_cache_dim=kv_cache_dim.calculate_mla_kv_cache_dim(\n"
            "                    model_config=self.model_config,\n"
            "                    kv_cache_dtype=self.kv_cache_dtype,\n"
            "                    server_args=self.server_args,\n"
            "                ),\n"
        ),
    )
    mixin.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
