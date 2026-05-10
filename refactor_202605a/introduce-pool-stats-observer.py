#!/usr/bin/env python3
"""1:N split #1 of ``SchedulerRuntimeCheckerMixin``: introduce
``SchedulerPoolStatsObserver`` at
``scheduler_components/observability/pool_stats_observer.py``.

12 stats methods + the ``PoolStats`` dataclass move to the new class. 7
privacy flips (drop leading ``_``): ``_streaming_session_count``,
``_active_pool_idxs``, 5 ``_session_held_*``. Per-call kwargs ``last_batch``
+ ``running_batch`` added to: ``active_pool_idxs``, ``session_held_tokens``,
``session_held_full_tokens``, ``session_held_swa_tokens``,
``session_held_mamba_slots``, ``get_pool_stats`` (R4 kwarg add).
``session_held_req_count`` and ``streaming_session_count`` need no per-call
kwargs.

Callers updated across: ``scheduler.py`` (3 hot-path call + watchdog),
``scheduler_runtime_checker_mixin.py`` (7 internal calls inside
``_check_*_pool`` methods that themselves move to ``InvariantChecker`` in
the next commit), ``observability/scheduler_metrics_mixin.py`` (5 callsites
in ``report_*_stats`` methods).

The runtime_checker mixin still exists; its check methods + the
``create_scheduler_watchdog`` free function move out in the next 2 commits.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_class_lines, find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-pool-stats-observer"
SUBJECT = "Introduce SchedulerPoolStatsObserver (split #1 of runtime_checker mixin)"
BODY = """\
Pull 12 stats methods + the ``PoolStats`` dataclass out of
``SchedulerRuntimeCheckerMixin`` into a new class
``SchedulerPoolStatsObserver`` at
``scheduler_components/observability/pool_stats_observer.py``.

Privacy flips (7) drop the leading ``_``:
``_streaming_session_count`` / ``_active_pool_idxs`` / 5 ``_session_held_*``.

Per-call kwargs (R4 kwarg add): ``last_batch`` + ``running_batch`` on
``active_pool_idxs`` / ``session_held_tokens`` / ``session_held_full_tokens``
/ ``session_held_swa_tokens`` / ``session_held_mamba_slots`` /
``get_pool_stats``. ``session_held_req_count`` and
``streaming_session_count`` take no per-call kwargs.

Ctor narrow kwargs (per CLAUDE.md ch4): 5 collaborators (tree_cache,
token_to_kv_pool_allocator, req_to_token_pool, session_controller,
hisparse_coordinator) + 6 configs (is_hybrid_swa, is_hybrid_ssm,
enable_hisparse, full_tokens_per_layer, swa_tokens_per_layer,
max_total_num_tokens). No scheduler_ref back-reference.

Caller rewrites:
- ``scheduler.py`` ``run_batch`` hot path: 1 ``self.get_pool_stats()``.
- ``scheduler.py`` ``on_idle`` / ``_maybe_log_idle_metrics`` (moved to
  Scheduler in the previous commit): 4 callsites.
- ``scheduler.py`` ``create_scheduler_watchdog`` free function: 1 callsite.
- ``scheduler_runtime_checker_mixin.py`` (still partly mixin until the next
  commit): 7 internal callsites inside ``_check_*_pool`` methods, which
  themselves move to ``SchedulerInvariantChecker`` next.
- ``observability/scheduler_metrics_mixin.py``: 5 callsites in
  ``report_prefill_stats`` / ``report_decode_stats`` and
  ``calculate_utilization``.

No method renames beyond the 7 privacy flips. No body restructuring beyond
the per-call kwarg substitutions.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


