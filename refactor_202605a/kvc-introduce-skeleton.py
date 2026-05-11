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
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/move-step-span-name"
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
    from sglang.srt.model_executor.model_runner_components.pool_configurator import MemoryPoolConfig


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

    # deployment env (runtime, not in server_args)
    device: str
    gpu_id: int
    # model / dtype (resolved objects, not in server_args)
    model_config: ModelConfig
    server_args: ServerArgs
    kv_cache_dtype: torch.dtype
    # speculative decoding (runtime / derived, not in server_args)
    spec_algorithm: SpeculativeAlgorithm
    is_draft_worker: bool
    # DFLASH-only: target's `cell_size` is scaled to include draft KV cache.
    # ``pool_configurator.DefaultPoolConfigurator`` reads this off the
    # configurator (was ``getattr(mr, "dflash_draft_num_layers", None)`` in
    # the mixin era — silent ``None`` if missing). Must be plumbed through;
    # otherwise the target KV pool oversizes by 1+ GB on 32GB GPUs and
    # OOMs at cuda graph capture (see debug_journal 2026-05-11-kvc-...).
    dflash_draft_num_layers: Optional[int]
    # arch flags (derived, not direct server_args fields)
    is_hybrid_swa: bool
    is_hybrid_swa_compress: bool
    use_mla_backend: bool
    mambaish_config: Optional[Any]
    hybrid_gdn_config: Optional[Any]
    # PP slice
    start_layer: int
    end_layer: int
    num_effective_layers: int
    # optional pre-injection (draft worker reuses target's pool)
    req_to_token_pool: Optional[ReqToTokenPool]
    token_to_kv_pool_allocator: Optional[BaseTokenToKVPoolAllocator]
    # draft worker budget
    memory_pool_config: Optional["MemoryPoolConfig"]

    def configure(self, *, pre_model_load_memory: int) -> KVCacheConfigResult:
        raise NotImplementedError("populated in kvc-migrate-method-bodies")
'''


# Constructor block inserted in ModelRunner.initialize() above the
# init_memory_pool call. Fields that are pure ``server_args`` reads
# (mem_fraction_static / page_size / tp_size / pp_size / dp_size /
# enable_hisparse) are not stored separately — body reads via
# ``self.server_args.X``. Fields that were dead (tp_rank /
# attention_tp_size / dtype) are dropped outright.
_CTOR_INSERT = '''\
        self.kv_cache_configurator = KVCacheConfigurator(
            device=self.device,
            gpu_id=self.gpu_id,
            model_config=self.model_config,
            server_args=self.server_args,
            kv_cache_dtype=self.kv_cache_dtype,
            spec_algorithm=self.spec_algorithm,
            is_draft_worker=self.is_draft_worker,
            dflash_draft_num_layers=self.dflash_draft_num_layers,
            is_hybrid_swa=self.is_hybrid_swa,
            is_hybrid_swa_compress=self.is_hybrid_swa_compress,
            use_mla_backend=self.use_mla_backend,
            mambaish_config=mambaish_config(self.model_config),
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
    # Per MECH_COMMIT_SPLIT "长 ctor → init_X" rule, the multi-line ctor
    # lives in its own ``init_kv_cache_configurator`` helper method.
    text = replace_call_site(
        text,
        old=(
            "        # Init memory pool and attention backends\n"
            "        self.init_memory_pool(pre_model_load_memory)\n"
        ),
        new=(
            "        # Init memory pool and attention backends\n"
            "        self.init_kv_cache_configurator()\n"
            "        self.init_memory_pool(pre_model_load_memory)\n"
        ),
    )
    helper_method = (
        "    def init_kv_cache_configurator(self):\n"
        f"{_CTOR_INSERT}"
        "\n"
    )
    text = text.replace(
        "    def _build_model_config(",
        helper_method + "    def _build_model_config(",
        1,
    )

    mr.write_text(text)

    # 3) pool_configurator reads ``mr.enable_hisparse`` — switch to
    # ``mr.server_args.enable_hisparse`` since the new ``mr`` (now
    # ``KVCacheConfigurator``) drops the redundant ``enable_hisparse``
    # field; reading via ``server_args`` works for both ModelRunner
    # (preflight callers) and KVCacheConfigurator.
    pc = wt / "python/sglang/srt/model_executor/model_runner_components/pool_configurator.py"
    pc_text = pc.read_text()
    pc_text = pc_text.replace("mr.enable_hisparse", "mr.server_args.enable_hisparse")
    pc.write_text(pc_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
