#!/usr/bin/env python3
"""Inplace prep for ``introduce-pool-stats-observer``: create the empty
``SchedulerPoolStatsObserver`` class skeleton (+ move ``PoolStats`` dataclass)
into ``scheduler_components/pool_stats_observer.py``. Instantiate in
``Scheduler.__init__`` with Callable getter injection for runtime-mutable
``last_batch`` / ``running_batch`` state. Convert the 12 stats methods in
the runtime_checker mixin to ``@staticmethod`` with
``self: "SchedulerPoolStatsObserver"`` type annotation; do the 7 privacy
flips (drop leading ``_``); rewrite body reads
``self.last_batch`` / ``self.running_batch`` →
``self.get_last_batch()`` / ``self.get_running_batch()``.

Internal sibling calls inside method bodies (e.g.
``self.active_pool_idxs()`` / ``self._get_swa_token_info()``) are written
as **class-qualified** calls ``SchedulerRuntimeCheckerMixin.<method>(self)``
during prep because: while the @staticmethods physically live on
``SchedulerRuntimeCheckerMixin`` but receive a ``SchedulerPoolStatsObserver``
instance as ``self`` (via the type-flip), unqualified ``self.foo(...)``
lookup on a ``SchedulerPoolStatsObserver`` would fail at runtime. The move
commit strips the ``SchedulerRuntimeCheckerMixin.`` prefix and the
explicit ``self`` positional once the methods are physically on the new
class. This is a pragmatic body-bytes deviation, documented here.

Bodies otherwise byte-identical wrt the post-move state (modulo the
``@staticmethod`` decorator drop, the ``self: "SchedulerPoolStatsObserver"``
→ bare ``self`` annotation, and the sibling-call qualification strip).
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

ID = "introduce-pool-stats-observer-prep"
SUBJECT = "Stage pool-stats sampling for handoff to SchedulerPoolStatsObserver"
BODY = """\
Inplace prep for the ``introduce-pool-stats-observer`` mech move.

- Create ``scheduler_components/pool_stats_observer.py`` containing the
  ``PoolStats`` dataclass (relocated verbatim from
  ``scheduler_runtime_checker_mixin.py``) + an empty
  ``SchedulerPoolStatsObserver`` class skeleton (5 collaborators + 6 configs
  + 2 Callable getters, no methods yet).
- Instantiate ``self.pool_stats_observer = SchedulerPoolStatsObserver(...)``
  in ``Scheduler.__init__`` just before ``self.is_initializing = False``.
  Runtime-mutable ``last_batch`` / ``running_batch`` are injected as
  ``get_last_batch`` / ``get_running_batch`` Callable getters
  (CLAUDE.md §4 form).
- Mixin file imports ``PoolStats`` from the new module (mixin still defines
  the 12 stats methods until the move commit).
- 7 privacy flips (drop leading ``_``): ``_streaming_session_count`` /
  ``_active_pool_idxs`` / 5 ``_session_held_*``. ``get_pool_stats`` and the
  4 ``_get_*_token_info`` keep their existing names.
- 12 methods on ``SchedulerRuntimeCheckerMixin`` retyped to ``@staticmethod``
  with ``self: "SchedulerPoolStatsObserver"`` type annotation.
- Body reads of ``self.last_batch`` / ``self.running_batch`` are rewritten
  to ``self.get_last_batch()`` / ``self.get_running_batch()`` Callable
  getter calls. No per-call ``last_batch`` / ``running_batch`` kwargs.
- Sibling calls inside the 12 prep-form @staticmethods use the qualified
  form ``SchedulerRuntimeCheckerMixin.<method>(self)`` because the methods
  physically live on the mixin during prep but receive a
  ``SchedulerPoolStatsObserver`` as ``self``. The move commit strips the
  ``SchedulerRuntimeCheckerMixin.`` prefix and the explicit ``self``
  positional. This is a pragmatic body-bytes deviation, documented here.
- Callers updated to ``self.<method>(self.pool_stats_observer)`` form
  (mixin-internal MRO dispatch routes through the @staticmethod). No
  caller-side ``last_batch`` / ``running_batch`` kwargs.
- ``test/registered/unit/managers/test_scheduler_pause_generation.py``:
  update import of ``PoolStats`` to the new module.

