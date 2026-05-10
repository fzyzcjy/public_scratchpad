#!/usr/bin/env python3
"""Migrate 9 method bodies from `ModelRunnerKVCacheMixin` into
`KVCacheConfigurator`. Per ch3.2 spec (kv_cache_configurator.md).

Method-by-method changes:

| Mixin method                  | KVCacheConfigurator                        |
|-------------------------------|--------------------------------------------|
| ``init_memory_pool``          | ``configure`` (rename + dataclass return)  |
| ``_profile_available_bytes``  | ``_profile_available_bytes`` (as-is)       |
| ``handle_max_mamba_cache``    | ``_handle_max_mamba_cache`` (privacy flip) |
| ``_calculate_mamba_ratio``    | ``_calculate_mamba_ratio`` (as-is)         |
| ``_init_pools``               | ``_init_pools`` (locals + return tuple)    |
| ``_apply_token_constraints``  | ``_apply_token_constraints`` (as-is)       |
| ``_resolve_max_num_reqs``     | ``_resolve_max_num_reqs`` (as-is)          |
| ``_apply_memory_pool_config`` | (absorbed into ``configure``)              |
| ``_resolve_memory_pool_config`` | ``_resolve_memory_pool_config`` (as-is)  |
| ``calculate_mla_kv_cache_dim`` | (already in this file as a free function) |

Substitutions across all migrated bodies:

- ``self: ModelRunner`` parameter annotation → ``self``.
- ``mambaish_config(self)`` → ``self.mambaish_config`` (use cached field).
- ``hybrid_gdn_config(self.model_config)`` → ``self.hybrid_gdn_config``.
- ``self.calculate_mla_kv_cache_dim()`` →
  ``calculate_mla_kv_cache_dim(model_config=..., kv_cache_dtype=..., server_args=...)``
  (bare call — the helper lives in the same module).

`_init_pools` body extras:

- Substitute the 8 result-style ``self.X`` reads / writes
  (``max_total_num_tokens``, ``max_running_requests``,
  ``full_max_total_num_tokens``, ``swa_max_total_num_tokens``,
  ``c4_max_total_num_tokens``, ``c128_max_total_num_tokens``,
  ``c4_state_pool_size``, ``c128_state_pool_size``, ``state_dtype``,
  ``req_to_token_pool``, ``token_to_kv_pool``,
  ``token_to_kv_pool_allocator``) with bare names — they become method
  kwargs (the configurator passes them in from ``configure``).
- ``token_to_kv_pool`` is initialized to ``None`` at top of body.
- Method ends with ``return req_to_token_pool, token_to_kv_pool, token_to_kv_pool_allocator``.

`configure` body (custom, not migrated mechanically):

- Resolve ``MemoryPoolConfig`` (use pre-injected for draft, else profile).
- Compute c4/c128/state_dtype intermediates from config.
- Call ``self._init_pools(...)`` → 3-tuple.
- Return ``KVCacheConfigResult(...)``.

Mixin reduces to a 1-line ``init_memory_pool`` delegate that calls
``self.kv_cache_configurator.configure(...)`` and writes back the 8
result fields. The 1-line delegate goes away in
`kvc-drop-mixin-inheritance`.

Usage:
    uv run --python 3.12 kvc-migrate-method-bodies.py run
    uv run --python 3.12 kvc-migrate-method-bodies.py verify
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
from _helpers import find_method_lines
from _runner import run_pr

ID = "kvc-migrate-method-bodies"
SUBJECT = "Migrate ModelRunnerKVCacheMixin method bodies to KVCacheConfigurator"
BODY = ""
AREA = "nonmech_model_runner"
BASE = "tom_refactor_202605a/primary/nonmech_model_runner/kvc-introduce-skeleton"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Methods migrated as-is (only annotation cleanup + global substitutions).
_AS_IS_METHODS = [
    "_profile_available_bytes",
    "_calculate_mamba_ratio",
    "_apply_token_constraints",
    "_resolve_max_num_reqs",
    "_resolve_memory_pool_config",
]


# Field names in `_init_pools` that move from dataclass-field reads /
# self-writes to bare method-local kwargs / vars. Order matters — longer
# names first so prefix substrings don't get partially substituted (e.g.
# ``token_to_kv_pool_allocator`` must run before ``token_to_kv_pool``).
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
    """Substitutions applied to every migrated method body."""
    body = body.replace("(self: ModelRunner, ", "(self, ")
    body = body.replace("(self: ModelRunner)", "(self)")
    # Mixin's `self: ModelRunner` may also appear with a multi-line
    # signature — handle the leading-arg case.
    body = body.replace(
        "self: ModelRunner, pre_model_load_memory: int",
        "self, pre_model_load_memory: int",
    )
    body = body.replace(
        "self: ModelRunner, token_capacity: int",
        "self, token_capacity: int",
    )
    # ``mambaish_config(self.model_config, is_draft_worker=self.is_draft_worker)``
    # may span multiple lines (black-wrapped). Match both forms — the cached
    # ``self.mambaish_config`` field on KVCacheConfigurator already holds the
    # value from the constructor; reuse it instead of recomputing.
    body = re.sub(
        r"mambaish_config\(\s*self\.model_config,\s*is_draft_worker=self\.is_draft_worker\s*\)",
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
    """Rewrite ``_init_pools`` body — change signature, drop ``self.X``
    references on the kwarg fields, init ``token_to_kv_pool`` local, append
    return tuple.
    """
    body = _global_subs(body)
    # Field self.X → bare X (covers both reads and self-writes).
    for name in _INIT_POOLS_FIELDS:
        body = body.replace(f"self.{name}", name)
    # Replace the original method signature with the kwarg-laden form.
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
    # Append return-tuple at the very end of the body (just before the
    # trailing newline).
    if not body.rstrip().endswith(
        "return req_to_token_pool, token_to_kv_pool, token_to_kv_pool_allocator"
    ):
        body = body.rstrip() + (
            "\n        return req_to_token_pool, token_to_kv_pool, token_to_kv_pool_allocator\n"
        )
    return body


def _migrate_handle_max_mamba_cache(body: str) -> str:
    body = _global_subs(body)
    # Privacy flip: handle_max_mamba_cache → _handle_max_mamba_cache.
    body = body.replace(
        "    def handle_max_mamba_cache(",
        "    def _handle_max_mamba_cache(",
    )
    return body


def _migrate_as_is(body: str) -> str:
    return _global_subs(body)


_INIT_POOLS_CALL_REPLACEMENT = '''\
        req_to_token_pool, token_to_kv_pool, token_to_kv_pool_allocator = self._init_pools(
            max_total_num_tokens=max_total_num_tokens,
            max_running_requests=max_running_requests,
            full_max_total_num_tokens=full_max_total_num_tokens,
            swa_max_total_num_tokens=swa_max_total_num_tokens,
            c4_max_total_num_tokens=c4_max_total_num_tokens,
            c128_max_total_num_tokens=c128_max_total_num_tokens,
            c4_state_pool_size=c4_state_pool_size,
            c128_state_pool_size=c128_state_pool_size,
            state_dtype=state_dtype,
            req_to_token_pool=self.req_to_token_pool,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
        )
'''


_RETURN_BLOCK = '''\

        return KVCacheConfigResult(
            max_total_num_tokens=max_total_num_tokens,
            max_running_requests=max_running_requests,
            full_max_total_num_tokens=full_max_total_num_tokens,
            swa_max_total_num_tokens=swa_max_total_num_tokens,
            req_to_token_pool=req_to_token_pool,
            token_to_kv_pool=token_to_kv_pool,
            token_to_kv_pool_allocator=token_to_kv_pool_allocator,
            memory_pool_config=config,
        )
'''


# 8 `self.X = config.X` writes inside _apply_memory_pool_config that
# convert to local-var assignments. The c4/c128 quartet has both
# branches (``self.is_draft_worker`` else `else:`) that need converting.
_APC_FIELDS = [
    "max_total_num_tokens",
    "max_running_requests",
    "full_max_total_num_tokens",
    "swa_max_total_num_tokens",
    "c4_max_total_num_tokens",
    "c128_max_total_num_tokens",
    "c4_state_pool_size",
    "c128_state_pool_size",
]


def _strip_def_and_docstring(method_text: str) -> str:
    """Drop the ``def ...:\\n`` line and any single-line docstring; keep the
    body lines (with original leading indent intact)."""
    lines = method_text.splitlines(keepends=True)
    # Skip leading blank lines.
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    # Skip the def line (single line — no multiline-def support needed here).
    if i < len(lines) and lines[i].lstrip().startswith("def "):
        i += 1
    # Skip the docstring (single-line """...""").
    if i < len(lines) and lines[i].lstrip().startswith('"""'):
        i += 1
    return "".join(lines[i:])


