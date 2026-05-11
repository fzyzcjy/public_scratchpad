#!/usr/bin/env python3
"""Inplace prep for ``introduce-load-inquirer``: build the
``SchedulerLoadInquirer`` class skeleton (ctor only, NO methods yet),
instantiate on Scheduler, type-flip ``get_loads`` to ``@staticmethod``
with ``self: "SchedulerLoadInquirer"``, rewrite callers to sister form.

Body bytes byte-identical wrt the post-move state (modulo decorator +
``self: SchedulerLoadInquirer`` → bare ``self`` simplification in the
move commit).

No method renames. Per-call kwargs for runtime-mutable Scheduler state
(``running_batch`` / ``waiting_queue`` / ``stats`` / spec accumulators /
4 disagg queues) are added to the signature as a pragmatic deviation
(per ``MECH_COMMIT_SPLIT.md`` doc R4 kwarg-add allowance — documented).
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
SUBJECT = "Build SchedulerLoadInquirer skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-load-inquirer`` mech move.

- Create ``scheduler_components/load_inquirer.py`` with an empty
  ``SchedulerLoadInquirer`` class skeleton (ctor only; no methods yet).
- Instantiate ``self.load_inquirer = SchedulerLoadInquirer(...)`` in
  ``Scheduler.__init__`` after ``self.pool_stats_observer`` so the
  sister dep resolves.
- In ``SchedulerMetricsMixin``, convert ``get_loads`` to ``@staticmethod``
  with ``self: "SchedulerLoadInquirer"`` type annotation. Body bytes
  unchanged.
- Callers (RPC dispatch tuple in ``init_request_dispatcher`` and 1 call
  in ``scheduler_output_processor_mixin.stream_output_generation``)
  rewritten to call through ``self.load_inquirer`` via lambda / kwargs.

Pragmatic deviation: runtime-mutable Scheduler state read by the body
(``running_batch`` / ``waiting_queue`` / ``stats`` / 2 spec accumulators
/ 4 disagg queues) becomes per-call kwargs (R4 kwarg-add per the doc).

The method stays inside ``SchedulerMetricsMixin`` in this commit;
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
from typing import Optional

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


logger = logging.getLogger(__name__)


'''


NEW_CLASS_SKELETON = '''\
class SchedulerLoadInquirer:
    """``/v1/loads`` RPC handler. Composition target on Scheduler
    (``self.load_inquirer``)."""

    def __init__(
        self,
        *,
        disaggregation_mode,
        ps,
        max_total_num_tokens: int,
        max_running_requests: int,
        enable_lora: bool,
        pool_stats_observer,
        tp_worker,
        token_to_kv_pool_allocator,
        spec_algorithm,
    ) -> None:
        self.disaggregation_mode = disaggregation_mode
        self.ps = ps
        self.max_total_num_tokens = max_total_num_tokens
        self.max_running_requests = max_running_requests
        self.enable_lora = enable_lora
        self.pool_stats_observer = pool_stats_observer
        self.tp_worker = tp_worker
        self.token_to_kv_pool_allocator = token_to_kv_pool_allocator
        self.spec_algorithm = spec_algorithm
'''


SCHEDULER_INIT_INSERT = """\
        self.load_inquirer = SchedulerLoadInquirer(
            disaggregation_mode=self.disaggregation_mode,
            ps=self.ps,
            max_total_num_tokens=self.max_total_num_tokens,
            max_running_requests=self.max_running_requests,
            enable_lora=self.enable_lora,
            pool_stats_observer=self.pool_stats_observer,
            tp_worker=self.tp_worker,
            token_to_kv_pool_allocator=self.token_to_kv_pool_allocator,
            spec_algorithm=self.spec_algorithm,
        )

"""


LOAD_INQUIRER_CALL_KWARGS = """\
                running_batch=self.running_batch,
                waiting_queue=self.waiting_queue,
                stats=self.stats,
                spec_total_num_accepted_tokens=self.spec_total_num_accepted_tokens,
                spec_total_num_forward_ct=self.spec_total_num_forward_ct,
                disagg_prefill_bootstrap_queue=getattr(self, "disagg_prefill_bootstrap_queue", None),
                disagg_prefill_inflight_queue=getattr(self, "disagg_prefill_inflight_queue", None),
                disagg_decode_prealloc_queue=getattr(self, "disagg_decode_prealloc_queue", None),
                disagg_decode_transfer_queue=getattr(self, "disagg_decode_transfer_queue", None),