The 12 methods stay inside ``SchedulerRuntimeCheckerMixin`` in this commit;
physical cut + paste into ``SchedulerPoolStatsObserver`` body happens in
``introduce-pool-stats-observer-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Target file: PoolStats dataclass moves verbatim (cut + paste). Class
# skeleton: ctor + fields + 2 Callable getters. The methods land here in
# the move commit.
TARGET_FILE_HEADER = '''\
from __future__ import annotations  # noqa: F401

import dataclasses  # noqa: F401
from dataclasses import dataclass  # noqa: F401
from typing import Callable, List, Optional, Tuple  # noqa: F401


# ``SchedulerStats`` is referenced only for the ``update_scheduler_stats``
# annotation; importing the type directly would cause a circular import in
# practice, so leave it as a forward reference.
class SchedulerStats: ...  # type: ignore[no-redef]


'''


SKELETON_CLASS = '''\
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
        get_last_batch: Callable,
        get_running_batch: Callable,
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
        self.get_last_batch = get_last_batch
        self.get_running_batch = get_running_batch
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
            get_last_batch=lambda: self.last_batch,
            get_running_batch=lambda: self.running_batch,
        )

"""


# Each entry: (old_method_name, new_method_block).
# The new block already has @staticmethod, the type-flipped ``self:
# "SchedulerPoolStatsObserver"`` annotation, post-flip name, and body
# rewrites: ``self.last_batch`` / ``self.running_batch`` reads are
# rewritten as ``self.get_last_batch()`` / ``self.get_running_batch()``
# Callable getter calls; sibling calls use the qualified
# ``SchedulerRuntimeCheckerMixin.<flipped_name>(self)`` form so the
# runtime lookup resolves correctly while the methods still live there.
PREP_METHOD_BLOCKS = {
    "_streaming_session_count": '''\
    @staticmethod
    def streaming_session_count(self: "SchedulerPoolStatsObserver") -> int:
        return sum(
            1
            for session in self.session_controller.sessions.values()
            if session.streaming
        )

''',
    "_active_pool_idxs": '''\
    @staticmethod
    def active_pool_idxs(self: "SchedulerPoolStatsObserver") -> set:
        """Pool idxs currently owned by reqs in last_batch / running_batch.

        Used to decide which session slots' KV is owned by batch reqs
        (and thus counted via uncached_size, not session_held).
        """
        idxs = set()
        for batch in [self.get_last_batch(), self.get_running_batch()]:
            if batch is None or batch.is_empty():
                continue
            for req in batch.reqs:
                if req.req_pool_idx is not None:
                    idxs.add(req.req_pool_idx)
        return idxs

''',
    "_session_held_tokens": '''\
    @staticmethod
    def session_held_tokens(self: "SchedulerPoolStatsObserver") -> int:
        return self.tree_cache.session_held_tokens(
            SchedulerRuntimeCheckerMixin.active_pool_idxs(self)
        )

''',
    "_session_held_full_tokens": '''\
    @staticmethod
    def session_held_full_tokens(self: "SchedulerPoolStatsObserver") -> int:
        return self.tree_cache.session_held_full_tokens(
            SchedulerRuntimeCheckerMixin.active_pool_idxs(self)
        )

''',
    "_session_held_swa_tokens": '''\
    @staticmethod
    def session_held_swa_tokens(self: "SchedulerPoolStatsObserver") -> int:
        return self.tree_cache.session_held_swa_tokens(
            SchedulerRuntimeCheckerMixin.active_pool_idxs(self)
        )

''',
    "_session_held_req_count": '''\
    @staticmethod
    def session_held_req_count(self: "SchedulerPoolStatsObserver") -> int:
        return self.tree_cache.session_held_req_count()

''',
    "_session_held_mamba_slots": '''\
    @staticmethod
    def session_held_mamba_slots(self: "SchedulerPoolStatsObserver") -> int:
        return self.tree_cache.session_held_mamba_slots(
            SchedulerRuntimeCheckerMixin.active_pool_idxs(self)
        )

''',
    "get_pool_stats": '''\
    @staticmethod
    def get_pool_stats(self: "SchedulerPoolStatsObserver") -> PoolStats:
        if self.is_hybrid_swa:
            pool_stats = SchedulerRuntimeCheckerMixin._get_swa_token_info(self)
        elif self.is_hybrid_ssm:
            pool_stats = SchedulerRuntimeCheckerMixin._get_mamba_token_info(self)
        else:
            pool_stats = SchedulerRuntimeCheckerMixin._get_token_info(self)

        if self.enable_hisparse:
            pool_stats = SchedulerRuntimeCheckerMixin._get_hisparse_token_info(self, pool_stats)

        # swa + ssm can coexist: overlay mamba fields onto swa stats
        if self.is_hybrid_ssm:
            mamba_stats = SchedulerRuntimeCheckerMixin._get_mamba_token_info(self)
            pool_stats.is_hybrid_ssm = True
            pool_stats.mamba_num_used = mamba_stats.mamba_num_used
            pool_stats.mamba_usage = mamba_stats.mamba_usage
            pool_stats.mamba_available_size = mamba_stats.mamba_available_size
            pool_stats.mamba_evictable_size = mamba_stats.mamba_evictable_size

        return pool_stats

