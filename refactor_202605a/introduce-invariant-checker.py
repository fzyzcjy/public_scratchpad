#!/usr/bin/env python3
"""1:N split #2 of ``SchedulerRuntimeCheckerMixin``: introduce
``SchedulerInvariantChecker`` at
``scheduler_components/observability/invariant_checker.py``.

10 check methods move out. ``self.last_batch`` / ``self.running_batch`` reads
inside the method bodies become per-call ``last_batch`` / ``running_batch``
kwargs (R4 kwarg add). ``count_req_pool_leak_warnings`` /
``count_memory_leak_warnings`` are owned by the new class (``raise_error_or_warn``
target switches from Scheduler to InvariantChecker).

After this commit the runtime_checker mixin is empty except for the
module-level ``create_scheduler_watchdog`` free function — moved to
``scheduler.py`` in this same commit. The mixin file is then deleted.

Sister: ``pool_stats_observer`` injected via ctor.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_function_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-invariant-checker"
SUBJECT = "Introduce SchedulerInvariantChecker (split #2 of runtime_checker mixin); delete runtime_checker mixin file"
BODY = """\
Pull 10 check methods out of ``SchedulerRuntimeCheckerMixin`` into a new
``SchedulerInvariantChecker`` at
``scheduler_components/observability/invariant_checker.py``. Scheduler holds
it as ``self.invariant_checker``.

Ctor narrow kwargs (per CLAUDE.md ch4): 8 configs + 3 collaborators + 1
sister (``pool_stats_observer``). Owned: ``count_req_pool_leak_warnings`` /
``count_memory_leak_warnings`` (ownership migration from Scheduler — those
counters were lazily created via ``raise_error_or_warn`` setattr; now
explicit ``__init__`` fields).

