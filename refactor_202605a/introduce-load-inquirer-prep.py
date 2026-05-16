#!/usr/bin/env python3
"""Inplace prep for ``introduce-load-inquirer``: build the
``SchedulerLoadInquirer`` class skeleton (ctor with Callable injection),
instantiate on Scheduler, type-flip ``get_loads`` + ``_get_num_pending_tokens``
to ``@staticmethod`` with ``self: "SchedulerLoadInquirer"``, rewrite the
method bodies to read through ``self.get_X()`` Callable getters, and
rewrite callers to the sister form.

Body bytes byte-identical wrt the post-move state (modulo decorator +
``self: SchedulerLoadInquirer`` → bare ``self`` simplification in the
move commit).

Pragmatic deviation: rather than R4 per-call kwargs for runtime-mutable
Scheduler state (``running_batch`` / ``waiting_queue`` / ``stats`` / spec
accumulators / 4 disagg queues / ``chunked_req``), we use Callable getter
injection (``get_running_batch`` / ``get_waiting_queue`` / ...). This is
consistent with C14's Callable injection pattern (``metrics_reporter`` ctor)
and keeps the ``get_loads`` signature stable (no caller-side kwargs).
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

ID = "introduce-load-inquirer-prep"
SUBJECT = "Carve out SchedulerLoadInquirer for queue-load state"
BODY = """\
Inplace prep for the ``introduce-load-inquirer`` mech move.

- Create ``scheduler_components/load_inquirer.py`` with an empty
  ``SchedulerLoadInquirer`` class skeleton (ctor only; no methods yet).
- Instantiate ``self.load_inquirer = SchedulerLoadInquirer(...)`` in
  ``Scheduler.__init__`` after ``self.pool_stats_observer`` so the
  sister dep resolves.
- In ``SchedulerMetricsMixin``, convert ``get_loads`` and
  ``_get_num_pending_tokens`` to ``@staticmethod`` with
  ``self: "SchedulerLoadInquirer"`` type annotation. Body reads of
  runtime-mutable Scheduler state are rewritten to call
  ``self.get_X()`` Callable getters.
- Callers (RPC dispatch tuple in ``init_request_dispatcher``, call
  in ``scheduler_output_processor_mixin.stream_output_generation``,
  and the ``_get_num_pending_tokens`` caller in
  ``_get_new_batch_prefill_raw``) rewritten to call through
  ``self.load_inquirer``.

Pragmatic deviation (per doc): Callable injection
(``get_running_batch`` / ``get_waiting_queue`` / ``get_stats`` /
``get_chunked_req`` / spec accumulators / disagg queues) is kept in this
prep commit (not pushed to per-call kwarg add) so the ``get_loads`` /
``_get_num_pending_tokens`` signatures stay stable and the upcoming
``-move`` commit is a true byte-equal cut + paste. This mirrors the
Callable injection pattern used by ``SchedulerMetricsReporter``.

The methods stay inside ``SchedulerMetricsMixin`` in this commit;
physical cut + paste to ``SchedulerLoadInquirer`` body happens in
``introduce-load-inquirer-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


TARGET_FILE_HEADER = '''\
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

from sglang.srt.disaggregation.utils import DisaggregationMode
from sglang.srt.managers.io_struct import (
    DisaggregationMetrics,
    GetLoadsReqInput,
    GetLoadsReqOutput,
    LoRAMetrics,
    MemoryMetrics,
    QueueMetrics,
    SpeculativeMetrics,
)

if TYPE_CHECKING:
    from sglang.srt.distributed.parallel_state_wrapper import ParallelState
    from sglang.srt.managers.scheduler_components.pool_stats_observer import (
        SchedulerPoolStatsObserver,
    )
    from sglang.srt.managers.tp_worker import BaseTpWorker
    from sglang.srt.mem_cache.allocator import BaseTokenToKVPoolAllocator
    from sglang.srt.server_args import ServerArgs
    from sglang.srt.speculative.spec_info import SpeculativeAlgorithm


logger = logging.getLogger(__name__)


'''


