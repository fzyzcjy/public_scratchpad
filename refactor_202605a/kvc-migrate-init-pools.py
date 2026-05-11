#!/usr/bin/env python3
"""Migrate the 470-line ``_init_pools`` from ``ModelRunnerKVCacheMixin``
into ``KVCacheConfigurator``. PR 2/3 of the body migration.

The body is mostly an if/else matrix instantiating one of many KV pool /
allocator classes. The mechanical-ish transforms:

- Signature swap: ``def _init_pools(self: ModelRunner)`` →
  ``def _init_pools(self, *, max_total_num_tokens, ..., req_to_token_pool,
  token_to_kv_pool_allocator) -> tuple[ReqToTokenPool, KVCache,
  BaseTokenToKVPoolAllocator]`` — 11 kwargs covering the result-style
  fields plus the two pre-injectable pools.
- All ``self.X`` reads / writes for the 12 result-style fields
  (``max_total_num_tokens`` / ``max_running_requests`` / hybrid-swa pair /
  c4/c128 quartet / ``state_dtype`` / 3 pool fields) → bare names.
- Append ``return req_to_token_pool, token_to_kv_pool, token_to_kv_pool_allocator``.
- Init ``token_to_kv_pool = None`` at the top of the body (pool is set
  exactly once per branch but the local needs an initial binding before
  the if/else chain).
- ``mambaish_config(...)`` / ``hybrid_gdn_config(...)`` → cached
  dataclass fields.
- ``self.calculate_mla_kv_cache_dim()`` → bare
  ``calculate_mla_kv_cache_dim(...)`` (same module).

Mixin side:

- Delete ``_init_pools``. No delegate — the only call site,
  ``_apply_memory_pool_config``, switches to a direct kwarg-rich call
  on the configurator that captures the 3-tuple and writes back to
  ``self``.

Usage:
    uv run --python 3.12 kvc-migrate-init-pools.py run
    uv run --python 3.12 kvc-migrate-init-pools.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
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

ID = "kvc-migrate-init-pools"
SUBJECT = "Migrate _init_pools from mixin to KVCacheConfigurator"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/kvc-migrate-leaves"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Result-style field names that flow through ``_init_pools`` as method-local
# kwargs (no longer ``self.X``). Order matters — longer names first so prefix
# substrings don't get half-substituted.
_INIT_POOLS_FIELDS = [
    "token_to_kv_pool_allocator",
    "token_to_kv_pool",
    "req_to_token_pool",
    "full_max_total_num_tokens",
    "swa_max_total_num_tokens",
    "max_total_num_tokens",
    "max_running_requests",
    "c4_max_total_num_tokens",
    "c128_max_total_num_tokens",
    "c4_state_pool_size",
    "c128_state_pool_size",
    "state_dtype",
]


def _global_subs(body: str) -> str:
    body = body.replace("(self: ModelRunner, ", "(self, ")
    body = body.replace("(self: ModelRunner)", "(self)")
    body = re.sub(
        r"mambaish_config\(\s*self\.model_config\s*\)",
        "self.mambaish_config",
        body,
    )
    body = body.replace(
        "hybrid_gdn_config(self.model_config)", "self.hybrid_gdn_config"
    )
    body = body.replace(
        "self.calculate_mla_kv_cache_dim()",
        "calculate_mla_kv_cache_dim(\n"
        "    model_config=self.model_config,\n"
        "    kv_cache_dtype=self.kv_cache_dtype,\n"
        "    server_args=self.server_args,\n"
        ")",
    )
    return body


def _migrate_init_pools(body: str) -> str:
    body = _global_subs(body)
    for name in _INIT_POOLS_FIELDS:
        body = body.replace(f"self.{name}", name)
    body = body.replace(
        "    def _init_pools(self):\n"
        '        """Initialize the memory pools."""\n',
        '''    def _init_pools(
        self,
        *,
        max_total_num_tokens: int,
        max_running_requests: int,
        full_max_total_num_tokens: Optional[int],
        swa_max_total_num_tokens: Optional[int],
        c4_max_total_num_tokens: int,
        c128_max_total_num_tokens: int,
        c4_state_pool_size: int,
        c128_state_pool_size: int,
        state_dtype: Optional[torch.dtype],
        req_to_token_pool: Optional[ReqToTokenPool],
        token_to_kv_pool_allocator: Optional[BaseTokenToKVPoolAllocator],
    ) -> tuple[ReqToTokenPool, KVCache, BaseTokenToKVPoolAllocator]:
        """Initialize the memory pools."""
        token_to_kv_pool = None
''',
    )
    if not body.rstrip().endswith(
        "return req_to_token_pool, token_to_kv_pool, token_to_kv_pool_allocator"
    ):
        body = body.rstrip() + (
            "\n        return req_to_token_pool, token_to_kv_pool, token_to_kv_pool_allocator\n"
        )
    return body


# Imports the migrated _init_pools body needs (the if/else matrix references
# many KV pool / allocator classes + helpers). Inserted into configurator.
_EXTRA_IMPORTS = '''\
import logging

from sglang.srt.configs.model_config import get_nsa_index_head_dim, is_deepseek_v4
from sglang.srt.distributed.parallel_state import get_world_group
from sglang.srt.environ import envs
from sglang.srt.layers.dp_attention import get_attention_tp_size
from sglang.srt.mem_cache.allocator import (
    PagedTokenToKVPoolAllocator,
    TokenToKVPoolAllocator,
)
from sglang.srt.mem_cache.deepseek_v4_memory_pool import DeepSeekV4TokenToKVPool
from sglang.srt.mem_cache.hisparse_memory_pool import (
    DeepSeekV4HiSparseTokenToKVPoolAllocator,
    HiSparseNSATokenToKVPool,
    HiSparseTokenToKVPoolAllocator,
)
from sglang.srt.mem_cache.memory_pool import (
    HybridLinearKVPool,
    HybridReqToTokenPool,
    MHATokenToKVPool,
    MHATokenToKVPoolFP4,
    MLATokenToKVPool,
    MLATokenToKVPoolFP4,
)
from sglang.srt.mem_cache.swa_memory_pool import SWAKVPool, SWATokenToKVPoolAllocator
from sglang.srt.utils.common import (
    get_available_gpu_memory,
    is_float4_e2m1fn_x2,
    is_npu,
)

logger = logging.getLogger(__name__)

_is_npu = is_npu()

# the ratio of mamba cache pool size to max_running_requests
MAMBA_CACHE_SIZE_MAX_RUNNING_REQUESTS_RATIO = 3
MAMBA_CACHE_V2_ADDITIONAL_RATIO_OVERLAP = 2
MAMBA_CACHE_V2_ADDITIONAL_RATIO_NO_OVERLAP = 1

'''


# At the call site inside ``_apply_memory_pool_config`` (still on the mixin),
# the original ``self._init_pools()`` becomes a kwarg-rich call to the
# configurator, capturing the 3-tuple and writing it back to ``self``.
_MIXIN_CALL_REPLACEMENT = '''\
        (
            self.req_to_token_pool,
            self.token_to_kv_pool,
            self.token_to_kv_pool_allocator,
        ) = self.kv_cache_configurator._init_pools(
            max_total_num_tokens=self.max_total_num_tokens,
            max_running_requests=self.max_running_requests,
            full_max_total_num_tokens=getattr(self, "full_max_total_num_tokens", None),
            swa_max_total_num_tokens=getattr(self, "swa_max_total_num_tokens", None),
            c4_max_total_num_tokens=self.c4_max_total_num_tokens,
            c128_max_total_num_tokens=self.c128_max_total_num_tokens,
            c4_state_pool_size=self.c4_state_pool_size,
            c128_state_pool_size=self.c128_state_pool_size,
            state_dtype=getattr(self, "state_dtype", None),
            req_to_token_pool=self.req_to_token_pool,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
        )
'''


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py"
    cfg = wt / "python/sglang/srt/mem_cache/kv_cache_configurator.py"

    mixin_text = mixin.read_text()

    # ---- Cut + transform _init_pools ----
    s, e = find_method_lines(
        mixin_text, class_name="ModelRunnerKVCacheMixin", method_name="_init_pools"
    )
    body = "".join(mixin_text.splitlines(keepends=True)[s:e])
    migrated = _migrate_init_pools(body)

    # ---- Insert into configurator (after the configure stub) + grow imports ----
    cfg_text = cfg.read_text()
    cfg_text = cfg_text.replace(
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n\n",
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n\n"
        + _EXTRA_IMPORTS,
    )
    cfg_text = insert_after(
        cfg_text,
        anchor=(
            '        raise NotImplementedError("populated in kvc-migrate-method-bodies")\n'
        ),
        addition="\n" + migrated,
    )
    cfg.write_text(cfg_text)

    # ---- Mixin side: rewrite the call site, then cut the method ----
    text = mixin.read_text()
    text = replace_call_site(
        text,
        old="        self._init_pools()\n",
        new=_MIXIN_CALL_REPLACEMENT,
    )
    mixin.write_text(text)

    s, e = find_method_lines(
        mixin.read_text(),
        class_name="ModelRunnerKVCacheMixin",
        method_name="_init_pools",
    )
    cut_lines(mixin, s, e)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
