#!/usr/bin/env python3
"""Pure block-move pre-prep for ``extract-build-kv-cache``: hoist the
tail blocks (``hisparse_coordinator`` ref-grab + ``decode_offload_manager``
construction) out of ``Scheduler.init_cache_with_memory_pool`` and into
``Scheduler.__init__`` immediately after the ``self.init_cache_with_memory_pool()``
call.

This is a standalone block-relocation commit per
``MECH_COMMIT_SPLIT.md`` §"例外" (move a hunk between functions within the
same file/class). After this commit:

- ``init_cache_with_memory_pool`` method body ends with the
  ``init_mm_embedding_cache(...)`` call (tail blocks are gone).
- ``Scheduler.__init__`` carries the tail blocks right after the
  ``self.init_cache_with_memory_pool()`` call, with method-local refs
  (``server_args.X``, ``params.tp_cache_group``) rewritten to their
  Scheduler-instance equivalents.

The follow-up ``extract-build-kv-cache-prep`` commit handles the semantic
``init_cache_with_memory_pool`` → ``build_kv_cache`` redesign (staticmethod
+ kwargs + KVCacheBuildResult return). ``extract-build-kv-cache-move`` then
physically cuts + pastes the method.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "extract-build-kv-cache-pre-prep"
SUBJECT = "Hoist hisparse and decode-offload setup out of init_cache_with_memory_pool"
BODY = """\
Pure block-move pre-prep for ``extract-build-kv-cache``.

Move tail blocks from the body of
``Scheduler.init_cache_with_memory_pool`` to ``Scheduler.__init__``,
immediately after the ``self.init_cache_with_memory_pool()`` call:

- ``if self.enable_hisparse: ...`` (``hisparse_coordinator`` ref-grab +
  ``set_decode_producer_stream(...)``).
- ``if (server_args.disaggregation_mode == "decode" and ...): ...
  else: self.decode_offload_manager = None`` (decode-offload manager
  construction).

Method-local refs that no longer resolve in ``Scheduler.__init__`` are
rewritten to their ``self.X`` form:

- ``server_args.disaggregation_mode`` → ``self.server_args.disaggregation_mode``
- ``server_args.disaggregation_decode_enable_offload_kvcache`` →
  ``self.server_args.disaggregation_decode_enable_offload_kvcache``
- ``params.tp_cache_group`` (local alias) → the inlined conditional
  ``(self.attn_tp_cpu_group if self.server_args.enable_dp_attention else
  self.tp_cpu_group)``.

Diff is one delete from
``Scheduler.init_cache_with_memory_pool`` plus one insert into
``Scheduler.__init__``. ``git --color-moved`` should mark the relocated
lines as moved (modulo the ref rewrites listed above).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Original tail blocks as they appear inside ``init_cache_with_memory_pool``
# body (method-local ``server_args`` / ``params.tp_cache_group`` refs).
TAIL_BLOCK_INSIDE_METHOD = """\
        if self.enable_hisparse:
            # Coordinator was created inside ModelRunner.initialize() before CUDA graph capture
            self.hisparse_coordinator = self.tp_worker.model_runner.hisparse_coordinator
            self.hisparse_coordinator.set_decode_producer_stream(self.forward_stream)

        if (
            server_args.disaggregation_mode == "decode"
            and server_args.disaggregation_decode_enable_offload_kvcache
        ):
            self.decode_offload_manager = DecodeKVCacheOffloadManager(
                req_to_token_pool=self.req_to_token_pool,
                token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
                tp_group=params.tp_cache_group,
                tree_cache=self.tree_cache,
                server_args=self.server_args,
            )
        else:
            self.decode_offload_manager = None

"""


# Same blocks rewritten for ``Scheduler.__init__`` context: ``server_args.X``
# (local) → ``self.server_args.X``, ``params.tp_cache_group`` (local alias) →
# the original conditional expression it aliased.
TAIL_BLOCK_IN_CALLER = """\

        if self.enable_hisparse:
            # Coordinator was created inside ModelRunner.initialize() before CUDA graph capture
            self.hisparse_coordinator = self.tp_worker.model_runner.hisparse_coordinator
            self.hisparse_coordinator.set_decode_producer_stream(self.forward_stream)

        if (
            self.server_args.disaggregation_mode == "decode"
            and self.server_args.disaggregation_decode_enable_offload_kvcache
        ):
            self.decode_offload_manager = DecodeKVCacheOffloadManager(
                req_to_token_pool=self.req_to_token_pool,
                token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
                tp_group=(
                    self.attn_tp_cpu_group
                    if self.server_args.enable_dp_attention
                    else self.tp_cpu_group
                ),
                tree_cache=self.tree_cache,
                server_args=self.server_args,
            )
        else:
            self.decode_offload_manager = None
"""


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    text = sched.read_text()

    # 1. Strip the 2 tail blocks from inside the method body.
    if TAIL_BLOCK_INSIDE_METHOD not in text:
        raise RuntimeError(
            "tail block anchor mismatch — init_cache_with_memory_pool body shape changed"
        )
    text = text.replace(TAIL_BLOCK_INSIDE_METHOD, "")

    # 2. Insert the rewritten blocks in Scheduler.__init__ after the
    #    init_cache_with_memory_pool() call.
    text = replace_call_site(
        text,
        old="        # Init cache and memory pool\n"
        "        self.init_cache_with_memory_pool()\n",
        new="        # Init cache and memory pool\n"
        "        self.init_cache_with_memory_pool()\n"
        + TAIL_BLOCK_IN_CALLER,
    )

    sched.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