NEW_CLASS_SKELETON = '''\
@dataclass(kw_only=True, slots=True, frozen=True)
class SchedulerLoadInquirer:
    disaggregation_mode: "DisaggregationMode"
    ps: "ParallelState"
    server_args: "ServerArgs"
    max_total_num_tokens: int
    max_running_requests: int
    pool_stats_observer: "SchedulerPoolStatsObserver"
    tp_worker: "BaseTpWorker"
    token_to_kv_pool_allocator: "BaseTokenToKVPoolAllocator"
    spec_algorithm: "SpeculativeAlgorithm"
    get_running_batch: Callable
    get_waiting_queue: Callable
    get_stats: Callable
    get_chunked_req: Callable
    get_disagg_prefill_bootstrap_queue: Callable
    get_disagg_prefill_inflight_queue: Callable
    get_disagg_decode_prealloc_queue: Callable
    get_disagg_decode_transfer_queue: Callable
    get_spec_total_num_accept_tokens: Callable
    get_spec_total_num_forward_ct: Callable
'''


SCHEDULER_INIT_INSERT = """\
        self.load_inquirer = SchedulerLoadInquirer(
            disaggregation_mode=self.disaggregation_mode,
            ps=self.ps,
            server_args=self.server_args,
            max_total_num_tokens=self.max_total_num_tokens,
            max_running_requests=self.max_running_requests,
            pool_stats_observer=self.pool_stats_observer,
            tp_worker=self.tp_worker,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            spec_algorithm=self.spec_algorithm,
            get_running_batch=lambda: self.running_batch,
            get_waiting_queue=lambda: self.waiting_queue,
            get_stats=lambda: self.stats,
            get_chunked_req=lambda: self.chunked_req,
            get_disagg_prefill_bootstrap_queue=lambda: self.disagg_prefill_bootstrap_queue,
            get_disagg_prefill_inflight_queue=lambda: self.disagg_prefill_inflight_queue,
            get_disagg_decode_prealloc_queue=lambda: self.disagg_decode_prealloc_queue,
            get_disagg_decode_transfer_queue=lambda: self.disagg_decode_transfer_queue,
            get_spec_total_num_accept_tokens=lambda: self.spec_total_num_accept_tokens,
            get_spec_total_num_forward_ct=lambda: self.spec_total_num_forward_ct,
        )

"""