``self.last_batch`` / ``self.running_batch`` reads in the original method
bodies (introduced by the previous commit's pool_stats_observer wiring)
become per-call ``last_batch`` / ``running_batch`` kwargs forwarded through
``self_check_during_busy`` / ``_check_all_pools`` / ``_check_full_pool`` /
``_check_swa_pool`` / ``_check_mamba_pool`` / ``_get_total_uncached_sizes``.

After this commit the original ``scheduler_runtime_checker_mixin.py`` file
contains only the module-level ``create_scheduler_watchdog`` free function;
that function is moved verbatim into ``scheduler.py`` (where its 2 callers
already live) and the mixin file is deleted.

3 callsites updated: ``on_idle`` (now on Scheduler main, post-C8) and the
1 ``self.self_check_during_busy()`` call in ``run_batch``.

No method renames; no privacy flips.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Full body of the new class. Bodies are the originals with:
#   - ``self.X`` reads → kwarg-or-ctor-field substitutions
#   - per-call kwargs added (last_batch / running_batch)
#   - ``self._sched.`` removed (no back-ref)
#   - ``self.pool_stats_observer.X`` for sister calls (already inserted by C9)
NEW_CLASS_BODY = '''\
class SchedulerInvariantChecker:
    """KV pool / req pool / tree_cache memory invariant checks.
    Composition target on Scheduler (``self.invariant_checker``)."""

    def __init__(
        self,
        *,
        is_hybrid_swa: bool,
        is_hybrid_ssm: bool,
        disaggregation_mode,
        page_size: int,
        full_tokens_per_layer,
        swa_tokens_per_layer,
        max_total_num_tokens: int,
        server_args,
        tree_cache,
        token_to_kv_pool_allocator,
        req_to_token_pool,
        pool_stats_observer,
    ) -> None:
        self.is_hybrid_swa = is_hybrid_swa
        self.is_hybrid_ssm = is_hybrid_ssm
        self.disaggregation_mode = disaggregation_mode
        self.page_size = page_size
        self.full_tokens_per_layer = full_tokens_per_layer
        self.swa_tokens_per_layer = swa_tokens_per_layer
        self.max_total_num_tokens = max_total_num_tokens
        self.server_args = server_args
        self.tree_cache = tree_cache
        self.token_to_kv_pool_allocator = token_to_kv_pool_allocator
        self.req_to_token_pool = req_to_token_pool
        self.pool_stats_observer = pool_stats_observer
        self.count_req_pool_leak_warnings: int = 0
        self.count_memory_leak_warnings: int = 0

    @staticmethod
    def _check_pool_invariant(
        *,
        pool_name: str,
        available: int,
        evictable: int,
        protected: int,
        session_held: int,
        total: int,
        uncached: int = 0,
    ) -> Tuple[bool, str]:
        """Check that available + evictable + protected + session_held + uncached == total."""
        accounted = available + evictable + protected + session_held + uncached
        if accounted != total:
            msg = (
                f"{pool_name} pool size mismatch: "
                f"available={available}, evictable={evictable}, "
                f"protected={protected}, session_held={session_held}, "
                f"uncached={uncached}, total={total}, accounted={accounted}, "
                f"diff={total - accounted}"
            )
            return True, msg
        return False, ""

    def _check_full_pool(
        self,
        *,
        ps: PoolStats,
        last_batch,
        running_batch,
        uncached: int = 0,
    ) -> Tuple[bool, str]:
        if self.is_hybrid_swa:
            available = ps.full_available_size
            evictable = ps.full_evictable_size
            protected = self.tree_cache.full_protected_size()
            session_held = self.pool_stats_observer.session_held_full_tokens(
                last_batch=last_batch, running_batch=running_batch
            )
            total = self.full_tokens_per_layer
        else:
            available = ps.full_available_size
            evictable = ps.full_evictable_size
            protected = self.tree_cache.protected_size()
            session_held = self.pool_stats_observer.session_held_tokens(
                last_batch=last_batch, running_batch=running_batch
            )
            total = self.max_total_num_tokens
        return self._check_pool_invariant(
            pool_name="full",
            available=available,
            evictable=evictable,
            protected=protected,
            session_held=session_held,
            total=total,
            uncached=uncached,
        )

    def _check_swa_pool(
        self,
        *,
        ps: PoolStats,
        last_batch,
        running_batch,
        uncached: int = 0,
    ) -> Tuple[bool, str]:
        available = ps.swa_available_size
        evictable = ps.swa_evictable_size
        protected = self.tree_cache.swa_protected_size()
        session_held = self.pool_stats_observer.session_held_swa_tokens(
            last_batch=last_batch, running_batch=running_batch
        )
        total = self.swa_tokens_per_layer
        return self._check_pool_invariant(
            pool_name="swa",
            available=available,
            evictable=evictable,
            protected=protected,
            session_held=session_held,
            total=total,
            uncached=uncached,
        )

    def _check_mamba_pool(
        self, *, ps: PoolStats, last_batch, running_batch
    ) -> Tuple[bool, str]:
        is_mamba_radix_cache = (
            self.tree_cache.supports_mamba() and self.tree_cache.is_tree_cache()
        )
        if is_mamba_radix_cache:
            mamba_available = self.req_to_token_pool.mamba_pool.available_size()
            mamba_evictable = self.tree_cache.mamba_evictable_size()
            mamba_protected = self.tree_cache.mamba_protected_size()
            mamba_total = self.req_to_token_pool.mamba_pool.size
            session_held = self.pool_stats_observer.session_held_mamba_slots(
                last_batch=last_batch, running_batch=running_batch
            )
            return self._check_pool_invariant(
                pool_name="mamba",
                available=mamba_available,
                evictable=mamba_evictable,
                protected=mamba_protected,
                session_held=session_held,
                total=mamba_total,
            )
        return False, ""

    def _get_total_uncached_sizes(
        self, *, last_batch, running_batch
    ) -> Tuple[int, int]:
        """Sum of (uncached) tokens across last_batch + running_batch reqs.

        Returns (full_uncached, swa_uncached) — for non-hybrid_swa configs the
        swa_uncached is 0.
        """
        full_uncached = 0
        swa_uncached = 0
        for batch in [last_batch, running_batch]:
            if batch is None or batch.is_empty():
                continue
            for req in batch.reqs:
                cached = req.prefix_indices.shape[0] if req.prefix_indices is not None else 0
                req_full = req.seqlen - cached
                full_uncached += req_full
                if self.is_hybrid_swa:
                    swa_window = min(self.swa_tokens_per_layer, req_full)
                    swa_uncached += swa_window
        return full_uncached, swa_uncached

    def self_check_during_busy(self, *, last_batch, running_batch) -> None:
        """Check memory invariants during busy state (hot-path adjacent)."""
        if self.server_args.disable_radix_cache:
            return
        if self.server_args.speculative_num_steps is not None and self.server_args.speculative_num_steps > 0 and self.server_args.speculative_eagle_topk is not None and self.server_args.speculative_eagle_topk > 1:
            warnings.warn(
                "Pool invariant check is currently broken with eagle topk > 1.",
                UserWarning,
                stacklevel=2,
            )
            return
        ps = self.pool_stats_observer.get_pool_stats(
            last_batch=last_batch, running_batch=running_batch
        )
        full_uncached, swa_uncached = self._get_total_uncached_sizes(
            last_batch=last_batch, running_batch=running_batch
        )
        full_leak, full_msg = self._check_full_pool(
            ps=ps, last_batch=last_batch, running_batch=running_batch, uncached=full_uncached
        )
        if full_leak:
            self._report_leak("full", full_msg)
        if self.is_hybrid_swa:
            swa_leak, swa_msg = self._check_swa_pool(
                ps=ps, last_batch=last_batch, running_batch=running_batch, uncached=swa_uncached
            )
            if swa_leak:
                self._report_leak("swa", swa_msg)

    def _check_req_pool(self) -> None:
        session_req_count = self.pool_stats_observer.session_held_req_count()
        req_total_size = self.req_to_token_pool.size
        if len(self.req_to_token_pool.free_slots) + session_req_count != req_total_size:
            msg = (
                "req_to_token_pool memory leak detected!"
                f"available_size={len(self.req_to_token_pool.free_slots)}, "
                f"session_held={session_req_count}, "
                f"total_size={self.req_to_token_pool.size}\\n"
            )
            raise_error_or_warn(
                self,
                envs.SGLANG_ENABLE_STRICT_MEM_CHECK_DURING_IDLE.get(),
                "count_req_pool_leak_warnings",
                msg,
            )

    def _report_leak(self, pool_name: str, token_msg: str) -> None:
        msg = f"{pool_name} memory leak detected! {token_msg}"
        raise_error_or_warn(
            self,
            envs.SGLANG_ENABLE_STRICT_MEM_CHECK_DURING_IDLE.get(),
            "count_memory_leak_warnings",
            msg,
        )

    def _check_all_pools(
        self,
        *,
        ps: PoolStats,
        last_batch,
        running_batch,
        uncached: int = 0,
    ) -> Tuple[bool, List[str]]:
        """Check memory invariant across all pools. Returns (has_leak, messages)."""
        has_leak = False
        messages = []

        full_leak, full_msg = self._check_full_pool(
            ps=ps, last_batch=last_batch, running_batch=running_batch, uncached=uncached
        )
        has_leak |= full_leak
        messages.append(full_msg)

        if self.is_hybrid_swa:
            swa_leak, swa_msg = self._check_swa_pool(
                ps=ps, last_batch=last_batch, running_batch=running_batch
            )
            has_leak |= swa_leak
            messages.append(swa_msg)

        if self.is_hybrid_ssm and self.tree_cache.supports_mamba():
            mamba_leak, mamba_msg = self._check_mamba_pool(
                ps=ps, last_batch=last_batch, running_batch=running_batch
            )
            has_leak |= mamba_leak
            messages.append(mamba_msg)

        return has_leak, messages

    def _check_tree_cache(self) -> None:
        if (
            self.tree_cache.is_tree_cache()
            and (self.is_hybrid_swa and self.tree_cache.supports_swa())
            or (self.is_hybrid_ssm and self.tree_cache.supports_mamba())
        ):
            self.tree_cache.sanity_check()
'''


TARGET_FILE_HEADER = '''\
from __future__ import annotations

import warnings
from typing import List, Tuple

from sglang.srt.environ import envs
from sglang.srt.managers.scheduler_components.observability.pool_stats_observer import (
    PoolStats,
)
from sglang.srt.utils.common import raise_error_or_warn


'''


SCHEDULER_INIT_INSERT = """\
        self.invariant_checker = SchedulerInvariantChecker(
            is_hybrid_swa=self.is_hybrid_swa,
            is_hybrid_ssm=self.is_hybrid_ssm,
            disaggregation_mode=self.disaggregation_mode,
            page_size=self.page_size,
            full_tokens_per_layer=self.full_tokens_per_layer,
            swa_tokens_per_layer=self.swa_tokens_per_layer,
            max_total_num_tokens=self.max_total_num_tokens,
            server_args=self.server_args,
            tree_cache=self.tree_cache,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            req_to_token_pool=self.req_to_token_pool,
            pool_stats_observer=self.pool_stats_observer,
        )

"""


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/observability/invariant_checker.py"

    src_text = src.read_text()

    # Cut ``create_scheduler_watchdog`` free function — move verbatim to scheduler.py.
    s, e = find_function_lines(src_text, function_name="create_scheduler_watchdog")
    watchdog_lines = src_text.splitlines(keepends=True)[s:e]
    watchdog_text = "".join(watchdog_lines)
    # The watchdog body uses ``scheduler._check_all_pools(scheduler.get_pool_stats())``
    # — already rewritten by C9 to the pool_stats_observer form. Now also
    # rewrite ``scheduler._check_all_pools(...)`` → ``scheduler.invariant_checker._check_all_pools(...)``.
    watchdog_text = watchdog_text.replace(
        "scheduler._check_all_pools(\n"
        "            scheduler.pool_stats_observer.get_pool_stats(\n"
        "                last_batch=scheduler.last_batch, running_batch=scheduler.running_batch\n"
        "            )\n"
        "        )\n",
        "scheduler.invariant_checker._check_all_pools(\n"
        "            ps=scheduler.pool_stats_observer.get_pool_stats(\n"
        "                last_batch=scheduler.last_batch, running_batch=scheduler.running_batch\n"
        "            ),\n"
        "            last_batch=scheduler.last_batch,\n"
        "            running_batch=scheduler.running_batch,\n"
        "        )\n",
    )

    # Build the new invariant_checker.py file.
    target.write_text(TARGET_FILE_HEADER + NEW_CLASS_BODY)

    # Delete the original mixin file (now empty save for create_scheduler_watchdog,
    # which we're moving to scheduler.py).
    src.unlink()

    # Update Scheduler:
    # - drop the ``from .scheduler_runtime_checker_mixin import ...`` line
    # - add the new imports for SchedulerInvariantChecker + watchdog moved here
    # - drop ``SchedulerRuntimeCheckerMixin`` from inheritance list
    # - insert ctor instantiation
    # - insert ``create_scheduler_watchdog`` free function definition
    # - rewrite the 4 callsites in on_idle (moved here in C8) +
    #   self_check_during_busy in run_batch
    text = sched.read_text()

    # Remove the 3-line import block (multi-line ``from sglang...scheduler_runtime_checker_mixin import (\n    create_scheduler_watchdog,\n    ...,\n)``).
    text = text.replace(
        "from sglang.srt.managers.scheduler_runtime_checker_mixin import (\n"
        "    create_scheduler_watchdog,\n"
        "    SchedulerRuntimeCheckerMixin,\n"
        ")\n",
        "",
    )
    # Add new imports.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.observability.pool_stats_observer import (\n    PoolStats,\n    SchedulerPoolStatsObserver,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.observability.invariant_checker import (\n"
            "    SchedulerInvariantChecker,\n"
            ")\n"
        ),
    )
    # Drop ``SchedulerRuntimeCheckerMixin,`` from inheritance.
    text = replace_call_site(text, old="    SchedulerRuntimeCheckerMixin,\n", new="")
    # Insert ctor.
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=SCHEDULER_INIT_INSERT + "        self.is_initializing = False\n",
    )
    # Insert ``create_scheduler_watchdog`` just BEFORE ``class Scheduler(`` so it's
    # available at the module level.
    text = replace_call_site(
        text,
        old="class Scheduler(\n",
        new=watchdog_text + "\n\nclass Scheduler(\n",
    )
    # Rewrite callsites in on_idle / _maybe_log_idle_metrics (moved here in C8).
    # 4 callsites:
    #   1. self._check_all_pools(self.pool_stats_observer.get_pool_stats(...)) — already pool_stats wrapped by C9
    #   2. self._report_leak("pool", ...)
    #   3. self._check_req_pool()
    #   4. self._check_tree_cache()
    text = text.replace(
        "            has_leak, messages = self._check_all_pools(\n"
        "                self.pool_stats_observer.get_pool_stats(\n"
        "                    last_batch=self.last_batch, running_batch=self.running_batch\n"
        "                )\n"
        "            )\n",
        "            has_leak, messages = self.invariant_checker._check_all_pools(\n"
        "                ps=self.pool_stats_observer.get_pool_stats(\n"
        "                    last_batch=self.last_batch, running_batch=self.running_batch\n"
        "                ),\n"
        "                last_batch=self.last_batch,\n"
        "                running_batch=self.running_batch,\n"
        "            )\n",
    )
    text = text.replace(
        '                self._report_leak("pool", "\\n".join(messages))\n',
        '                self.invariant_checker._report_leak("pool", "\\n".join(messages))\n',
    )
    text = text.replace(
        "            self._check_req_pool()\n",
        "            self.invariant_checker._check_req_pool()\n",
    )
    text = text.replace(
        "        self._check_tree_cache()\n",
        "        self.invariant_checker._check_tree_cache()\n",
    )
    # self_check_during_busy callsite (in run_batch hot path).
    text = text.replace(
        "        self.self_check_during_busy()\n",
        "        self.invariant_checker.self_check_during_busy(\n"
        "            last_batch=self.last_batch, running_batch=self.running_batch\n"
        "        )\n",
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