NEW_CLASS_HEADER = '''\
class SchedulerPoolStatsObserver:
    """Read-only KV / req / session pool statistics. Composition target on
    Scheduler (``self.pool_stats_observer``)."""

    def __init__(
        self,
        *,
        tree_cache,
        token_to_kv_pool_allocator,
        req_to_token_pool,
        session_controller,
        hisparse_coordinator,
        is_hybrid_swa: bool,
        is_hybrid_ssm: bool,
        enable_hisparse: bool,
        full_tokens_per_layer,
        swa_tokens_per_layer,
        max_total_num_tokens: int,
    ) -> None:
        self.tree_cache = tree_cache
        self.token_to_kv_pool_allocator = token_to_kv_pool_allocator
        self.req_to_token_pool = req_to_token_pool
        self.session_controller = session_controller
        self.hisparse_coordinator = hisparse_coordinator
        self.is_hybrid_swa = is_hybrid_swa
        self.is_hybrid_ssm = is_hybrid_ssm
        self.enable_hisparse = enable_hisparse
        self.full_tokens_per_layer = full_tokens_per_layer
        self.swa_tokens_per_layer = swa_tokens_per_layer
        self.max_total_num_tokens = max_total_num_tokens

'''


# 12 method bodies post-transform. We rebuild as a single ``METHODS_BODY``
# string. Easier than text-replacing a hundred individual self.X reads.
METHODS_BODY = '''\
    def streaming_session_count(self) -> int:
        return sum(
            1
            for session in self.session_controller.sessions.values()
            if session.streaming
        )

    def active_pool_idxs(self, *, last_batch, running_batch) -> set:
        """Pool idxs currently owned by reqs in last_batch / running_batch.

        Used to decide which session slots' KV is owned by batch reqs
        (and thus counted via uncached_size, not session_held).
        """
        idxs = set()
        for batch in [last_batch, running_batch]:
            if batch is None or batch.is_empty():
                continue
            for req in batch.reqs:
                if req.req_pool_idx is not None:
                    idxs.add(req.req_pool_idx)
        return idxs

    def session_held_tokens(self, *, last_batch, running_batch) -> int:
        return self.tree_cache.session_held_tokens(
            self.active_pool_idxs(last_batch=last_batch, running_batch=running_batch)
        )

    def session_held_full_tokens(self, *, last_batch, running_batch) -> int:
        return self.tree_cache.session_held_full_tokens(
            self.active_pool_idxs(last_batch=last_batch, running_batch=running_batch)
        )

    def session_held_swa_tokens(self, *, last_batch, running_batch) -> int:
        return self.tree_cache.session_held_swa_tokens(
            self.active_pool_idxs(last_batch=last_batch, running_batch=running_batch)
        )

    def session_held_req_count(self) -> int:
        return self.tree_cache.session_held_req_count()

    def session_held_mamba_slots(self, *, last_batch, running_batch) -> int:
        return self.tree_cache.session_held_mamba_slots(
            self.active_pool_idxs(last_batch=last_batch, running_batch=running_batch)
        )

    def get_pool_stats(self, *, last_batch, running_batch) -> PoolStats:
        if self.is_hybrid_swa:
            pool_stats = self._get_swa_token_info()
        elif self.is_hybrid_ssm:
            pool_stats = self._get_mamba_token_info()
        else:
            pool_stats = self._get_token_info()

        if self.enable_hisparse:
            pool_stats = self._get_hisparse_token_info(pool_stats)

        # swa + ssm can coexist: overlay mamba fields onto swa stats
        if self.is_hybrid_ssm:
            mamba_stats = self._get_mamba_token_info()
            pool_stats.is_hybrid_ssm = True
            pool_stats.mamba_num_used = mamba_stats.mamba_num_used
            pool_stats.mamba_usage = mamba_stats.mamba_usage
            pool_stats.mamba_available_size = mamba_stats.mamba_available_size
            pool_stats.mamba_evictable_size = mamba_stats.mamba_evictable_size

        return pool_stats

    def _get_token_info(self) -> PoolStats:
        available_size = self.token_to_kv_pool_allocator.available_size()
        evictable_size = self.tree_cache.evictable_size()
        num_used = self.max_total_num_tokens - (available_size + evictable_size)
        token_usage = num_used / self.max_total_num_tokens
        return PoolStats(
            full_num_used=num_used,
            full_token_usage=token_usage,
            full_available_size=available_size,
            full_evictable_size=evictable_size,
        )

    def _get_hisparse_token_info(self, pool_stats: PoolStats) -> PoolStats:
        if self.enable_hisparse and self.hisparse_coordinator is not None:
            h = self.hisparse_coordinator.get_token_stats()
            return dataclasses.replace(
                pool_stats,
                is_hisparse=True,
                hisparse_device_tokens=h.device_tokens,
                hisparse_device_token_usage=h.device_token_usage,
                hisparse_host_tokens=h.host_tokens,
                hisparse_host_token_usage=h.host_token_usage,
            )
        return pool_stats

    def _get_mamba_token_info(self):
        is_mamba_radix_cache = (
            self.tree_cache.supports_mamba() and self.tree_cache.is_tree_cache()
        )
        full_available_size = self.token_to_kv_pool_allocator.available_size()
        full_evictable_size = (
            self.tree_cache.full_evictable_size() if is_mamba_radix_cache else 0
        )
        mamba_available_size = self.req_to_token_pool.mamba_pool.available_size()
        mamba_evictable_size = (
            self.tree_cache.mamba_evictable_size() if is_mamba_radix_cache else 0
        )
        full_num_used = self.token_to_kv_pool_allocator.size - (
            full_available_size + full_evictable_size
        )
        mamba_num_used = self.req_to_token_pool.mamba_pool.size - (
            mamba_available_size + mamba_evictable_size
        )
        full_token_usage = full_num_used / self.token_to_kv_pool_allocator.size
        mamba_usage = mamba_num_used / self.req_to_token_pool.mamba_pool.size

        return PoolStats(
            is_hybrid_ssm=True,
            full_num_used=full_num_used,
            full_token_usage=full_token_usage,
            full_available_size=full_available_size,
            full_evictable_size=full_evictable_size,
            mamba_num_used=mamba_num_used,
            mamba_usage=mamba_usage,
            mamba_available_size=mamba_available_size,
            mamba_evictable_size=mamba_evictable_size,
        )

    def _get_swa_token_info(self) -> PoolStats:
        full_available_size = self.token_to_kv_pool_allocator.full_available_size()
        full_evictable_size = self.tree_cache.full_evictable_size()
        swa_available_size = self.token_to_kv_pool_allocator.swa_available_size()
        swa_evictable_size = self.tree_cache.swa_evictable_size()
        full_num_used = self.full_tokens_per_layer - (
            full_available_size + full_evictable_size
        )
        swa_num_used = self.swa_tokens_per_layer - (
            swa_available_size + swa_evictable_size
        )
        # FIXME(hisparse): host-backup transiently over-releases the device pool
        # counter, producing negative full_num_used / swa_num_used. We clamp to 0
        # to keep token_usage / leak checks sane, but the underlying accounting
        # bug should be fixed so the clamp can go away.
        if self.enable_hisparse:
            full_num_used = max(0, full_num_used)
            swa_num_used = max(0, swa_num_used)
        full_token_usage = full_num_used / self.full_tokens_per_layer
        swa_token_usage = swa_num_used / self.swa_tokens_per_layer

        return PoolStats(
            is_hybrid_swa=True,
            full_num_used=full_num_used,
            full_token_usage=full_token_usage,
            full_available_size=full_available_size,
            full_evictable_size=full_evictable_size,
            swa_num_used=swa_num_used,
            swa_token_usage=swa_token_usage,
            swa_available_size=swa_available_size,
            swa_evictable_size=swa_evictable_size,
        )
'''


