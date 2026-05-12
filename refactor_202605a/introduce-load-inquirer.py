#!/usr/bin/env python3
"""1:N split #2 of ``SchedulerMetricsMixin``: introduce
``SchedulerLoadInquirer`` at
``scheduler_components/load_inquirer.py``.

Single method (``get_loads``) moves out. Ctor narrow kwargs (5 config + 1
sister + 3 collaborators). Per-call kwargs added for runtime mutable state
(running_batch / waiting_queue / stats / spec accumulators / 4 disagg
queues — all forwarded by the caller via lambda from
``init_request_dispatcher`` and from ``stream_output_generation``).

No method rename. ``req: GetLoadsReqInput = None`` default kept (default-arg
tightening is Ch2). The ``if hasattr(self, "lora_scheduler")`` dead-code
branch is preserved verbatim (preflight / Ch2). The ``try/except
AttributeError`` guard around ``MemoryMetrics`` is preserved verbatim.
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

ID = "introduce-load-inquirer"
SUBJECT = "Introduce SchedulerLoadInquirer (split #2 of metrics mixin)"
BODY = """\
Pull ``get_loads`` out of ``SchedulerMetricsMixin`` into a new
``SchedulerLoadInquirer`` at
``scheduler_components/load_inquirer.py``. Scheduler holds it
as ``self.load_inquirer``.

Ctor narrow kwargs (per CLAUDE.md ch4): 5 configs (disaggregation_mode,
ps, max_total_num_tokens, max_running_requests, enable_lora) + 1 sister
(``pool_stats_observer``) + 3 collaborators (tp_worker,
token_to_kv_pool_allocator, spec_algorithm).

Runtime-mutable state read by the body becomes per-call kwargs (R4 kwarg
add per EXECUTION_GUIDE item 2): ``running_batch`` / ``waiting_queue`` /
``stats`` / ``spec_total_num_accept_tokens`` /
``spec_total_num_forward_ct`` / 4 disagg queues. Callers (RPC dispatch
tuple in ``init_request_dispatcher`` and 1 internal call from
``stream_output_generation``) provide these via lambda.

No method renames. ``req: GetLoadsReqInput = None`` default kept (default
tightening = Ch2). Dead ``hasattr(self, "lora_scheduler")`` branch and
``try/except AttributeError`` guard preserved verbatim — preflight is Ch2.

The metrics mixin remains in place; ``introduce-metrics-reporter`` finishes
the 1:N split next.
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


