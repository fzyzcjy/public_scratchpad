#!/usr/bin/env python3
"""Synthesize ``configure`` from ``init_memory_pool`` +
``_apply_memory_pool_config`` (cut + inline + sub) and reduce the mixin
to a single 1-line ``init_memory_pool`` delegate. PR 3/3 of the body
migration.

After this commit:

- ``KVCacheConfigurator.configure`` runs the full pipeline (resolve
  config → unpack into locals → call ``_init_pools`` → return
  ``KVCacheConfigResult``). Body is ~80 LOC, derived purely by
  cut+sub+inline from the original mixin source — no literal copy of
  body lines lives in this script.
- ``ModelRunnerKVCacheMixin`` has exactly one method left:
  ``init_memory_pool`` (1-line delegate that calls
  ``self.kv_cache_configurator.configure(...)`` and writes back the 8
  result fields). Everything else (5 leaf delegates + the now-dead
  ``_apply_memory_pool_config``) is dropped.
- The temporary ``raise NotImplementedError`` stub is replaced.

Synthesis steps for ``configure``:

  1. Cut ``init_memory_pool`` body verbatim.
  2. Signature swap: ``init_memory_pool(self: ModelRunner, pre_model_load_memory)``
     → ``configure(self, *, pre_model_load_memory) -> KVCacheConfigResult``.
  3. Introduce ``config`` local: rename
     ``self.memory_pool_config = self._resolve_memory_pool_config(...)`` to
     ``config = self._resolve_memory_pool_config(...)`` and add
     ``config = self.memory_pool_config`` after the draft-worker assert.
  4. Inline ``_apply_memory_pool_config`` body in place of
     ``self._apply_memory_pool_config(...)``: convert its 8 result-style
     ``self.X`` writes to local-var; predeclare ``full_max_total_num_tokens``
     / ``swa_max_total_num_tokens`` / ``state_dtype`` to ``None`` before
     their conditional sets; replace ``self._init_pools()`` with the
     kwarg-tuple form bound to local vars.
  5. Append the ``return KVCacheConfigResult(...)`` block.

Usage:
    uv run --python 3.12 kvc-migrate-configure.py run
    uv run --python 3.12 kvc-migrate-configure.py verify
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
from _helpers import find_method_lines, replace_call_site
from _runner import run_pr

ID = "kvc-migrate-configure"
SUBJECT = "Synthesize KVCacheConfigurator.configure; reduce mixin to 1-line delegate"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/kvc-migrate-init-pools"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# 8 result-style ``self.X = ...`` writes inside _apply_memory_pool_config
# that convert to local-var assignments.
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


# 8-field caller writeback — identical to the spec block in
# kv_cache_configurator.md ch3.2.
_MIXIN_INIT_MEMORY_POOL = '''\
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


def _strip_def_and_docstring(method_text: str) -> str:
    lines = method_text.splitlines(keepends=True)
    i = 0
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i < len(lines) and lines[i].lstrip().startswith("def "):
        i += 1
    if i < len(lines) and lines[i].lstrip().startswith('"""'):
        i += 1
    return "".join(lines[i:])


def _global_subs(body: str) -> str:
    body = body.replace("(self: ModelRunner, ", "(self, ")
    body = body.replace("(self: ModelRunner)", "(self)")
    body = re.sub(
        r"mambaish_config\(\s*self\.model_config,\s*is_draft_worker=self\.is_draft_worker\s*\)",
        "self.mambaish_config",
        body,
    )
    body = body.replace(
        "hybrid_gdn_config(self.model_config)", "self.hybrid_gdn_config"
    )
    return body