"""


# Old body's per-instance reads are rewritten to per-call kwarg reads
# (R4 kwarg-add pragmatic deviation). All replacements operate on the
# in-place method body text.
BODY_RUNTIME_KWARG_REPLACEMENTS = [
    ("len(self.running_batch.reqs)", "len(running_batch.reqs)"),
    ("waiting_queues = [self.waiting_queue]", "waiting_queues = [waiting_queue]"),
    (
        "waiting_queues.append(self.disagg_prefill_bootstrap_queue.queue)",
        "waiting_queues.append(disagg_prefill_bootstrap_queue.queue)",
    ),
    (
        "waiting_queues.append(self.disagg_decode_prealloc_queue.queue)",
        "waiting_queues.append(disagg_decode_prealloc_queue.queue)",
    ),
    (
        "waiting_queues.append(self.disagg_decode_transfer_queue.queue)",
        "waiting_queues.append(disagg_decode_transfer_queue.queue)",
    ),
    (
        "waiting_queues.append(self.disagg_decode_prealloc_queue.retracted_queue)",
        "waiting_queues.append(disagg_decode_prealloc_queue.retracted_queue)",
    ),
    (
        "num_used_tokens, kv_token_usage = self.get_pool_stats().get_kv_token_stats()",
        "num_used_tokens, kv_token_usage = self.pool_stats_observer.get_pool_stats(\n"
        "            last_batch=None, running_batch=running_batch\n"
        "        ).get_kv_token_stats()",
    ),
    (
        "if not self.spec_algorithm.is_none() and self.spec_total_num_forward_ct > 0:",
        "if not self.spec_algorithm.is_none() and spec_total_num_forward_ct > 0:",
    ),
    (
        "                        self.spec_total_num_accepted_tokens\n"
        "                        / self.spec_total_num_forward_ct",
        "                        spec_total_num_accepted_tokens\n"
        "                        / spec_total_num_forward_ct",
    ),
    (
        "                    accept_rate=self.stats.spec_accept_rate,",
        "                    accept_rate=stats.spec_accept_rate,",
    ),
    (
        "            if hasattr(self, \"lora_scheduler\") and self.lora_scheduler is not None:",
        "            if self.enable_lora:",
    ),
    (
        "                    slots_used=self.stats.lora_pool_slots_used,",
        "                    slots_used=stats.lora_pool_slots_used,",
    ),
    (
        "                    slots_total=self.stats.lora_pool_slots_total,",
        "                    slots_total=stats.lora_pool_slots_total,",
    ),
    (
        "                    utilization=self.stats.lora_pool_utilization,",
        "                    utilization=stats.lora_pool_utilization,",
    ),
    (
        "                prefill_bootstrap = len(self.disagg_prefill_bootstrap_queue.queue)",
        "                prefill_bootstrap = len(disagg_prefill_bootstrap_queue.queue)",
    ),
    (
        "                prefill_inflight = len(self.disagg_prefill_inflight_queue)",
        "                prefill_inflight = len(disagg_prefill_inflight_queue)",
    ),
    (
        "                decode_prealloc = len(self.disagg_decode_prealloc_queue.queue)",
        "                decode_prealloc = len(disagg_decode_prealloc_queue.queue)",
    ),
    (
        "                decode_transfer = len(self.disagg_decode_transfer_queue.queue)",
        "                decode_transfer = len(disagg_decode_transfer_queue.queue)",
    ),
    (
        "                    self.disagg_decode_prealloc_queue.retracted_queue",
        "                    disagg_decode_prealloc_queue.retracted_queue",
    ),
    (
        "                kv_transfer_speed_gb_s=self.stats.kv_transfer_speed_gb_s,",
        "                kv_transfer_speed_gb_s=stats.kv_transfer_speed_gb_s,",
    ),
    (
        "                kv_transfer_latency_ms=self.stats.kv_transfer_latency_ms,",
        "                kv_transfer_latency_ms=stats.kv_transfer_latency_ms,",
    ),
    (
        "                waiting=len(self.waiting_queue),",
        "                waiting=len(waiting_queue),",
    ),
    (
        "                grammar=self.stats.num_grammar_queue_reqs,",
        "                grammar=stats.num_grammar_queue_reqs,",
    ),
    (
        "                paused=self.stats.num_paused_reqs,",
        "                paused=stats.num_paused_reqs,",
    ),
    (
        "                retracted=self.stats.num_retracted_reqs,",
        "                retracted=stats.num_retracted_reqs,",
    ),
    ("dp_rank=self.dp_rank,", "dp_rank=self.ps.dp_rank,"),
    ("gen_throughput=round(self.stats.gen_throughput, 2),",
     "gen_throughput=round(stats.gen_throughput, 2),"),
    ("cache_hit_rate=round(self.stats.cache_hit_rate, 4),",
     "cache_hit_rate=round(stats.cache_hit_rate, 4),"),
    ("utilization=round(self.stats.utilization, 4),",
     "utilization=round(stats.utilization, 4),"),
]


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/load_inquirer.py"

    # 1. Create new target file (skeleton: header + empty class).
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_FILE_HEADER + NEW_CLASS_SKELETON)

    # 2. Type-flip ``get_loads`` to @staticmethod + self: SchedulerLoadInquirer
    #    and rewrite per-call kwargs.
    text = src.read_text()
    s, e = find_method_lines(
        text, class_name="SchedulerMetricsMixin", method_name="get_loads"
    )
    lines = text.splitlines(keepends=True)
    method_text = "".join(lines[s:e])

    if "    def get_loads(self: Scheduler, req: GetLoadsReqInput = None) -> GetLoadsReqOutput:" not in method_text:
        raise RuntimeError("get_loads signature anchor mismatch")
    new_method = method_text.replace(
        "    def get_loads(self: Scheduler, req: GetLoadsReqInput = None) -> GetLoadsReqOutput:",
        "    @staticmethod\n"
        "    def get_loads(\n"
        "        self: \"SchedulerLoadInquirer\",\n"
        "        req: GetLoadsReqInput = None,\n"
        "        *,\n"
        "        running_batch,\n"
        "        waiting_queue,\n"
        "        stats,\n"
        "        spec_total_num_accepted_tokens: int,\n"
        "        spec_total_num_forward_ct: int,\n"
        "        disagg_prefill_bootstrap_queue,\n"
        "        disagg_prefill_inflight_queue,\n"
        "        disagg_decode_prealloc_queue,\n"
        "        disagg_decode_transfer_queue,\n"
        "    ) -> GetLoadsReqOutput:",
    )
    for old, new in BODY_RUNTIME_KWARG_REPLACEMENTS:
        if old not in new_method:
            raise RuntimeError(f"get_loads body anchor missing: {old!r}")
        new_method = new_method.replace(old, new)
    text = "".join(lines[:s]) + new_method + "".join(lines[e:])
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

    # 3. Scheduler: import + ctor + RPC dispatch lambda.
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
            "        )\n\n"
        ),
        addition=SCHEDULER_INIT_INSERT,
    )
    # RPC dispatch tuple — bind static method to self.load_inquirer via lambda.
    text = replace_call_site(
        text,
        old="                (GetLoadsReqInput, self.get_loads),\n",
        new=(
            "                (\n"
            "                    GetLoadsReqInput,\n"
            "                    lambda req: self.get_loads(\n"
            "                        self.load_inquirer,\n"
            "                        req,\n"
            + LOAD_INQUIRER_CALL_KWARGS
            + "                    ),\n"
            "                ),\n"
        ),
    )
    sched.write_text(text)

    # 4. Output processor mixin callsite.
    text = output_mixin.read_text()
    text = text.replace(
        '        load = self.get_loads(GetLoadsReqInput(include=["core"]))\n',
        "        load = self.get_loads(\n"
        "            self.load_inquirer,\n"
        '            GetLoadsReqInput(include=["core"]),\n'
        + LOAD_INQUIRER_CALL_KWARGS
        + "        )\n",
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
