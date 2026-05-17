#!/usr/bin/env python3
"""Inplace prep for ``introduce-invariant-checker``: build the
``SchedulerInvariantChecker`` class skeleton (ctor with Callable getter
injection for runtime-mutable Scheduler state + 2 mutable counter fields),
instantiate on Scheduler, type-flip 10 check methods in
``SchedulerRuntimeCheckerMixin`` to ``@staticmethod`` with
``self: "SchedulerInvariantChecker"``, rewrite body reads of
``self.last_batch`` / ``self.running_batch`` /
``self.pool_stats_observer.get_pool_stats(...)`` through the Callable
getters, and rewrite callers to the sister staticmethod-on-mixin form
(``self.foo(self.invariant_checker, args)``).

Body bytes byte-identical wrt the post-move state (modulo decorator +
``self: SchedulerInvariantChecker`` → bare ``self`` simplification in the
move commit, and sibling-call ``SchedulerRuntimeCheckerMixin.<m>(self,...)``
→ ``self.<m>(...)`` strip in the move commit). The 10 methods physically
stay in the mixin during prep; cut+paste happens in
``introduce-invariant-checker-move``.

Pragmatic deviation: per the
``MECH_COMMIT_SPLIT.md`` Callable-getter-injection section, runtime-mutable
state (``last_batch`` / ``running_batch``) and the
``pool_stats_observer.get_pool_stats(...)`` derived view are injected as
``Callable[[], T]`` getters in the ctor (not per-call kwargs). The
``pool_stats_observer`` itself remains a static ctor field so the
session_held_*_tokens calls inside ``_check_full_pool`` / ``_check_swa_pool``
/ ``_check_mamba_pool`` stay readable. The ``count_*_leak_warnings``
counter fields are fresh-initialised here (they had no static definition on
``Scheduler`` previously — ``raise_error_or_warn`` creates them dynamically
via ``setattr``).
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

ID = "introduce-invariant-checker-prep"
SUBJECT = "Introduce SchedulerInvariantChecker to own invariant-check state"
BODY = """\
Inplace prep for the ``introduce-invariant-checker`` mech move.

- Create ``scheduler_components/invariant_checker.py`` with an empty
  ``SchedulerInvariantChecker`` class skeleton (ctor only; no methods
  yet). Ctor takes the static fields (collaborators + configs +
  ``pool_stats_observer``) plus the Callable getters
  (``get_last_batch`` / ``get_running_batch``) plus the mutable counter
  fields ``count_req_pool_leak_warnings`` / ``count_memory_leak_warnings``
  fresh-initialised to 0.
- Instantiate ``self.invariant_checker = SchedulerInvariantChecker(...)``
  in ``Scheduler.__init__`` just after ``self.pool_stats_observer`` so
  the sister composition dep resolves.
- In ``SchedulerRuntimeCheckerMixin``, convert the instance methods to
  ``@staticmethod`` with ``self: "SchedulerInvariantChecker"`` type
  annotation. (``_check_pool_invariant`` is already a stateless
  ``@staticmethod``.) Body reads of runtime-mutable ``Scheduler`` state
  are rewritten through the Callable getters: ``self.last_batch`` →
  ``self.get_last_batch()``, ``self.running_batch`` →
  ``self.get_running_batch()``.
- Callers rewritten to the sister staticmethod-on-mixin form
  ``self.<method>(self.invariant_checker, ...)`` (mirrors
  ``introduce-load-inquirer-prep``'s pattern; the move commit reduces
  this to ``self.invariant_checker.<method>(...)``). Callsites in
  ``scheduler.py``: ``_check_all_pools`` / ``_report_leak`` /
  ``_check_req_pool`` / ``_check_tree_cache`` (in ``on_idle`` /
  ``_maybe_log_idle_metrics``); ``self_check_during_busy`` (in
  ``run_batch``, direct + overlap variant). Also a callsite in the
  ``create_scheduler_watchdog`` free function (moved into
  ``scheduler.py`` in the pre-prep commit).

