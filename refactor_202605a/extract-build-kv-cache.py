#!/usr/bin/env python3
"""Cut ``init_cache_with_memory_pool`` from Scheduler; paste as a free
function ``build_kv_cache`` in ``scheduler_components/setup/kv_cache.py``.
Returns a ``KVCacheBuildResult`` dataclass containing 9 KV-cache derived
fields; the caller (Scheduler.__init__) unpacks each into a separate
``self.X``.

Per setup/kv_cache.md the field-cluster bundling (``self._kv_cache: KVCacheBundle``
single ref + ~283 callsite rewrite) is deferred to a follow-up commit; this
commit does only the method-extraction half.

The original method body has two tails that don't belong to KV-cache builder
proper (``hisparse_coordinator`` ref-grab + ``decode_offload_manager`` direct
construction). Those are moved out of the free function to live inline in
``Scheduler.__init__`` after the build call.

Usage:
    uv run --python 3.12 extract-build-kv-cache.py run
    uv run --python 3.12 extract-build-kv-cache.py verify
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
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-build-kv-cache"
SUBJECT = "Extract init_cache_with_memory_pool to scheduler_components/setup/kv_cache.py"
BODY = """\
Move ``init_cache_with_memory_pool`` body off Scheduler into a free function
``build_kv_cache`` in ``scheduler_components/setup/kv_cache.py``. The method
writes 9 ``self.X`` fields (is_hybrid_swa / is_hybrid_ssm /
sliding_window_size / full_tokens_per_layer / swa_tokens_per_layer /
req_to_token_pool / token_to_kv_pool_allocator / disable_radix_cache /
tree_cache); these become the fields of a returned ``KVCacheBuildResult``
dataclass. The caller in ``Scheduler.__init__`` unpacks each result field
into a ``self.X``.