def _build_configure_body(mixin_text: str) -> str:
    def extract(name: str) -> str:
        s, e = find_method_lines(
            mixin_text, class_name="ModelRunnerKVCacheMixin", method_name=name
        )
        return "".join(mixin_text.splitlines(keepends=True)[s:e])

    body = _global_subs(extract("init_memory_pool"))

    # Step 1 — signature swap.
    body = body.replace(
        "    def init_memory_pool(self, pre_model_load_memory: int):\n",
        "    def configure(self, *, pre_model_load_memory: int) -> KVCacheConfigResult:\n",
    )

    # Step 2 — introduce ``config`` local: rename the resolve assignment
    # and add ``config = self.memory_pool_config`` after the draft assert.
    body = body.replace(
        "            self.memory_pool_config = self._resolve_memory_pool_config(\n",
        "            config = self._resolve_memory_pool_config(\n",
    )
    body = body.replace(
        '            ), "Draft worker requires memory_pool_config"\n        else:\n',
        '            ), "Draft worker requires memory_pool_config"\n'
        "            config = self.memory_pool_config\n"
        "        else:\n",
    )

    # Step 3 — inline _apply_memory_pool_config body where the call lives.
    apc = _strip_def_and_docstring(_global_subs(extract("_apply_memory_pool_config")))
    for field in _APC_FIELDS:
        apc = re.sub(
            rf"^(\s+)self\.{field} = ",
            rf"\1{field} = ",
            apc,
            flags=re.MULTILINE,
        )
    apc = apc.replace(
        "        if self.is_hybrid_swa:\n",
        "        full_max_total_num_tokens = None\n"
        "        swa_max_total_num_tokens = None\n"
        "        if self.is_hybrid_swa:\n",
    )
    apc = apc.replace(
        "        if is_deepseek_v4(self.model_config.hf_config):\n"
        "            self.state_dtype = torch.float32\n",
        "        state_dtype: Optional[torch.dtype] = None\n"
        "        if is_deepseek_v4(self.model_config.hf_config):\n"
        "            state_dtype = torch.float32\n",
    )
    # The ``_init_pools`` call site in apc was already patched by
    # ``kvc-migrate-init-pools`` to a mixin-style writeback
    # (``(self.req_to_token_pool, self.token_to_kv_pool, ...) =
    # self.kv_cache_configurator._init_pools(...)`` with ``self.X`` kwargs).
    # When apc is absorbed into the configurator's ``configure``, the same
    # call needs to bind to local-var lhs and use bare-local kwargs that the
    # surrounding inlined block already populated. Replace the whole 14-line
    # patched block with the local-var form.
    _PATCHED_INIT_POOLS_CALL = (
        "        (\n"
        "            self.req_to_token_pool,\n"
        "            self.token_to_kv_pool,\n"
        "            self.token_to_kv_pool_allocator,\n"
        "        ) = self.kv_cache_configurator._init_pools(\n"
        "            max_total_num_tokens=self.max_total_num_tokens,\n"
        "            max_running_requests=self.max_running_requests,\n"
        '            full_max_total_num_tokens=getattr(self, "full_max_total_num_tokens", None),\n'
        '            swa_max_total_num_tokens=getattr(self, "swa_max_total_num_tokens", None),\n'
        "            c4_max_total_num_tokens=self.c4_max_total_num_tokens,\n"
        "            c128_max_total_num_tokens=self.c128_max_total_num_tokens,\n"
        "            c4_state_pool_size=self.c4_state_pool_size,\n"
        "            c128_state_pool_size=self.c128_state_pool_size,\n"
        '            state_dtype=getattr(self, "state_dtype", None),\n'
        "            req_to_token_pool=self.req_to_token_pool,\n"
        "            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,\n"
        "        )\n"
    )
    apc = apc.replace(_PATCHED_INIT_POOLS_CALL, _INIT_POOLS_CALL_REPLACEMENT)
    body = body.replace(
        "        self._apply_memory_pool_config(self.memory_pool_config)\n",
        apc,
    )

    # Step 4 — append return.
    body = body.rstrip() + "\n" + _RETURN_BLOCK
    return body


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py"
    cfg = wt / "python/sglang/srt/mem_cache/kv_cache_configurator.py"

    # ---- Build configure body from mixin sources ----
    mixin_text = mixin.read_text()
    configure_body = _build_configure_body(mixin_text)

    # ---- Replace the stub configure in the configurator ----
    cfg_text = cfg.read_text()
    stub = (
        "    def configure(self, *, pre_model_load_memory: int) -> KVCacheConfigResult:\n"
        '        raise NotImplementedError("populated in kvc-migrate-method-bodies")\n'
    )
    cfg_text = replace_call_site(cfg_text, old=stub, new=configure_body)
    cfg.write_text(cfg_text)

    # ---- Reduce mixin to the single ``init_memory_pool`` delegate ----
    new_mixin = '''from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sglang.srt.model_executor.model_runner import ModelRunner


class ModelRunnerKVCacheMixin:
''' + _MIXIN_INIT_MEMORY_POOL
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
