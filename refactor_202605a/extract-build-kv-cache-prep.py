#!/usr/bin/env python3
"""Inplace prep for ``extract-build-kv-cache``: rewrite
``init_cache_with_memory_pool`` body to its final ``build_kv_cache`` form
**in place** in Scheduler; add ``KVCacheBuildResult`` dataclass + needed
imports to ``scheduler_components/kv_cache.py``; update sole caller to
``Scheduler.build_kv_cache(...)``.

Body bytes after this commit match the body bytes that will land in
``kv_cache.py`` after ``extract-build-kv-cache-move`` (mod dedent +
decorator removal).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "extract-build-kv-cache-prep"
SUBJECT = "Rewrite init_cache_with_memory_pool body to build_kv_cache form (prep for move)"
BODY = """\
Inplace prep for the ``extract-build-kv-cache`` mech move.

In Scheduler, ``init_cache_with_memory_pool(self)`` becomes
``@staticmethod build_kv_cache(*, kwargs...) -> KVCacheBuildResult``. The
body rewrite is identical to the final free-function form:

- 22+ ``self.X`` reads converted to bare kwarg / local names.
- 9 ``self.X = Y`` writes converted to local-var writes.
- 3 None-initializers added for conditional fields.
- ``return KVCacheBuildResult(...)`` appended.

Caller in ``Scheduler.__init__`` rewritten: the
``self.init_cache_with_memory_pool()`` call is replaced by an inlined
``result = Scheduler.build_kv_cache(...)`` + 9 writebacks. (The
``hisparse_coordinator`` + ``decode_offload_manager`` tail blocks already
live in ``Scheduler.__init__`` after the ``-pre-prep`` block-move commit.)

``KVCacheBuildResult`` dataclass + needed imports are appended to
``scheduler_components/kv_cache.py`` (file already exists from earlier
chain commits).

The method **stays in Scheduler** in this commit; physical cut + paste
happens in ``extract-build-kv-cache-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


NEW_SIGNATURE = (
    "    @staticmethod\n"
    "    def build_kv_cache(\n"
    "        *,\n"
    "        server_args,\n"
    "        model_config,\n"
    "        tp_worker,\n"
    "        page_size: int,\n"
    "        spec_algorithm,\n"
    "        attn_tp_cpu_group,\n"
    "        tp_cpu_group,\n"
    "        attn_cp_cpu_group,\n"
    "        enable_metrics: bool,\n"
    "        enable_kv_cache_events: bool,\n"
    "        ps,\n"
    "        tp_group,\n"
    "        enable_hierarchical_cache: bool,\n"
    "    ) -> \"KVCacheBuildResult\":"
)


INLINE_CALLER_REPLACEMENT = """\
        # Init cache and memory pool
        result = Scheduler.build_kv_cache(
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
"""


KVCACHE_HEADER_INSERT = """\
from dataclasses import dataclass  # noqa: F401
from typing import Optional  # noqa: F401

from sglang.srt.configs.model_config import ModelImpl  # noqa: F401
from sglang.srt.environ import envs  # noqa: F401
from sglang.srt.model_loader.utils import get_resolved_model_impl  # noqa: F401
from sglang.srt.managers.mm_utils import init_mm_embedding_cache  # noqa: F401
from sglang.srt.mem_cache.cache_init_params import CacheInitParams  # noqa: F401
from sglang.srt.mem_cache.radix_cache import RadixCache  # noqa: F401
from sglang.srt.session.streaming_session import StreamingSession  # noqa: F401


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


def _rewrite_method_body(method_text: str) -> str:
    """Convert in-place: signature + body rewrites. Stays inside Scheduler
    (with class-level indent + @staticmethod). The hisparse + decode_offload
    tail blocks were already hoisted out to ``Scheduler.__init__`` by the
    ``-pre-prep`` commit, so the body shape at this point is missing them."""
    text = method_text

    # Replace signature.
    text = text.replace(
        "    def init_cache_with_memory_pool(self):", NEW_SIGNATURE
    )

    # Drop the ``server_args = self.server_args`` first body line — server_args
    # is now a parameter.
    text = text.replace("        server_args = self.server_args\n", "")

    # Bulk ``self.X`` → bare ``X`` (longest-first to avoid prefix collisions).
    fields = sorted(
        [
            # 9 bundle/output fields
            "is_hybrid_swa",
            "is_hybrid_ssm",
            "sliding_window_size",
            "full_tokens_per_layer",
            "swa_tokens_per_layer",
            "req_to_token_pool",
            "token_to_kv_pool_allocator",
            "disable_radix_cache",
            "tree_cache",
            # 13 kwarg inputs
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
        ],
        key=len,
        reverse=True,
    )
    for name in fields:
        text = text.replace(f"self.{name}", name)

    # Insert 3 None-initializers right after the signature.
    text = text.replace(
        ") -> \"KVCacheBuildResult\":\n        uses_transformers_backend = (\n",
        ") -> \"KVCacheBuildResult\":\n"
        "        sliding_window_size: Optional[int] = None\n"
        "        full_tokens_per_layer: Optional[int] = None\n"
        "        swa_tokens_per_layer: Optional[int] = None\n"
        "        uses_transformers_backend = (\n",
    )

    # Append return statement after the final ``init_mm_embedding_cache`` call.
    text = text.replace(
        "        init_mm_embedding_cache(embedding_cache_size * 1024 * 1024)\n",
        "        init_mm_embedding_cache(embedding_cache_size * 1024 * 1024)\n"
        "\n"
        "        return KVCacheBuildResult(\n"
        "            is_hybrid_swa=is_hybrid_swa,\n"
        "            is_hybrid_ssm=is_hybrid_ssm,\n"
        "            sliding_window_size=sliding_window_size,\n"
        "            full_tokens_per_layer=full_tokens_per_layer,\n"
        "            swa_tokens_per_layer=swa_tokens_per_layer,\n"
        "            req_to_token_pool=req_to_token_pool,\n"
        "            token_to_kv_pool_allocator=token_to_kv_pool_allocator,\n"
        "            disable_radix_cache=disable_radix_cache,\n"
        "            tree_cache=tree_cache,\n"
        "        )\n",
    )

    return text


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    kvc = wt / "python/sglang/srt/managers/scheduler_components/kv_cache.py"

    # 1. Locate and rewrite method in place.
    text = sched.read_text()
    s, e = find_method_lines(
        text, class_name="Scheduler", method_name="init_cache_with_memory_pool"
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    new_method = _rewrite_method_body(method_text)
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # 2. Update caller.
    text = replace_call_site(
        text,
        old="        # Init cache and memory pool\n"
        "        self.init_cache_with_memory_pool()\n",
        new=INLINE_CALLER_REPLACEMENT,
    )

    # 3. Import KVCacheBuildResult so the @staticmethod body's
    # ``return KVCacheBuildResult(...)`` resolves at runtime.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components import kv_cache\n",
        addition="from sglang.srt.managers.scheduler_components.kv_cache import KVCacheBuildResult\n",
    )

    sched.write_text(text)

    # 4. Append KVCacheBuildResult + imports to kv_cache.py.
    kvc_text = kvc.read_text()
    kvc_text = insert_after(
        kvc_text,
        anchor="logger = logging.getLogger(__name__)\n",
        addition="\n" + KVCACHE_HEADER_INSERT,
    )
    kvc.write_text(kvc_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
