#!/usr/bin/env python3
"""Migrate the 6 leaf helpers off ``ModelRunnerKVCacheMixin`` into
``KVCacheConfigurator``. PR 1/3 of the body migration.

Leaves (no self-writes; pure reads) are migrated whole via cut+sub+paste.
Each migrated method goes into the configurator class right after the
``configure`` stub (still ``raise NotImplementedError`` until
``kvc-migrate-configure``).

Migrated:

| Mixin                        | Configurator                          |
|------------------------------|---------------------------------------|
| ``_profile_available_bytes`` | ``_profile_available_bytes``          |
| ``handle_max_mamba_cache``   | ``_handle_max_mamba_cache`` (privacy) |
| ``_calculate_mamba_ratio``   | ``_calculate_mamba_ratio``            |
| ``_apply_token_constraints`` | ``_apply_token_constraints``          |
| ``_resolve_max_num_reqs``    | ``_resolve_max_num_reqs``             |
| ``_resolve_memory_pool_config`` | ``_resolve_memory_pool_config``    |

Mixin keeps thin 1-line delegates for the 5 methods still called by
its remaining body (``_init_pools`` / ``_apply_memory_pool_config`` /
``init_memory_pool``); the only caller of ``handle_max_mamba_cache``
was ``_profile_available_bytes`` itself, so the privacy-flipped
``_handle_max_mamba_cache`` lives only on the configurator and the
mixin does NOT need a corresponding delegate.

Substitutions applied to each migrated body:

- ``(self: ModelRunner, ...)`` → ``(self, ...)`` (annotation cleanup).
- ``mambaish_config(self.model_config, is_draft_worker=...)`` →
  ``self.mambaish_config`` (cached field).
- ``hybrid_gdn_config(self.model_config)`` → ``self.hybrid_gdn_config``.
- ``self.handle_max_mamba_cache(...)`` →
  ``self._handle_max_mamba_cache(...)`` (privacy flip, only inside
  ``_profile_available_bytes``).

Usage:
    uv run --python 3.12 kvc-migrate-leaves.py run
    uv run --python 3.12 kvc-migrate-leaves.py verify
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
from _helpers import find_method_lines, insert_after
from _runner import run_pr

ID = "kvc-migrate-leaves"
SUBJECT = "Migrate KV cache leaf helpers from mixin to KVCacheConfigurator"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/kvc-extract-mla-dim"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Mixin → configurator names.
_LEAVES_AS_IS = [
    "_profile_available_bytes",
    "_calculate_mamba_ratio",
    "_apply_token_constraints",
    "_resolve_max_num_reqs",
    "_resolve_memory_pool_config",
]
_HANDLE_MAMBA_PRIVACY_FLIP = ("handle_max_mamba_cache", "_handle_max_mamba_cache")

# Mixin delegate signatures (kept terse — passed-through args; configurator's
# return type does the talking).
_DELEGATE_SIGS = {
    "_profile_available_bytes": (
        "    def _profile_available_bytes(self: ModelRunner, pre_model_load_memory: int) -> int:\n"
        "        return self.kv_cache_configurator._profile_available_bytes(pre_model_load_memory)\n"
    ),
    "_calculate_mamba_ratio": (
        "    def _calculate_mamba_ratio(self: ModelRunner) -> int:\n"
        "        return self.kv_cache_configurator._calculate_mamba_ratio()\n"
    ),
    "_apply_token_constraints": (
        "    def _apply_token_constraints(self: ModelRunner, token_capacity: int) -> int:\n"
        "        return self.kv_cache_configurator._apply_token_constraints(token_capacity)\n"
    ),
    "_resolve_max_num_reqs": (
        "    def _resolve_max_num_reqs(self: ModelRunner, token_capacity: int) -> int:\n"
        "        return self.kv_cache_configurator._resolve_max_num_reqs(token_capacity)\n"
    ),
    "_resolve_memory_pool_config": (
        "    def _resolve_memory_pool_config(\n"
        "        self: ModelRunner, pre_model_load_memory: int\n"
        "    ) -> MemoryPoolConfig:\n"
        "        return self.kv_cache_configurator._resolve_memory_pool_config(\n"
        "            pre_model_load_memory\n"
        "        )\n"
    ),
}


def _global_subs(body: str) -> str:
    body = body.replace("(self: ModelRunner, ", "(self, ")
    body = body.replace("(self: ModelRunner)", "(self)")
    body = body.replace(
        "self: ModelRunner, pre_model_load_memory: int",
        "self, pre_model_load_memory: int",
    )
    body = body.replace(
        "self: ModelRunner, token_capacity: int",
        "self, token_capacity: int",
    )
    body = body.replace(
        "self: ModelRunner, total_rest_memory",
        "self, total_rest_memory",
    )
    body = re.sub(
        r"mambaish_config\(\s*self\.model_config,\s*is_draft_worker=self\.is_draft_worker\s*\)",
        "self.mambaish_config",
        body,
    )
    body = body.replace(
        "hybrid_gdn_config(self.model_config)", "self.hybrid_gdn_config"
    )
    return body


def _extract(text: str, name: str) -> tuple[str, int, int]:
    s, e = find_method_lines(
        text, class_name="ModelRunnerKVCacheMixin", method_name=name
    )
    return "".join(text.splitlines(keepends=True)[s:e]), s, e


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/model_executor/model_runner_kv_cache_mixin.py"
    cfg = wt / "python/sglang/srt/mem_cache/kv_cache_configurator.py"

    mixin_text = mixin.read_text()

    # ---- Build the migrated method block (configurator side) ----
    migrated_parts: list[str] = []

    # 5 as-is leaves.
    for name in _LEAVES_AS_IS:
        body, _, _ = _extract(mixin_text, name)
        migrated_parts.append(_global_subs(body))

    # handle_max_mamba_cache → _handle_max_mamba_cache (privacy flip).
    body, _, _ = _extract(mixin_text, _HANDLE_MAMBA_PRIVACY_FLIP[0])
    body = body.replace(
        "    def handle_max_mamba_cache(",
        "    def _handle_max_mamba_cache(",
    )
    migrated_parts.append(_global_subs(body))

    methods_block = "\n".join(migrated_parts)

    # Inject methods into the configurator class right after the configure
    # stub's ``raise NotImplementedError`` line (stable anchor — the stub
    # survives until kvc-migrate-configure).
    cfg_text = cfg.read_text()
    cfg_text = insert_after(
        cfg_text,
        anchor=(
            '        raise NotImplementedError("populated in kvc-migrate-method-bodies")\n'
        ),
        addition="\n" + methods_block,
    )
    cfg.write_text(cfg_text)

    # ---- Mixin side: convert ``_profile_available_bytes`` etc. to delegates,
    # delete ``handle_max_mamba_cache`` (its only caller is migrating away). ----
    # The 5 as-is methods get a 1-line delegate. ``_profile_available_bytes``
    # also picks up the privacy flip in its body — but the body is gone now
    # (replaced by the delegate), so no extra step needed.
    text = mixin.read_text()
    src = text.splitlines(keepends=True)

    # Sort cut/replace operations from BOTTOM to TOP so the line numbers
    # earlier in the file aren't invalidated by edits below them.
    ops: list[tuple[int, int, str]] = []
    for name in _LEAVES_AS_IS:
        s, e = find_method_lines(text, class_name="ModelRunnerKVCacheMixin", method_name=name)
        ops.append((s, e, _DELEGATE_SIGS[name]))
    s, e = find_method_lines(
        text, class_name="ModelRunnerKVCacheMixin", method_name=_HANDLE_MAMBA_PRIVACY_FLIP[0]
    )
    ops.append((s, e, ""))  # delete entirely

    for s, e, replacement in sorted(ops, key=lambda op: op[0], reverse=True):
        repl_lines = [replacement] if replacement else []
        # Preserve trailing blank line after the method (if there was one,
        # the cut already includes it; the delegate string ends with \n so
        # no extra blank line is needed here).
        src = src[:s] + repl_lines + src[e:]

    mixin.write_text("".join(src))


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