''',
    "_get_token_info": '''\
    @staticmethod
    def _get_token_info(self: "SchedulerPoolStatsObserver") -> PoolStats:
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

''',
    "_get_hisparse_token_info": '''\
    @staticmethod
    def _get_hisparse_token_info(self: "SchedulerPoolStatsObserver", pool_stats: PoolStats) -> PoolStats:
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

''',
    "_get_mamba_token_info": '''\
    @staticmethod
    def _get_mamba_token_info(self: "SchedulerPoolStatsObserver"):
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

''',
    "_get_swa_token_info": '''\
    @staticmethod
    def _get_swa_token_info(self: "SchedulerPoolStatsObserver") -> PoolStats:
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

''',
}


# Order of methods in the mixin file (top-to-bottom). We replace inplace,
# preserving relative order, so the final file lays out the same as the
# post-move target's METHODS_BODY section.
METHOD_ORDER = [
    "_streaming_session_count",
    "_active_pool_idxs",
    "_session_held_tokens",
    "_session_held_full_tokens",
    "_session_held_swa_tokens",
    "_session_held_req_count",
    "_session_held_mamba_slots",
    "get_pool_stats",
    "_get_token_info",
    "_get_hisparse_token_info",
    "_get_mamba_token_info",
    "_get_swa_token_info",
]


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    metrics_mixin = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/pool_stats_observer.py"

    src_text = src.read_text()

    # 1. Cut PoolStats dataclass from mixin file (verbatim move to target).
    s, e = find_class_lines(src_text, class_name="PoolStats")
    lines = src_text.splitlines(keepends=True)
    pool_stats_block = "".join(lines[s:e]).rstrip() + "\n"
    del lines[s:e]
    src_text = "".join(lines)

    # 2. Replace each of the 12 mixin methods with the prep-form @staticmethod
    # block (bottom-up to keep line ranges valid).
    for name in reversed(METHOD_ORDER):
        s, e = find_method_lines(
            src_text, class_name="SchedulerRuntimeCheckerMixin", method_name=name
        )
        lines = src_text.splitlines(keepends=True)
        new_block = PREP_METHOD_BLOCKS[name]
        src_text = "".join(lines[:s]) + new_block + "".join(lines[e:])

    # 3. Add PoolStats import to mixin (it now lives in the new module).
    src_text = insert_after(
        src_text,
        anchor="from sglang.srt.utils.watchdog import WatchdogRaw\n",
        addition="\nfrom sglang.srt.managers.scheduler_components.pool_stats_observer import PoolStats\n",
    )
    # Add TYPE_CHECKING import for the new TargetClass so the
    # ``self: "SchedulerPoolStatsObserver"`` annotation resolves under pyflakes.
    if "from sglang.srt.managers.scheduler_components.pool_stats_observer import SchedulerPoolStatsObserver" not in src_text:
        src_text = src_text.replace(
            "if TYPE_CHECKING:\n",
            "if TYPE_CHECKING:\n"
            "    from sglang.srt.managers.scheduler_components.pool_stats_observer import SchedulerPoolStatsObserver\n",
            1,
        )
    src.write_text(src_text)

    # 4. Build the new target file: header + PoolStats dataclass + empty class
    # skeleton (methods land here in the move commit).
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_FILE_HEADER + pool_stats_block + "\n" + SKELETON_CLASS)

    # 5. Scheduler: add import + ctor instantiation.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.profiler_manager import (\n    SchedulerProfilerManager,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.pool_stats_observer import (\n"
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

    # 6. Hot-path callsites in scheduler.py (1 run_batch + 4 in
    # _maybe_log_idle_metrics / on_idle methods moved here in C8).
    text = text.replace(
        "            max_pool_usage = self.get_pool_stats().get_max_pool_usage()\n",
        "            max_pool_usage = self.get_pool_stats(\n"
        "                self.pool_stats_observer,\n"
        "            ).get_max_pool_usage()\n",
    )
    text = text.replace(
        "        self.get_pool_stats().update_scheduler_stats(self.stats)\n",
        "        self.get_pool_stats(\n"
        "            self.pool_stats_observer,\n"
        "        ).update_scheduler_stats(self.stats)\n",
    )
    text = text.replace(
        "        self.stats.num_streaming_sessions = self._streaming_session_count()\n",
        "        self.stats.num_streaming_sessions = self.streaming_session_count(\n"
        "            self.pool_stats_observer,\n"
        "        )\n",
    )
    text = text.replace(
        "        self.stats.streaming_session_held_tokens = self._session_held_tokens()\n",
        "        self.stats.streaming_session_held_tokens = self.session_held_tokens(\n"
        "            self.pool_stats_observer,\n"
        "        )\n",
    )
    text = text.replace(
        "            has_leak, messages = self._check_all_pools(self.get_pool_stats())\n",
        "            has_leak, messages = self._check_all_pools(\n"
        "                self.get_pool_stats(\n"
        "                    self.pool_stats_observer,\n"
        "                )\n"
        "            )\n",
    )
    sched.write_text(text)

    # 7. Internal callsites in the runtime_checker mixin (still mixin until the
    # move commit). 7 callsites in _check_*_pool / _check_req_pool /
    # create_scheduler_watchdog (dump_info).
    text = src.read_text()
    text = text.replace(
        "        ps = self.get_pool_stats()\n",
        "        ps = self.get_pool_stats(\n"
        "            self.pool_stats_observer,\n"
        "        )\n",
    )
    text = text.replace(
        "        session_req_count = self._session_held_req_count()\n",
        "        session_req_count = self.session_held_req_count(\n"
        "            self.pool_stats_observer,\n"
        "        )\n",
    )
    text = text.replace(
        "            session_held = self._session_held_full_tokens()\n",
        "            session_held = self.session_held_full_tokens(\n"
        "                self.pool_stats_observer,\n"
        "            )\n",
    )
    text = text.replace(
        "            session_held = self._session_held_tokens()\n",
        "            session_held = self.session_held_tokens(\n"
        "                self.pool_stats_observer,\n"
        "            )\n",
    )
    text = text.replace(
        "            self._session_held_swa_tokens(),\n",
        "            self.session_held_swa_tokens(\n"
        "                self.pool_stats_observer,\n"
        "            ),\n",
    )
    text = text.replace(
        "            self._session_held_mamba_slots(),\n",
        "            self.session_held_mamba_slots(\n"
        "                self.pool_stats_observer,\n"
        "            ),\n",
    )
    # create_scheduler_watchdog dump_info: scheduler.get_pool_stats().
    text = text.replace(
        "        _, messages = scheduler._check_all_pools(scheduler.get_pool_stats())\n",
        "        _, messages = scheduler._check_all_pools(\n"
        "            scheduler.get_pool_stats(\n"
        "                scheduler.pool_stats_observer,\n"
        "            )\n"
        "        )\n",
    )
    src.write_text(text)

    # 8. Metrics mixin callsites (5).
    text = metrics_mixin.read_text()
    text = text.replace(
        "        pool_stats = self.get_pool_stats()\n",
        "        pool_stats = self.get_pool_stats(\n"
        "            self.pool_stats_observer,\n"
        "        )\n",
    )
    text = text.replace(
        "        num_used_tokens, kv_token_usage = self.get_pool_stats().get_kv_token_stats()\n",
        "        num_used_tokens, kv_token_usage = self.get_pool_stats(\n"
        "            self.pool_stats_observer,\n"
        "        ).get_kv_token_stats()\n",
    )
    text = text.replace(
        "            self.stats.num_streaming_sessions = self._streaming_session_count()\n",
        "            self.stats.num_streaming_sessions = self.streaming_session_count(\n"
        "                self.pool_stats_observer,\n"
        "            )\n",
    )
    text = text.replace(
        "            self.stats.streaming_session_held_tokens = self._session_held_tokens()\n",
        "            self.stats.streaming_session_held_tokens = self.session_held_tokens(\n"
        "                self.pool_stats_observer,\n"
        "            )\n",
    )
    metrics_mixin.write_text(text)

    # 9. Test file: update the PoolStats import (the dataclass moved this commit).
    test_pause = wt / "test/registered/unit/managers/test_scheduler_pause_generation.py"
    if test_pause.exists():
        ttext = test_pause.read_text()
        ttext = ttext.replace(
            "from sglang.srt.managers.scheduler_runtime_checker_mixin import PoolStats\n",
            "from sglang.srt.managers.scheduler_components.pool_stats_observer import PoolStats\n",
        )
        test_pause.write_text(ttext)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