NEW_CLASS_BODY = '''\
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

    def get_loads(
        self,
        req: GetLoadsReqInput = None,
        *,
        running_batch,
        waiting_queue,
        stats,
        spec_total_num_accept_tokens: int,
        spec_total_num_forward_ct: int,
        disagg_prefill_bootstrap_queue,
        disagg_prefill_inflight_queue,
        disagg_decode_prealloc_queue,
        disagg_decode_transfer_queue,
    ) -> GetLoadsReqOutput:
        """Get comprehensive load metrics for /v1/loads endpoint."""
        if req is None:
            req = GetLoadsReqInput()

        include = set(req.include) if req.include else {"core"}
        include_all = "all" in include

        num_running_reqs = len(running_batch.reqs)

        waiting_queues = [waiting_queue]
        if self.disaggregation_mode == DisaggregationMode.PREFILL:
            waiting_queues.append(disagg_prefill_bootstrap_queue.queue)
        elif self.disaggregation_mode == DisaggregationMode.DECODE:
            waiting_queues.append(disagg_decode_prealloc_queue.queue)
            waiting_queues.append(disagg_decode_transfer_queue.queue)
            waiting_queues.append(disagg_decode_prealloc_queue.retracted_queue)

        num_waiting_reqs = sum(len(queue) for queue in waiting_queues)
        num_used_tokens, kv_token_usage = self.pool_stats_observer.get_pool_stats(
            last_batch=None, running_batch=running_batch
        ).get_kv_token_stats()
        num_total_tokens = num_used_tokens + sum(
            r.seqlen for queue in waiting_queues for r in queue
        )

        memory = None
        if include_all or "memory" in include:
            try:
                memory = MemoryMetrics(
                    weight_gb=round(
                        self.tp_worker.model_runner.weight_load_mem_usage, 3
                    ),
                    kv_cache_gb=round(
                        self.token_to_kv_pool_allocator.get_kvcache().mem_usage, 3
                    ),
                    graph_gb=round(self.tp_worker.model_runner.graph_mem_usage, 3),
                    token_capacity=int(self.max_total_num_tokens),
                )
            except AttributeError as e:
                logger.debug(f"Memory metrics not available: {e}")

        speculative = None
        if include_all or "spec" in include:
            if not self.spec_algorithm.is_none() and spec_total_num_forward_ct > 0:
                speculative = SpeculativeMetrics(
                    accept_length=(
                        spec_total_num_accept_tokens
                        / spec_total_num_forward_ct
                    ),
                    accept_rate=stats.spec_accept_rate,
                )

        lora = None
        if include_all or "lora" in include:
            if self.enable_lora:
                lora = LoRAMetrics(
                    slots_used=stats.lora_pool_slots_used,
                    slots_total=stats.lora_pool_slots_total,
                    utilization=stats.lora_pool_utilization,
                )

        disaggregation = None
        if include_all or "disagg" in include:
            mode_str = "null"
            prefill_bootstrap = 0
            prefill_inflight = 0
            decode_prealloc = 0
            decode_transfer = 0
            decode_retracted = 0

            if self.disaggregation_mode == DisaggregationMode.PREFILL:
                mode_str = "prefill"
                prefill_bootstrap = len(disagg_prefill_bootstrap_queue.queue)
                prefill_inflight = len(disagg_prefill_inflight_queue)
            elif self.disaggregation_mode == DisaggregationMode.DECODE:
                mode_str = "decode"
                decode_prealloc = len(disagg_decode_prealloc_queue.queue)
                decode_transfer = len(disagg_decode_transfer_queue.queue)
                decode_retracted = len(
                    disagg_decode_prealloc_queue.retracted_queue
                )

            disaggregation = DisaggregationMetrics(
                mode=mode_str,
                prefill_bootstrap_queue_reqs=prefill_bootstrap,
                prefill_inflight_queue_reqs=prefill_inflight,
                decode_prealloc_queue_reqs=decode_prealloc,
                decode_transfer_queue_reqs=decode_transfer,
                decode_retracted_queue_reqs=decode_retracted,
                kv_transfer_speed_gb_s=stats.kv_transfer_speed_gb_s,
                kv_transfer_latency_ms=stats.kv_transfer_latency_ms,
            )

        queues = None
        if include_all or "queues" in include:
            queues = QueueMetrics(
                waiting=len(waiting_queue),
                grammar=stats.num_grammar_queue_reqs,
                paused=stats.num_paused_reqs,
                retracted=stats.num_retracted_reqs,
            )

        return GetLoadsReqOutput(
            dp_rank=self.ps.dp_rank,
            timestamp=time.time(),
            num_running_reqs=num_running_reqs,
            num_waiting_reqs=num_waiting_reqs,
            num_used_tokens=num_used_tokens,
            num_total_tokens=num_total_tokens,
            max_total_num_tokens=self.max_total_num_tokens,
            token_usage=round(kv_token_usage, 4),
            gen_throughput=round(stats.gen_throughput, 2),
            cache_hit_rate=round(stats.cache_hit_rate, 4),
            utilization=round(stats.utilization, 4),
            max_running_requests=self.max_running_requests,
            memory=memory,
            speculative=speculative,
            lora=lora,
            disaggregation=disaggregation,
            queues=queues,
        )
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


# Lambda used in RPC dispatch + as the helper-form replacement for the
# 1 internal callsite in stream_output_generation.
LOAD_INQUIRER_CALL_KWARGS = """\
                running_batch=self.running_batch,
                waiting_queue=self.waiting_queue,
                stats=self.stats,
                spec_total_num_accept_tokens=self.spec_total_num_accept_tokens,
                spec_total_num_forward_ct=self.spec_total_num_forward_ct,
                disagg_prefill_bootstrap_queue=getattr(self, "disagg_prefill_bootstrap_queue", None),
                disagg_prefill_inflight_queue=getattr(self, "disagg_prefill_inflight_queue", None),
                disagg_decode_prealloc_queue=getattr(self, "disagg_decode_prealloc_queue", None),
                disagg_decode_transfer_queue=getattr(self, "disagg_decode_transfer_queue", None),
"""


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/load_inquirer.py"

    # Cut get_loads from metrics mixin.
    src_text = src.read_text()
    s, e = find_method_lines(
        src_text, class_name="SchedulerMetricsMixin", method_name="get_loads"
    )
    lines = src_text.splitlines(keepends=True)
    del lines[s:e]
    src.write_text("".join(lines))

    # Build the new file.
    target.write_text(TARGET_FILE_HEADER + NEW_CLASS_BODY)

    # Update Scheduler: import + ctor + RPC dispatch lambda.
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
    # Insert AFTER the pool_stats_observer ctor (sister) so dep resolves.
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
    # RPC dispatch: ``(GetLoadsReqInput, self.get_loads)`` → lambda.
    text = replace_call_site(
        text,
        old="                (GetLoadsReqInput, self.get_loads),\n",
        new=(
            "                (\n"
            "                    GetLoadsReqInput,\n"
            "                    lambda req: self.load_inquirer.get_loads(\n"
            "                        req,\n"
            + LOAD_INQUIRER_CALL_KWARGS
            + "                    ),\n"
            "                ),\n"
        ),
    )
    sched.write_text(text)

    # Update output_processor_mixin: 1 callsite in stream_output_generation.
    text = output_mixin.read_text()
    text = text.replace(
        '        load = self.get_loads(GetLoadsReqInput(include=["core"]))\n',
        "        load = self.load_inquirer.get_loads(\n"
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