SCHEDULER_INIT_INSERT = """\
        self.pool_stats_observer = SchedulerPoolStatsObserver(
            tree_cache=self.tree_cache,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            req_to_token_pool=self.req_to_token_pool,
            session_controller=self.session_controller,
            hisparse_coordinator=self.hisparse_coordinator,
            is_hybrid_swa=self.is_hybrid_swa,
            is_hybrid_ssm=self.is_hybrid_ssm,
            enable_hisparse=self.enable_hisparse,
            full_tokens_per_layer=self.full_tokens_per_layer,
            swa_tokens_per_layer=self.swa_tokens_per_layer,
            max_total_num_tokens=self.max_total_num_tokens,
        )

"""


# Build the ``pool_stats_observer.py`` content. We re-export ``PoolStats``
# (currently defined inside the runtime_checker mixin file) so the callers
# can ``from .pool_stats_observer import PoolStats``.
TARGET_FILE_HEADER = '''\
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import List, Optional, Tuple


# ``SchedulerStats`` is referenced only for the ``update_scheduler_stats``
# annotation; importing the type directly would cause a circular import in
# practice, so leave it as a forward reference.
class SchedulerStats: ...  # type: ignore[no-redef]


'''


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    metrics_mixin = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/observability/pool_stats_observer.py"

    src_text = src.read_text()

    # Cut the ``PoolStats`` dataclass from the mixin file (lines ~23-138 — its
    # full body including methods).
    s, e = find_class_lines(src_text, class_name="PoolStats")
    pool_stats_block = "\n".join(src_text.splitlines()[s:e]) + "\n"
    # Remove from source.
    new_src_lines = src_text.splitlines(keepends=True)
    del new_src_lines[s:e]
    src_text = "".join(new_src_lines)

    # Cut all 12 stats methods from SchedulerRuntimeCheckerMixin (bottom-up).
    for name in [
        "_get_swa_token_info",
        "_get_mamba_token_info",
        "_get_hisparse_token_info",
        "_get_token_info",
        "get_pool_stats",
        "_session_held_mamba_slots",
        "_session_held_req_count",
        "_session_held_swa_tokens",
        "_session_held_full_tokens",
        "_session_held_tokens",
        "_active_pool_idxs",
        "_streaming_session_count",
    ]:
        s, e = find_method_lines(
            src_text, class_name="SchedulerRuntimeCheckerMixin", method_name=name
        )
        lines = src_text.splitlines(keepends=True)
        del lines[s:e]
        src_text = "".join(lines)

    src.write_text(src_text)

    # Build target file: header + PoolStats + new class.
    target_text = TARGET_FILE_HEADER + pool_stats_block + "\n" + NEW_CLASS_HEADER + METHODS_BODY
    target.write_text(target_text)

    # Update Scheduler: import + ctor + 5 callsite rewrites in main file
    # (1 in run_batch + 4 in on_idle/_maybe_log_idle_metrics + 1 in watchdog).
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.observability.profiler_manager import (\n    SchedulerProfilerManager,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.observability.pool_stats_observer import (\n"
            "    PoolStats,\n"
            "    SchedulerPoolStatsObserver,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=SCHEDULER_INIT_INSERT + "        self.is_initializing = False\n",
    )

    # Hot-path callsites in scheduler.py (run_batch + watchdog + on_idle methods
    # moved here in C8).
    text = text.replace(
        "            max_pool_usage = self.get_pool_stats().get_max_pool_usage()\n",
        "            max_pool_usage = self.pool_stats_observer.get_pool_stats(\n"
        "                last_batch=self.last_batch, running_batch=self.running_batch\n"
        "            ).get_max_pool_usage()\n",
    )
    text = text.replace(
        "        self.get_pool_stats().update_scheduler_stats(self.stats)\n",
        "        self.pool_stats_observer.get_pool_stats(\n"
        "            last_batch=self.last_batch, running_batch=self.running_batch\n"
        "        ).update_scheduler_stats(self.stats)\n",
    )
    text = text.replace(
        "        self.stats.num_streaming_sessions = self._streaming_session_count()\n",
        "        self.stats.num_streaming_sessions = self.pool_stats_observer.streaming_session_count()\n",
    )
    text = text.replace(
        "        self.stats.streaming_session_held_tokens = self._session_held_tokens()\n",
        "        self.stats.streaming_session_held_tokens = self.pool_stats_observer.session_held_tokens(\n"
        "            last_batch=self.last_batch, running_batch=self.running_batch\n"
        "        )\n",
    )
    text = text.replace(
        "            has_leak, messages = self._check_all_pools(self.get_pool_stats())\n",
        "            has_leak, messages = self._check_all_pools(\n"
        "                self.pool_stats_observer.get_pool_stats(\n"
        "                    last_batch=self.last_batch, running_batch=self.running_batch\n"
        "                )\n"
        "            )\n",
    )
    sched.write_text(text)

    # Internal callsites in runtime_checker mixin (still mixin until C10
    # moves the check methods). 7 callsites in _check_*_pool / _check_req_pool
    # / dump_info inside watchdog.
    text = src.read_text()
    text = text.replace(
        "        ps = self.get_pool_stats()\n",
        "        ps = self.pool_stats_observer.get_pool_stats(\n"
        "            last_batch=self.last_batch, running_batch=self.running_batch\n"
        "        )\n",
    )
    text = text.replace(
        "        session_req_count = self._session_held_req_count()\n",
        "        session_req_count = self.pool_stats_observer.session_held_req_count()\n",
    )
    # Inside _check_full_pool / _check_swa_pool (private helpers): 3 occurrences
    # of self._session_held_full_tokens() / self._session_held_tokens().
    text = text.replace(
        "            session_held = self._session_held_full_tokens()\n",
        "            session_held = self.pool_stats_observer.session_held_full_tokens(\n"
        "                last_batch=self.last_batch, running_batch=self.running_batch\n"
        "            )\n",
    )
    text = text.replace(
        "            session_held = self._session_held_tokens()\n",
        "            session_held = self.pool_stats_observer.session_held_tokens(\n"
        "                last_batch=self.last_batch, running_batch=self.running_batch\n"
        "            )\n",
        # The same line appears twice in the original (in _check_swa_pool and
        # _check_mamba_pool); ``str.replace`` does both.
    )
    text = text.replace(
        "            self._session_held_swa_tokens(),\n",
        "            self.pool_stats_observer.session_held_swa_tokens(\n"
        "                last_batch=self.last_batch, running_batch=self.running_batch\n"
        "            ),\n",
    )
    text = text.replace(
        "            self._session_held_mamba_slots(),\n",
        "            self.pool_stats_observer.session_held_mamba_slots(\n"
        "                last_batch=self.last_batch, running_batch=self.running_batch\n"
        "            ),\n",
    )
    # create_scheduler_watchdog free function: scheduler.get_pool_stats().
    text = text.replace(
        "        _, messages = scheduler._check_all_pools(scheduler.get_pool_stats())\n",
        "        _, messages = scheduler._check_all_pools(\n"
        "            scheduler.pool_stats_observer.get_pool_stats(\n"
        "                last_batch=scheduler.last_batch, running_batch=scheduler.running_batch\n"
        "            )\n"
        "        )\n",
    )
    # The runtime_checker mixin still references ``PoolStats`` (which used to
    # be defined locally above the class). Add the import.
    text = insert_after(
        text,
        anchor="from sglang.srt.utils.watchdog import WatchdogRaw\n",
        addition="\nfrom sglang.srt.managers.scheduler_components.observability.pool_stats_observer import PoolStats\n",
    )
    src.write_text(text)

    # Metrics mixin callsites (5).
    text = metrics_mixin.read_text()
    # 2x ``pool_stats = self.get_pool_stats()`` in report_prefill_stats /
    # report_decode_stats.
    text = text.replace(
        "        pool_stats = self.get_pool_stats()\n",
        "        pool_stats = self.pool_stats_observer.get_pool_stats(\n"
        "            last_batch=self.last_batch, running_batch=self.running_batch\n"
        "        )\n",
    )
    # 1x ``num_used_tokens, kv_token_usage = self.get_pool_stats().get_kv_token_stats()``.
    text = text.replace(
        "        num_used_tokens, kv_token_usage = self.get_pool_stats().get_kv_token_stats()\n",
        "        num_used_tokens, kv_token_usage = self.pool_stats_observer.get_pool_stats(\n"
        "            last_batch=self.last_batch, running_batch=self.running_batch\n"
        "        ).get_kv_token_stats()\n",
    )
    # 2x ``self._streaming_session_count()`` / ``self._session_held_tokens()``.
    text = text.replace(
        "            self.stats.num_streaming_sessions = self._streaming_session_count()\n",
        "            self.stats.num_streaming_sessions = self.pool_stats_observer.streaming_session_count()\n",
    )
    text = text.replace(
        "            self.stats.streaming_session_held_tokens = self._session_held_tokens()\n",
        "            self.stats.streaming_session_held_tokens = self.pool_stats_observer.session_held_tokens(\n"
        "                last_batch=self.last_batch, running_batch=self.running_batch\n"
        "            )\n",
    )
    metrics_mixin.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