def _build_configure_body(extract) -> str:
    """Synthesize ``configure`` by cut+substitute+inline from
    ``init_memory_pool`` + ``_apply_memory_pool_config``.

    Steps:
      1. Cut ``init_memory_pool`` body verbatim.
      2. Signature swap: ``init_memory_pool(self: ModelRunner, pre_model_load_memory)``
         → ``configure(self, *, pre_model_load_memory) -> KVCacheConfigResult``.
      3. Introduce ``config`` local: rename
         ``self.memory_pool_config = self._resolve_memory_pool_config(...)``
         to ``config = self._resolve_memory_pool_config(...)`` and add
         ``config = self.memory_pool_config`` after the draft-worker assert.
      4. Cut ``_apply_memory_pool_config`` body, strip its def+docstring,
         convert its 8 result-style ``self.X = config.X`` writes to local
         vars, predeclare ``state_dtype = None`` before the deepseek_v4
         conditional, and replace its ``self._init_pools()`` call with the
         kwarg-tuple form.
      5. Inline the converted apc body in place of
         ``self._apply_memory_pool_config(self.memory_pool_config)``.
      6. Append the ``return KVCacheConfigResult(...)`` block.
    """
    body = extract("init_memory_pool")

    # 2) Signature swap.
    body = body.replace(
        "    def init_memory_pool(self: ModelRunner, pre_model_load_memory: int):\n",
        "    def configure(self, *, pre_model_load_memory: int) -> KVCacheConfigResult:\n",
    )

    # 3a) Rename `self.memory_pool_config = self._resolve_memory_pool_config(`
    # to `config = self._resolve_memory_pool_config(`.
    body = body.replace(
        "            self.memory_pool_config = self._resolve_memory_pool_config(\n",
        "            config = self._resolve_memory_pool_config(\n",
    )
    # 3b) Add `config = self.memory_pool_config` after the draft-worker assert.
    body = body.replace(
        '            ), "Draft worker requires memory_pool_config"\n        else:\n',
        '            ), "Draft worker requires memory_pool_config"\n'
        "            config = self.memory_pool_config\n"
        "        else:\n",
    )

    # 4) Inline _apply_memory_pool_config body, with the 4 transforms.
    apc = extract("_apply_memory_pool_config")
    apc = _strip_def_and_docstring(apc)
    # Convert the 8 result-style ``self.X = ...`` writes to local-var. Indent
    # varies between 8 (method body) and 12 (inside ``if`` branches), so use
    # an indent-agnostic regex.
    for field in _APC_FIELDS:
        apc = re.sub(
            rf"^(\s+)self\.{field} = ",
            rf"\1{field} = ",
            apc,
            flags=re.MULTILINE,
        )
    # Predeclare full/swa to None — they're conditionally set.
    apc = apc.replace(
        "        if self.is_hybrid_swa:\n",
        "        full_max_total_num_tokens = None\n"
        "        swa_max_total_num_tokens = None\n"
        "        if self.is_hybrid_swa:\n",
    )
    # Predeclare state_dtype to None before the deepseek_v4 conditional;
    # convert the conditional self.X write to local-var.
    apc = apc.replace(
        "        if is_deepseek_v4(self.model_config.hf_config):\n"
        "            self.state_dtype = torch.float32\n",
        "        state_dtype: Optional[torch.dtype] = None\n"
        "        if is_deepseek_v4(self.model_config.hf_config):\n"
        "            state_dtype = torch.float32\n",
    )
    # Replace self._init_pools() with the kwarg-tuple form.
    apc = apc.replace(
        "        self._init_pools()\n",
        _INIT_POOLS_CALL_REPLACEMENT,
    )

    # 5) Inline apc at the call site.
    body = body.replace(
        "        self._apply_memory_pool_config(self.memory_pool_config)\n",
        apc,
    )

    # 6) Append return.
    body = body.rstrip() + "\n" + _RETURN_BLOCK

    return body


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py"
    cfg = wt / "python/sglang/srt/mem_cache/kv_cache_configurator.py"

    mixin_text = mixin.read_text()
    cfg_text = cfg.read_text()

    # Extract each method body (leading whitespace + def line + body lines)
    # via line-range, then apply per-method substitutions.
    src_lines = mixin_text.splitlines(keepends=True)

    def extract(name: str) -> str:
        s, e = find_method_lines(
            mixin_text, class_name="ModelRunnerKVCacheMixin", method_name=name
        )
        return "".join(src_lines[s:e])

    migrated_parts: list[str] = []

    # configure: synthesized by cut+substitute+inline from init_memory_pool +
    # _apply_memory_pool_config — see _build_configure_body for the steps.
    migrated_parts.append(_build_configure_body(extract))

    # _profile_available_bytes / _calculate_mamba_ratio / _apply_token_constraints
    # / _resolve_max_num_reqs / _resolve_memory_pool_config — as-is.
    for name in _AS_IS_METHODS:
        migrated_parts.append(_migrate_as_is(extract(name)))

    # handle_max_mamba_cache → _handle_max_mamba_cache (privacy flip).
    migrated_parts.append(_migrate_handle_max_mamba_cache(extract("handle_max_mamba_cache")))

    # _init_pools — heaviest transform.
    migrated_parts.append(_migrate_init_pools(extract("_init_pools")))

    methods_block = "\n".join(migrated_parts)

    # Replace the stub configure() in the configurator with the migrated block.
    stub = (
        "    def configure(self, *, pre_model_load_memory: int) -> KVCacheConfigResult:\n"
        '        raise NotImplementedError("populated in kvc-migrate-method-bodies")\n'
    )
    if stub not in cfg_text:
        raise RuntimeError("kvc-introduce-skeleton stub not found in configurator")
    cfg_text = cfg_text.replace(stub, methods_block)

    # Add the imports the migrated bodies need. We grow the existing import
    # block; isort normalizes order.
    extra_imports = '''\
import logging

from sglang.srt.configs.model_config import (
    get_nsa_index_head_dim,
    is_deepseek_nsa,
    is_deepseek_v4,
)
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
    cfg_text = cfg_text.replace(
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n\n",
        "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n\n" + extra_imports,
    )

    cfg.write_text(cfg_text)

    # Reduce mixin to the 1-line init_memory_pool delegate. The other 9
    # methods (incl. calculate_mla_kv_cache_dim which already lives in
    # kv_cache_dim.py) get cut.
    new_mixin = '''from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sglang.srt.model_executor.model_runner import ModelRunner


class ModelRunnerKVCacheMixin:
    def init_memory_pool(self: ModelRunner, pre_model_load_memory: int):
        """Temporary 1-line delegate — dropped in kvc-drop-mixin-inheritance."""
        result = self.kv_cache_configurator.configure(
            pre_model_load_memory=pre_model_load_memory
        )
        self.max_total_num_tokens = result.max_total_num_tokens
        self.max_running_requests = result.max_running_requests
        self.req_to_token_pool = result.req_to_token_pool
        self.token_to_kv_pool = result.token_to_kv_pool
        self.token_to_kv_pool_allocator = result.token_to_kv_pool_allocator
        self.memory_pool_config = result.memory_pool_config
        if self.is_hybrid_swa:
            self.full_max_total_num_tokens = result.full_max_total_num_tokens
            self.swa_max_total_num_tokens = result.swa_max_total_num_tokens
'''
    mixin.write_text(new_mixin)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