The hisparse_coordinator ref-grab and decode_offload_manager construction
that lived at the tail of the method are moved out of the builder and
inlined into ``Scheduler.__init__`` after the build call. The
``init_mm_embedding_cache`` call at the very end of the method stays inside
``build_kv_cache`` (it's part of the KV-cache subsystem setup closure).

Field-cluster bundling — collapsing the 9 individual ``self.X`` fields into
a single ``self._kv_cache: KVCacheBundle`` reference + repo-wide callsite
rewrite — is deferred to a follow-up commit.

No behavior change.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Tail block to STRIP from the method body (after dedent). Keyed on the
# unique ``    if self.enable_hisparse:`` opening at 4-space indent and the
# closing ``            self.decode_offload_manager = None\n\n`` blank-line
# separator that precedes the surviving ``embedding_cache_size = ...`` tail.
TAIL_BLOCK_TO_STRIP = """\
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


# Replacement for the call site in ``Scheduler.__init__`` (line ~451).
INLINE_CALLER_REPLACEMENT = """\
        # Init cache and memory pool
        result = kv_cache.build_kv_cache(
            server_args=self.server_args,
            model_config=self.model_config,
            tp_worker=self.tp_worker,
            page_size=self.page_size,
            spec_algorithm=self.spec_algorithm,
            attn_tp_cpu_group=self.attn_tp_cpu_group,
            tp_cpu_group=self.tp_cpu_group,
            attn_cp_cpu_group=self.attn_cp_cpu_group,
            enable_metrics=self.enable_metrics,
            enable_kv_cache_events=self.enable_kv_cache_events,
            ps=self.ps,
            tp_group=self.tp_group,
            enable_hierarchical_cache=self.enable_hierarchical_cache,
        )
        self.is_hybrid_swa = result.is_hybrid_swa
        self.is_hybrid_ssm = result.is_hybrid_ssm
        self.sliding_window_size = result.sliding_window_size
        self.full_tokens_per_layer = result.full_tokens_per_layer
        self.swa_tokens_per_layer = result.swa_tokens_per_layer
        self.req_to_token_pool = result.req_to_token_pool
        self.token_to_kv_pool_allocator = result.token_to_kv_pool_allocator
        self.disable_radix_cache = result.disable_radix_cache
        self.tree_cache = result.tree_cache

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


# Header inserted at top of the appended free function (imports + dataclass).
KVCACHE_HEADER_INSERT = """\
from dataclasses import dataclass
from typing import Optional

from sglang.srt.configs.model_config import ModelImpl
from sglang.srt.environ import envs
from sglang.srt.model_loader.utils import get_resolved_model_impl
from sglang.srt.managers.mm_utils import init_mm_embedding_cache
from sglang.srt.mem_cache.cache_init_params import CacheInitParams
from sglang.srt.mem_cache.radix_cache import RadixCache
from sglang.srt.session.streaming_session import StreamingSession


@dataclass(frozen=True, slots=True, kw_only=True)
class KVCacheBuildResult:
    \"\"\"Return type for ``build_kv_cache``: 9 fields the caller writes back to
    ``Scheduler.self.X``. Field-cluster bundling (a single
    ``self._kv_cache`` ref instead of 9) is a follow-up commit.\"\"\"

    is_hybrid_swa: bool
    is_hybrid_ssm: bool
    sliding_window_size: Optional[int]
    full_tokens_per_layer: Optional[int]
    swa_tokens_per_layer: Optional[int]
    req_to_token_pool: object
    token_to_kv_pool_allocator: object
    disable_radix_cache: bool
    tree_cache: object


"""


def _build_function_text(method_text: str) -> str:
    """Convert the cut method body to a free function body."""
    text = dedent_method_to_function(method_text)

    # Strip the hisparse + decode_offload tail (moved to caller).
    if TAIL_BLOCK_TO_STRIP not in text:
        raise RuntimeError("tail block anchor mismatch — method shape changed")
    text = text.replace(TAIL_BLOCK_TO_STRIP, "")

    # Replace the signature with the new free-function signature.
    text = text.replace(
        "def init_cache_with_memory_pool(self):",
        "def build_kv_cache(\n"
        "    *,\n"
        "    server_args,\n"
        "    model_config,\n"
        "    tp_worker,\n"
        "    page_size: int,\n"
        "    spec_algorithm,\n"
        "    attn_tp_cpu_group,\n"
        "    tp_cpu_group,\n"
        "    attn_cp_cpu_group,\n"
        "    enable_metrics: bool,\n"
        "    enable_kv_cache_events: bool,\n"
        "    ps,\n"
        "    tp_group,\n"
        "    enable_hierarchical_cache: bool,\n"
        ") -> \"KVCacheBuildResult\":",
    )

    # The body's first line is ``server_args = self.server_args`` — drop it,
    # since ``server_args`` is now a parameter.
    text = text.replace("    server_args = self.server_args\n", "")

    # The body assigns 9 ``self.X = Y`` writes; convert each to a local-var
    # write. Then convert remaining ``self.X`` reads to either kwarg names
    # (the 13 inputs) or local-var names (the 9 outputs).
    #
    # Order matters: ``self.tree_cache`` must be replaced AFTER ``self.tp_worker``
    # is converted, since assignments aren't ambiguous but reads may share
    # prefixes. We do longest-name-first to avoid prefix collisions.
    bundle_fields = [
        "is_hybrid_swa",
        "is_hybrid_ssm",
        "sliding_window_size",
        "full_tokens_per_layer",
        "swa_tokens_per_layer",
        "req_to_token_pool",
        "token_to_kv_pool_allocator",
        "disable_radix_cache",
        "tree_cache",
    ]
    kwarg_fields = [
        "model_config",
        "tp_worker",
        "page_size",
        "spec_algorithm",
        "attn_tp_cpu_group",
        "tp_cpu_group",
        "attn_cp_cpu_group",
        "server_args",
        "enable_metrics",
        "enable_kv_cache_events",
        "tp_group",
        "enable_hierarchical_cache",
        "ps",
    ]
    # Sort longest-first to avoid e.g. ``self.spec_algorithm`` being clobbered
    # by a hypothetical ``self.spec`` shorter prefix replace.
    for name in sorted(bundle_fields + kwarg_fields, key=len, reverse=True):
        text = text.replace(f"self.{name}", name)

    # Initialize the two conditionally-set bundle fields at the top so the
    # final ``return`` always has a value.
    text = text.replace(
        "def build_kv_cache(\n",
        "def build_kv_cache(\n",
        1,
    )
    # Insert ``full_tokens_per_layer = None`` etc. just after the signature
    # closing ``) -> \"KVCacheBuildResult\":`` line. Anchor on the unique
    # signature-end + first body line.
    text = text.replace(
        ") -> \"KVCacheBuildResult\":\n    uses_transformers_backend = (\n",
        ") -> \"KVCacheBuildResult\":\n"
        "    sliding_window_size: Optional[int] = None\n"
        "    full_tokens_per_layer: Optional[int] = None\n"
        "    swa_tokens_per_layer: Optional[int] = None\n"
        "    uses_transformers_backend = (\n",
    )

    # Insert ``return KVCacheBuildResult(...)`` at the very end, right before
    # the trailing ``init_mm_embedding_cache(...)`` line stays last? Actually
    # that runs as a setup side-effect — it should run, then the function
    # returns. So append return AFTER ``init_mm_embedding_cache(...)``.
    # The body's final two lines (post-dedent) are:
    #   ``    embedding_cache_size = envs.SGLANG_VLM_CACHE_SIZE_MB.get()\n``
    #   ``    init_mm_embedding_cache(embedding_cache_size * 1024 * 1024)\n``
    # Replace the second of those with itself + return statement.
    text = text.replace(
        "    init_mm_embedding_cache(embedding_cache_size * 1024 * 1024)\n",
        "    init_mm_embedding_cache(embedding_cache_size * 1024 * 1024)\n"
        "\n"
        "    return KVCacheBuildResult(\n"
        "        is_hybrid_swa=is_hybrid_swa,\n"
        "        is_hybrid_ssm=is_hybrid_ssm,\n"
        "        sliding_window_size=sliding_window_size,\n"
        "        full_tokens_per_layer=full_tokens_per_layer,\n"
        "        swa_tokens_per_layer=swa_tokens_per_layer,\n"
        "        req_to_token_pool=req_to_token_pool,\n"
        "        token_to_kv_pool_allocator=token_to_kv_pool_allocator,\n"
        "        disable_radix_cache=disable_radix_cache,\n"
        "        tree_cache=tree_cache,\n"
        "    )\n",
    )

    # The body still uses ``ps.pp_rank`` / ``ps.pp_size`` / ``ps.tp_size`` /
    # ``ps.tp_rank`` — the ``ps`` kwarg is the RankTopology. No further
    # rewrites needed.
    return text


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    kvc = wt / "python/sglang/srt/managers/scheduler_components/setup/kv_cache.py"

    # 1. Cut method body from Scheduler.
    s, e = find_method_lines(
        sched.read_text(),
        class_name="Scheduler",
        method_name="init_cache_with_memory_pool",
    )
    method_text = cut_lines(sched, s, e)

    # 2. Rebuild as free function.
    function_text = _build_function_text(method_text)

    # 3. Inject required imports + ``KVCacheBuildResult`` dataclass at top of
    # the kv_cache.py module (just below the existing ``logger = ...`` line).
    text = kvc.read_text()
    text = insert_after(
        text,
        anchor="logger = logging.getLogger(__name__)\n",
        addition="\n" + KVCACHE_HEADER_INSERT,
    )
    kvc.write_text(text + function_text)

    # 4. Update Scheduler.__init__: replace ``self.init_cache_with_memory_pool()``
    # call with the inlined ``result = build_kv_cache(...)`` + 9 writebacks +
    # the hisparse / decode_offload tail that used to live inside the method.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="        # Init cache and memory pool\n"
        "        self.init_cache_with_memory_pool()\n",
        new=INLINE_CALLER_REPLACEMENT,
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
