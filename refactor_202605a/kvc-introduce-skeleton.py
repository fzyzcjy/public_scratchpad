#!/usr/bin/env python3
"""Introduce KVCacheConfigurator + KVCacheConfigResult skeletons in
`python/sglang/srt/mem_cache/kv_cache_configurator.py`. Both are
``@dataclass(frozen=True, slots=True, kw_only=True)`` per ch3.2 + the
sprint-wide dataclass default.

`configure()` body is a single ``raise NotImplementedError`` placeholder;
method bodies migrate in the next commit (`kvc-migrate-method-bodies`).

ModelRunner.initialize() picks up a 27-kwarg constructor call assigning
``self.kv_cache_configurator = KVCacheConfigurator(...)`` immediately
above the still-existing ``self.init_memory_pool(pre_model_load_memory)``
line. Mixin inheritance and the ``init_memory_pool`` delegate stay in
place — they are dropped in `kvc-drop-mixin-inheritance`.

Usage:
    uv run --python 3.12 kvc-introduce-skeleton.py run
    uv run --python 3.12 kvc-introduce-skeleton.py verify
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
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "kvc-introduce-skeleton"
SUBJECT = "Introduce KVCacheConfigurator + KVCacheConfigResult skeletons"
BODY = ""
AREA = "nonmech_model_runner"
BASE = "tom_refactor_202605a/primary/nonmech_model_runner/kvc-extract-mla-dim"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_CONFIGURATOR_BODY = '''\
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

import torch

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.mem_cache.allocator import BaseTokenToKVPoolAllocator
from sglang.srt.mem_cache.memory_pool import KVCache, ReqToTokenPool
from sglang.srt.server_args import ServerArgs
from sglang.srt.speculative.spec_info import SpeculativeAlgorithm

if TYPE_CHECKING:
    from sglang.srt.model_executor.pool_configurator import MemoryPoolConfig


@dataclass(frozen=True, slots=True, kw_only=True)
class KVCacheConfigResult:
    """Configurator output — caller writes back to ModelRunner fields."""

    max_total_num_tokens: int
    max_running_requests: int
    full_max_total_num_tokens: Optional[int]
    swa_max_total_num_tokens: Optional[int]
    req_to_token_pool: ReqToTokenPool
    token_to_kv_pool: KVCache
    token_to_kv_pool_allocator: BaseTokenToKVPoolAllocator
    memory_pool_config: "MemoryPoolConfig"


@dataclass(frozen=True, slots=True, kw_only=True)
class KVCacheConfigurator:
    """KV cache pipeline (profile -> resolve -> constrain -> init pools).

    Replaces ``ModelRunnerKVCacheMixin`` via composition. ``frozen=True``
    blocks any stale ``self.X = Y`` writes left over from the mixin
    migration; ``slots=True`` blocks attribute typos at runtime;
    ``kw_only=True`` forces named-kwargs construction at the caller.

    Pipeline intermediate state (profiled bytes / resolved configs / pool
    objects) flows through local variables + return values, not via
    attribute writes on ``self``.
    """

    # 部署 env
    device: str
    gpu_id: int
    mem_fraction_static: float
    page_size: int
    # 并行 rank / size
    tp_rank: int
    tp_size: int
    pp_size: int
    dp_size: int
    attention_tp_size: int
    # 模型 / dtype
    model_config: ModelConfig
    server_args: ServerArgs
    dtype: torch.dtype
    kv_cache_dtype: torch.dtype
    # 推测
    spec_algorithm: SpeculativeAlgorithm
    is_draft_worker: bool
    # 架构 flag
    is_hybrid_swa: bool
    is_hybrid_swa_compress: bool
    use_mla_backend: bool
    enable_hisparse: bool
    mambaish_config: Optional[Any]
    hybrid_gdn_config: Optional[Any]
    # PP 切片
    start_layer: int
    end_layer: int
    num_effective_layers: int
    # 可选预注入（draft worker 复用 target 的 pool）
    req_to_token_pool: Optional[ReqToTokenPool]
    token_to_kv_pool_allocator: Optional[BaseTokenToKVPoolAllocator]
    # draft worker 预算
    memory_pool_config: Optional["MemoryPoolConfig"]

    def configure(self, *, pre_model_load_memory: int) -> KVCacheConfigResult:
        raise NotImplementedError("populated in kvc-migrate-method-bodies")
'''


# Constructor block inserted in ModelRunner.initialize() above the
# init_memory_pool call. 27 kwargs per ch3.2.
_CTOR_INSERT = '''\
        self.kv_cache_configurator = KVCacheConfigurator(
            device=self.device,
            gpu_id=self.gpu_id,
            mem_fraction_static=self.mem_fraction_static,
            page_size=self.page_size,
            tp_rank=self.tp_rank,
            tp_size=self.tp_size,
            pp_size=self.pp_size,
            dp_size=self.dp_size,
            attention_tp_size=get_attention_tp_size(),
            model_config=self.model_config,
            server_args=self.server_args,
            dtype=self.dtype,
            kv_cache_dtype=self.kv_cache_dtype,
            spec_algorithm=self.spec_algorithm,
            is_draft_worker=self.is_draft_worker,
            is_hybrid_swa=self.is_hybrid_swa,
            is_hybrid_swa_compress=self.is_hybrid_swa_compress,
            use_mla_backend=self.use_mla_backend,
            enable_hisparse=self.enable_hisparse,
            mambaish_config=mambaish_config(
                self.model_config, is_draft_worker=self.is_draft_worker
            ),
            hybrid_gdn_config=hybrid_gdn_config(self.model_config),
            start_layer=self.start_layer,
            end_layer=self.end_layer,
            num_effective_layers=self.num_effective_layers,
            req_to_token_pool=self.req_to_token_pool,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            memory_pool_config=self.memory_pool_config,
        )

'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    target = wt / "python/sglang/srt/mem_cache/kv_cache_configurator.py"

    # 1) Write the new module.
    target.write_text(_CONFIGURATOR_BODY)

    # 2) Wire imports + ctor block in ModelRunner.initialize.
    text = mr.read_text()
    if "from sglang.srt.mem_cache.kv_cache_configurator import" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.mem_cache.memory_pool import ReqToTokenPool\n",
            addition=(
                "from sglang.srt.mem_cache.kv_cache_configurator import (\n"
                "    KVCacheConfigurator,\n"
                ")\n"
            ),
        )
    if "from sglang.srt.configs.hybrid_arch import" not in text:
        # `mambaish_config` and `hybrid_gdn_config` are needed at the ctor
        # site. After `drop-hybrid-arch-delegates` (which removed the module
        # import), model_runner.py has no remaining hybrid_arch import — add
        # a fresh from-import. isort will normalize the position.
        text = insert_after(
            text,
            anchor="from sglang.srt.configs.device_config import DeviceConfig\n",
            addition=(
                "from sglang.srt.configs.hybrid_arch import (\n"
                "    hybrid_gdn_config,\n"
                "    mambaish_config,\n"
                ")\n"
            ),
        )

    text = replace_call_site(
        text,
        old=(
            "        # Init memory pool and attention backends\n"
            "        self.init_memory_pool(pre_model_load_memory)\n"
        ),
        new=(
            "        # Init memory pool and attention backends\n"
            f"{_CTOR_INSERT}"
            "        self.init_memory_pool(pre_model_load_memory)\n"
        ),
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