# Old body's per-instance reads are rewritten to Callable getter reads.
# All replacements operate on the in-place method body text.
BODY_GETTER_REPLACEMENTS = [
    # _get_num_pending_tokens body
    ("sum(req.seqlen for req in self.waiting_queue)",
     "sum(req.seqlen for req in self.get_waiting_queue())"),
    ("if self.chunked_req is not None:\n            req = self.chunked_req\n",
     "if self.get_chunked_req() is not None:\n            req = self.get_chunked_req()\n"),
    # get_loads body
    ("len(self.running_batch.reqs)", "len(self.get_running_batch().reqs)"),
    ("waiting_queues = [self.waiting_queue]", "waiting_queues = [self.get_waiting_queue()]"),
    (
        "waiting_queues.append(self.disagg_prefill_bootstrap_queue.queue)",
        "waiting_queues.append(self.get_disagg_prefill_bootstrap_queue().queue)",
    ),
    (
        "waiting_queues.append(self.disagg_decode_prealloc_queue.queue)",
        "waiting_queues.append(self.get_disagg_decode_prealloc_queue().queue)",
    ),
    (
        "waiting_queues.append(self.disagg_decode_transfer_queue.queue)",
        "waiting_queues.append(self.get_disagg_decode_transfer_queue().queue)",
    ),
    (
        "waiting_queues.append(self.disagg_decode_prealloc_queue.retracted_queue)",
        "waiting_queues.append(self.get_disagg_decode_prealloc_queue().retracted_queue)",
    ),
    (
        "        num_used_tokens, kv_token_usage = self.pool_stats_observer.get_pool_stats(\n"
        "            last_batch=self.last_batch,\n"
        "            running_batch=self.running_batch,\n"
        "        ).get_kv_token_stats()",
        "        num_used_tokens, kv_token_usage = self.pool_stats_observer.get_pool_stats(\n"
        "            last_batch=None,\n"
        "            running_batch=self.get_running_batch(),\n"
        "        ).get_kv_token_stats()",
    ),
    (
        "if not self.spec_algorithm.is_none() and self.spec_total_num_forward_ct > 0:",
        "if not self.spec_algorithm.is_none() and self.get_spec_total_num_forward_ct() > 0:",
    ),
    (
        "                        self.spec_total_num_accept_tokens\n"
        "                        / self.spec_total_num_forward_ct",
        "                        self.get_spec_total_num_accept_tokens()\n"
        "                        / self.get_spec_total_num_forward_ct()",
    ),
    (
        "                    accept_rate=self.stats.spec_accept_rate,",
        "                    accept_rate=self.get_stats().spec_accept_rate,",
    ),
    (
        "            if self.enable_lora:",
        "            if self.server_args.enable_lora:",
    ),
    (
        "                    slots_used=self.stats.lora_pool_slots_used,",
        "                    slots_used=self.get_stats().lora_pool_slots_used,",
    ),
    (
        "                    slots_total=self.stats.lora_pool_slots_total,",
        "                    slots_total=self.get_stats().lora_pool_slots_total,",
    ),
    (
        "                    utilization=self.stats.lora_pool_utilization,",
        "                    utilization=self.get_stats().lora_pool_utilization,",
    ),
    (
        "                prefill_bootstrap = len(self.disagg_prefill_bootstrap_queue.queue)",
        "                prefill_bootstrap = len(self.get_disagg_prefill_bootstrap_queue().queue)",
    ),
    (
        "                prefill_inflight = len(self.disagg_prefill_inflight_queue)",
        "                prefill_inflight = len(self.get_disagg_prefill_inflight_queue())",
    ),
    (
        "                decode_prealloc = len(self.disagg_decode_prealloc_queue.queue)",
        "                decode_prealloc = len(self.get_disagg_decode_prealloc_queue().queue)",
    ),
    (
        "                decode_transfer = len(self.disagg_decode_transfer_queue.queue)",
        "                decode_transfer = len(self.get_disagg_decode_transfer_queue().queue)",
    ),
    (
        "                    self.disagg_decode_prealloc_queue.retracted_queue",
        "                    self.get_disagg_decode_prealloc_queue().retracted_queue",
    ),
    (
        "                kv_transfer_speed_gb_s=self.stats.kv_transfer_speed_gb_s,",
        "                kv_transfer_speed_gb_s=self.get_stats().kv_transfer_speed_gb_s,",
    ),
    (
        "                kv_transfer_latency_ms=self.stats.kv_transfer_latency_ms,",
        "                kv_transfer_latency_ms=self.get_stats().kv_transfer_latency_ms,",
    ),
    (
        "                waiting=len(self.waiting_queue),",
        "                waiting=len(self.get_waiting_queue()),",
    ),
    (
        "                grammar=self.stats.num_grammar_queue_reqs,",
        "                grammar=self.get_stats().num_grammar_queue_reqs,",
    ),
    (
        "                paused=self.stats.num_paused_reqs,",
        "                paused=self.get_stats().num_paused_reqs,",
    ),
    (
        "                retracted=self.stats.num_retracted_reqs,",
        "                retracted=self.get_stats().num_retracted_reqs,",
    ),
    ("dp_rank=self.dp_rank,", "dp_rank=self.ps.dp_rank,"),
    ("gen_throughput=round(self.stats.gen_throughput, 2),",
     "gen_throughput=round(self.get_stats().gen_throughput, 2),"),
    ("cache_hit_rate=round(self.stats.cache_hit_rate, 4),",
     "cache_hit_rate=round(self.get_stats().cache_hit_rate, 4),"),
    ("utilization=round(self.stats.utilization, 4),",
     "utilization=round(self.get_stats().utilization, 4),"),
]