The invariant-check methods stay inside ``SchedulerRuntimeCheckerMixin``
in this commit; physical cut + paste into ``SchedulerInvariantChecker``
body happens in ``introduce-invariant-checker-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


TARGET_FILE_HEADER = '''\
from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple, TYPE_CHECKING

from sglang.srt.disaggregation.utils import DisaggregationMode
from sglang.srt.environ import envs
from sglang.srt.managers.scheduler_components.pool_stats_observer import (
    PoolStats,
    SchedulerPoolStatsObserver,
)
from sglang.srt.mem_cache.allocator import BaseTokenToKVPoolAllocator
from sglang.srt.mem_cache.base_prefix_cache import BasePrefixCache
from sglang.srt.mem_cache.memory_pool import ReqToTokenPool
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils.common import ceil_align, raise_error_or_warn


logger = logging.getLogger(__name__)


'''


SKELETON_CLASS = '''\
@dataclass(kw_only=True, slots=True)
class SchedulerInvariantChecker:
    is_hybrid_swa: bool
    is_hybrid_ssm: bool
    disaggregation_mode: DisaggregationMode
    page_size: int
    full_tokens_per_layer: Optional[int]
    swa_tokens_per_layer: Optional[int]
    max_total_num_tokens: int
    server_args: ServerArgs
    tree_cache: BasePrefixCache
    token_to_kv_pool_allocator: BaseTokenToKVPoolAllocator
    req_to_token_pool: ReqToTokenPool
    pool_stats_observer: SchedulerPoolStatsObserver
    get_last_batch: Callable
    get_running_batch: Callable
    count_req_pool_leak_warnings: int = 0
    count_memory_leak_warnings: int = 0
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
            get_last_batch=lambda: self.last_batch,
            get_running_batch=lambda: self.running_batch,
        )

"""


# Runtime-mutable Scheduler state references inside method bodies that need
# to be rewritten through ``self.get_X()`` Callable getters. Each pair is a
# fragment-level replacement applied to each method body in turn.
BODY_GETTER_REPLACEMENTS = [
    # _check_full_pool / _check_swa_pool / _check_mamba_pool: rewrite the
    # session_held_*_tokens kwargs through the getters. The
    # ``pool_stats_observer`` attribute remains a static ctor field so the
    # call shape is unchanged otherwise.
    (
        "                last_batch=self.last_batch,\n"
        "                running_batch=self.running_batch,\n",
        "                last_batch=self.get_last_batch(),\n"
        "                running_batch=self.get_running_batch(),\n",
    ),
    # _get_total_uncached_sizes: rewrite the 3 last_batch / running_batch
    # reads (one ``batches = [self.last_batch]``, two in the membership /
    # is_empty test, one ``batches.append(self.running_batch)``).
    (
        "        batches = [self.last_batch]\n"
        "        if (\n"
        "            self.running_batch not in (None, self.last_batch)\n"
        "            and not self.running_batch.is_empty()\n"
        "        ):\n"
        "            batches.append(self.running_batch)\n",
        "        batches = [self.get_last_batch()]\n"
        "        if (\n"
        "            self.get_running_batch() not in (None, self.get_last_batch())\n"
        "            and not self.get_running_batch().is_empty()\n"
        "        ):\n"
        "            batches.append(self.get_running_batch())\n",
    ),
    # self_check_during_busy: ``if self.last_batch is None: return`` head guard.
    (
        "        if self.last_batch is None:\n",
        "        if self.get_last_batch() is None:\n",
    ),
]


def _type_flip_method(text: str, *, method_name: str, original_sig: str,
                      new_sig: str) -> str:
    """Type-flip a SchedulerRuntimeCheckerMixin method to @staticmethod with
    ``self: "SchedulerInvariantChecker"``. Apply ``BODY_GETTER_REPLACEMENTS``
    inside the method body (anchors absent from a given method body are
    skipped — they belong to sibling methods)."""
    s, e = find_method_lines(
        text, class_name="SchedulerRuntimeCheckerMixin", method_name=method_name
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if original_sig not in method_text:
        raise RuntimeError(f"{method_name} signature anchor mismatch")
    new_method = method_text.replace(original_sig, new_sig)
    for old, new in BODY_GETTER_REPLACEMENTS:
        if old not in new_method:
            continue
        new_method = new_method.replace(old, new)
    return "".join(lines[:s]) + new_method + "".join(lines[e:])


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/invariant_checker.py"

    # 1. Create new target file (skeleton: header + empty class).
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_FILE_HEADER + SKELETON_CLASS)

    # 2. Type-flip the 9 instance methods to @staticmethod + retype +
    #    Callable getter rewrites. ``_check_pool_invariant`` is already a
    #    stateless @staticmethod and needs no retype.
    text = src.read_text()
    text = _type_flip_method(
        text,
        method_name="_check_full_pool",
        original_sig=(
            "    def _check_full_pool(\n"
            "        self: Scheduler, ps: PoolStats, uncached: int = 0\n"
            "    ) -> Tuple[bool, str]:"
        ),
        new_sig=(
            "    @staticmethod\n"
            "    def _check_full_pool(\n"
            "        self: \"SchedulerInvariantChecker\", ps: PoolStats, uncached: int = 0\n"
            "    ) -> Tuple[bool, str]:"
        ),
    )
    text = _type_flip_method(
        text,
        method_name="_check_swa_pool",
        original_sig=(
            "    def _check_swa_pool(\n"
            "        self: Scheduler, ps: PoolStats, uncached: int = 0\n"
            "    ) -> Tuple[bool, str]:"
        ),
        new_sig=(
            "    @staticmethod\n"
            "    def _check_swa_pool(\n"
            "        self: \"SchedulerInvariantChecker\", ps: PoolStats, uncached: int = 0\n"
            "    ) -> Tuple[bool, str]:"
        ),
    )
    text = _type_flip_method(
        text,
        method_name="_check_mamba_pool",
        original_sig=(
            "    def _check_mamba_pool(self: Scheduler, ps: PoolStats) -> Tuple[bool, str]:"
        ),
        new_sig=(
            "    @staticmethod\n"
            "    def _check_mamba_pool(\n"
            "        self: \"SchedulerInvariantChecker\", ps: PoolStats\n"
            "    ) -> Tuple[bool, str]:"
        ),
    )
    text = _type_flip_method(
        text,
        method_name="_get_total_uncached_sizes",
        original_sig=(
            "    def _get_total_uncached_sizes(self: Scheduler) -> Tuple[int, int]:"
        ),
        new_sig=(
            "    @staticmethod\n"
            "    def _get_total_uncached_sizes(\n"
            "        self: \"SchedulerInvariantChecker\",\n"
            "    ) -> Tuple[int, int]:"
        ),
    )
    text = _type_flip_method(
        text,
        method_name="self_check_during_busy",
        original_sig=(
            "    def self_check_during_busy(self: Scheduler):"
        ),
        new_sig=(
            "    @staticmethod\n"
            "    def self_check_during_busy(self: \"SchedulerInvariantChecker\"):"
        ),
    )
    text = _type_flip_method(
        text,
        method_name="_check_req_pool",
        original_sig=(
            "    def _check_req_pool(self: Scheduler):"
        ),
        new_sig=(
            "    @staticmethod\n"
            "    def _check_req_pool(self: \"SchedulerInvariantChecker\"):"
        ),
    )
    text = _type_flip_method(
        text,
        method_name="_report_leak",
        original_sig=(
            "    def _report_leak(self: Scheduler, pool_name: str, token_msg: str):"
        ),
        new_sig=(
            "    @staticmethod\n"
            "    def _report_leak(\n"
            "        self: \"SchedulerInvariantChecker\", pool_name: str, token_msg: str\n"
            "    ):"
        ),
    )
    text = _type_flip_method(
        text,
        method_name="_check_all_pools",
        original_sig=(
            "    def _check_all_pools(\n"
            "        self: Scheduler, ps: PoolStats, uncached: int = 0\n"
            "    ) -> Tuple[bool, List[str]]:"
        ),
        new_sig=(
            "    @staticmethod\n"
            "    def _check_all_pools(\n"
            "        self: \"SchedulerInvariantChecker\", ps: PoolStats, uncached: int = 0\n"
            "    ) -> Tuple[bool, List[str]]:"
        ),
    )
    text = _type_flip_method(
        text,
        method_name="_check_tree_cache",
        original_sig=(
            "    def _check_tree_cache(self: Scheduler):"
        ),
        new_sig=(
            "    @staticmethod\n"
            "    def _check_tree_cache(self: \"SchedulerInvariantChecker\"):"
        ),
    )

    # Sibling calls inside the prep-form @staticmethods must use the
    # qualified ``SchedulerRuntimeCheckerMixin.<method>(self, ...)`` form
    # because, at runtime, ``self`` is a ``SchedulerInvariantChecker``
    # instance and lacks the (still-mixin-defined) sibling check methods on
    # its MRO. The move commit strips the qualifier once the methods are
    # physically on ``SchedulerInvariantChecker``.
    sibling_qualifier_rewrites = [
        # self_check_during_busy → _get_total_uncached_sizes / _check_full_pool / _check_swa_pool / _report_leak.
        (
            "        full_uncached, swa_uncached = self._get_total_uncached_sizes()\n",
            "        full_uncached, swa_uncached = SchedulerRuntimeCheckerMixin._get_total_uncached_sizes(self)\n",
        ),
        (
            "        full_leak, full_msg = self._check_full_pool(ps, uncached=full_uncached)\n",
            "        full_leak, full_msg = SchedulerRuntimeCheckerMixin._check_full_pool(self, ps, uncached=full_uncached)\n",
        ),
        (
            "            swa_leak, swa_msg = self._check_swa_pool(ps, uncached=swa_uncached)\n",
            "            swa_leak, swa_msg = SchedulerRuntimeCheckerMixin._check_swa_pool(self, ps, uncached=swa_uncached)\n",
        ),
        # _check_full_pool / _check_swa_pool / _check_mamba_pool → _check_pool_invariant.
        (
            "        return self._check_pool_invariant(\n",
            "        return SchedulerRuntimeCheckerMixin._check_pool_invariant(\n",
        ),
        (
            "        leak, msg = self._check_pool_invariant(\n",
            "        leak, msg = SchedulerRuntimeCheckerMixin._check_pool_invariant(\n",
        ),
        # _check_all_pools → _check_full_pool / _check_swa_pool / _check_mamba_pool.
        (
            "        full_leak, full_msg = self._check_full_pool(ps, uncached=uncached)\n",
            "        full_leak, full_msg = SchedulerRuntimeCheckerMixin._check_full_pool(self, ps, uncached=uncached)\n",
        ),
        (
            "            swa_leak, swa_msg = self._check_swa_pool(ps)\n",
            "            swa_leak, swa_msg = SchedulerRuntimeCheckerMixin._check_swa_pool(self, ps)\n",
        ),
        (
            "            mamba_leak, mamba_msg = self._check_mamba_pool(ps)\n",
            "            mamba_leak, mamba_msg = SchedulerRuntimeCheckerMixin._check_mamba_pool(self, ps)\n",
        ),
    ]
    for old, new in sibling_qualifier_rewrites:
        if old in text:
            text = text.replace(old, new)

    # Add TYPE_CHECKING import for the new TargetClass so the
    # ``self: "SchedulerInvariantChecker"`` annotation resolves under pyflakes.
    if "from sglang.srt.managers.scheduler_components.invariant_checker import SchedulerInvariantChecker" not in text:
        text = text.replace(
            "if TYPE_CHECKING:\n",
            "if TYPE_CHECKING:\n"
            "    from sglang.srt.managers.scheduler_components.invariant_checker import SchedulerInvariantChecker\n",
            1,
        )
    src.write_text(text)

    # 3. Scheduler: add import + ctor instantiation.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor=(
            "from sglang.srt.managers.scheduler_components.pool_stats_observer import (\n"
            "    SchedulerPoolStatsObserver,\n"
            ")\n"
        ),
        addition=(
            "from sglang.srt.managers.scheduler_components.invariant_checker import (\n"
            "    SchedulerInvariantChecker,\n"
            ")\n"
        ),
    )
    text = insert_after(
        text,
        anchor=(
            "        self.pool_stats_observer = SchedulerPoolStatsObserver(\n"
            "            tree_cache=self.tree_cache,\n"
            "            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,\n"
            "            req_to_token_pool=self.req_to_token_pool,\n"
            "            session_controller=self.session_controller,\n"
            "            hisparse_coordinator=self.hisparse_coordinator,\n"
            "            is_hybrid_swa=self.is_hybrid_swa,\n"
            "            is_hybrid_ssm=self.is_hybrid_ssm,\n"
            "            enable_hisparse=self.enable_hisparse,\n"
            "            full_tokens_per_layer=self.full_tokens_per_layer,\n"
            "            swa_tokens_per_layer=self.swa_tokens_per_layer,\n"
            "            max_total_num_tokens=self.max_total_num_tokens,\n"
            "            get_last_batch=lambda: self.last_batch,\n"
            "            get_running_batch=lambda: self.running_batch,\n"
            "        )\n\n"
        ),
        addition=SCHEDULER_INIT_INSERT,
    )

    # 4. Rewrite the 5 Scheduler callsites + 1 watchdog callsite to bind the
    #    @staticmethod to ``self.invariant_checker`` (mirrors the load-inquirer
    #    pattern; the move commit reduces to ``self.invariant_checker.<m>(...)``).

    # on_idle: _check_all_pools (after C9 Callable injection, get_pool_stats() is no-arg).
    text = text.replace(
        "            has_leak, messages = self._check_all_pools(\n"
        "                self.pool_stats_observer.get_pool_stats()\n"
        "            )\n",
        "            has_leak, messages = self._check_all_pools(\n"
        "                self.invariant_checker,\n"
        "                self.pool_stats_observer.get_pool_stats(),\n"
        "            )\n",
    )
    # on_idle: _report_leak.
    text = text.replace(
        '                self._report_leak("pool", "\\n".join(messages))\n',
        '                self._report_leak(self.invariant_checker, "pool", "\\n".join(messages))\n',
    )
    # on_idle: _check_req_pool.
    text = text.replace(
        "            self._check_req_pool()\n",
        "            self._check_req_pool(self.invariant_checker)\n",
    )
    # on_idle: _check_tree_cache.
    text = text.replace(
        "        self._check_tree_cache()\n",
        "        self._check_tree_cache(self.invariant_checker)\n",
    )
    # run_batch / event_loop_overlap: self_check_during_busy (appears twice).
    text = text.replace(
        "                self.self_check_during_busy()\n",
        "                self.self_check_during_busy(self.invariant_checker)\n",
    )

    # watchdog dump_info (post C9 Callable injection: get_pool_stats() no-arg).
    text = text.replace(
        "        _, messages = scheduler._check_all_pools(\n"
        "            scheduler.pool_stats_observer.get_pool_stats()\n"
        "        )\n",
        "        _, messages = scheduler._check_all_pools(\n"
        "            scheduler.invariant_checker,\n"
        "            scheduler.pool_stats_observer.get_pool_stats(),\n"
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