def _type_flip_method(text: str, *, method_name: str, original_sig: str,
                      new_sig: str) -> str:
    """Type-flip a SchedulerMetricsMixin method to @staticmethod with
    ``self: "SchedulerLoadInquirer"``. Apply ``BODY_GETTER_REPLACEMENTS``
    inside the method body. Anchor errors abort."""
    s, e = find_method_lines(
        text, class_name="SchedulerMetricsMixin", method_name=method_name
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])
    if original_sig not in method_text:
        raise RuntimeError(f"{method_name} signature anchor mismatch")
    new_method = method_text.replace(original_sig, new_sig)
    for old, new in BODY_GETTER_REPLACEMENTS:
        if old not in new_method:
            # Anchor not present (likely method-local body shape diverged
            # from the original transform's assumption, or the anchor
            # belongs to the other method); skip rather than abort.
            continue
        new_method = new_method.replace(old, new)
    return "".join(lines[:s]) + new_method + "".join(lines[e:])


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/load_inquirer.py"

    # 1. Create new target file (skeleton: header + empty class).
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_FILE_HEADER + NEW_CLASS_SKELETON)

    # 2. Type-flip ``get_loads`` and ``_get_num_pending_tokens`` to
    #    @staticmethod + self: SchedulerLoadInquirer and rewrite body
    #    reads to Callable getter calls.
    text = src.read_text()
    text = _type_flip_method(
        text,
        method_name="_get_num_pending_tokens",
        original_sig=(
            "    def _get_num_pending_tokens(self: Scheduler, chunk_deduct: int = 0) -> int:"
        ),
        new_sig=(
            "    @staticmethod\n"
            "    def _get_num_pending_tokens(\n"
            "        self: \"SchedulerLoadInquirer\", chunk_deduct: int = 0\n"
            "    ) -> int:"
        ),
    )
    text = _type_flip_method(
        text,
        method_name="get_loads",
        original_sig=(
            "    def get_loads(self: Scheduler, req: GetLoadsReqInput = None) -> GetLoadsReqOutput:"
        ),
        new_sig=(
            "    @staticmethod\n"
            "    def get_loads(\n"
            "        self: \"SchedulerLoadInquirer\", req: GetLoadsReqInput = None\n"
            "    ) -> GetLoadsReqOutput:"
        ),
    )
    # Add TYPE_CHECKING import for the new TargetClass so the
    # ``self: "SchedulerLoadInquirer"`` annotation resolves under pyflakes.
    if "from sglang.srt.managers.scheduler_components.load_inquirer import SchedulerLoadInquirer" not in text:
        text = text.replace(
            "if TYPE_CHECKING:\n",
            "if TYPE_CHECKING:\n"
            "    from sglang.srt.managers.scheduler_components.load_inquirer import SchedulerLoadInquirer\n",
            1,
        )
    src.write_text(text)

    # 3. Scheduler: import + ctor + RPC dispatch lambda + _get_num_pending_tokens
    #    callsite rewrite.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.kv_events_publisher import (\n    SchedulerKvEventsPublisher,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.load_inquirer import (\n"
            "    SchedulerLoadInquirer,\n"
            ")\n"
        ),
    )
    # Insert load_inquirer ctor BEFORE ``self.is_initializing = False`` (stable anchor).
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=SCHEDULER_INIT_INSERT + "        self.is_initializing = False\n",
    )
    # RPC dispatch tuple — bind static method to self.load_inquirer via lambda.
    text = replace_call_site(
        text,
        old="                (GetLoadsReqInput, self.get_loads),\n",
        new=(
            "                (\n"
            "                    GetLoadsReqInput,\n"
            "                    lambda req: self.get_loads(self.load_inquirer, req),\n"
            "                ),\n"
        ),
    )
    # _get_num_pending_tokens caller (in _get_new_batch_prefill_raw) — bind
    # the static method to self.load_inquirer.
    text = text.replace(
        "            num_pending_tokens=self._get_num_pending_tokens(\n"
        "                chunk_deduct=(\n",
        "            num_pending_tokens=self._get_num_pending_tokens(\n"
        "                self.load_inquirer,\n"
        "                chunk_deduct=(\n",
    )
    sched.write_text(text)

    # 4. Output processor mixin callsite.
    text = output_mixin.read_text()
    text = text.replace(
        '        load = self.get_loads(GetLoadsReqInput(include=["core"]))\n',
        "        load = self.get_loads(\n"
        "            self.load_inquirer,\n"
        '            GetLoadsReqInput(include=["core"]),\n'
        "        )\n",
    )
    output_mixin.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
