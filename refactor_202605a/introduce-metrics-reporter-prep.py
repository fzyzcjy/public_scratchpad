#!/usr/bin/env python3
"""Inplace prep for ``introduce-metrics-reporter``: build the
``SchedulerMetricsReporter`` class skeleton (ctor only, NO methods yet),
instantiate on Scheduler, type-flip all remaining mixin methods to
``@staticmethod`` with ``self: "SchedulerMetricsReporter"``, perform the
fancy-reshape body substitutions (Callable getter form for mutable
Scheduler scalars), and rewrite callers to the sister form.

Body bytes are *not* fully byte-identical wrt the post-move state here:
this is a deliberate, doc-acknowledged deviation. The metrics reporter
needs Callable injection (``get_running_batch`` / ``get_forward_ct`` /
``get_running_mbs`` / ``get_last_batch``) because the originals are
mutable Scheduler scalars; the doc's strict rule pushes this to
nonmech follow-up but pragmatically we keep it here so the upcoming
``-move`` commit is a true byte-equal cut + paste.

Pragmatic deviations documented:
- Callable injection for 4 mutable scalars (``running_batch`` /
  ``forward_ct`` / ``running_mbs`` / ``last_batch``).
- Ownership migration: ``num_retracted_reqs`` / ``num_paused_reqs``
  move from Scheduler-owned to reporter-owned.
- ``init_metrics`` body is inlined into the reporter ctor.
- The original ``init_metrics`` callsite is replaced with an inline
  block that computes ``current_scheduler_metrics_enabled`` /
  ``enable_kv_cache_events`` / the metrics_collector (because
  ``init_ipc_channels`` / ``init_cache_with_memory_pool`` /
  ``init_model_worker`` read those fields before the reporter exists).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-metrics-reporter-prep"
SUBJECT = "Build SchedulerMetricsReporter skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``introduce-metrics-reporter`` mech move.

- Rewrite the mixin file header so ``SchedulerMetricsMixin`` becomes
  ``SchedulerMetricsReporter`` with a narrow-kwargs ctor that inlines
  the original ``init_metrics`` body (the manager owns the state).
- Add Callable getter injection (``get_running_batch`` /
  ``get_forward_ct`` / ``get_running_mbs`` / ``get_last_batch``) for
  mutable Scheduler scalars — body reads are rewritten to call the
  getters.
- Privacy flips done in the preceding ``-pre-rename`` commit.
- Ownership migration: ``num_retracted_reqs`` / ``num_paused_reqs``
  move to reporter; the single external writer in
  ``Scheduler.run_batch`` rewires to
  ``self.metrics_reporter.num_retracted_reqs = ...``.
- In Scheduler.__init__, replace the ``init_metrics`` call with an
  inline block computing the 3 early fields read by IPC / cache /
  model-worker init, then instantiate
  ``self.metrics_reporter = SchedulerMetricsReporter(...)`` after
  ``self.kv_events_publisher``.
- Hot-path callsites updated via sister form
  (``self.metrics_reporter.<method>(...)``).

Pragmatic deviation (per doc): Callable injection + ownership migration
+ signature redesign are kept in this prep commit (not pushed to a
nonmech follow-up) so the upcoming ``-move`` commit is a true byte-equal
cut + paste.

The 14 remaining mixin methods + ``PrefillStats`` stay inside the file
in this commit; physical cut + paste to the target file (and deletion
of the metrics mixin) happens in ``introduce-metrics-reporter-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


NEW_CTOR_AND_INIT_PROLOGUE = '''\
class SchedulerMetricsReporter:
    """Prometheus / Stats hot-path. Composition target on Scheduler
    (``self.metrics_reporter``)."""

    def __init__(
        self,
        *,
        ps,
        server_args,
        disaggregation_mode,
        spec_algorithm,
        metrics_collector,
        enable_priority_scheduling: bool,
        enable_lora,
        enable_hierarchical_cache: bool,
        max_running_requests: int,
        max_total_num_tokens: int,
        tp_rank: int,
        pp_rank: int,
        dp_rank,
        attn_tp_rank: int,
        moe_ep_rank: int,
        device: str,
        model_config,
        max_running_requests_under_SLO,
        waiting_queue,
        grammar_manager,
        mm_receiver,
        tree_cache,
        tp_worker,
        draft_worker,
        disagg_prefill_bootstrap_queue,
        disagg_prefill_inflight_queue,
        disagg_decode_prealloc_queue,
        disagg_decode_transfer_queue,
        kv_events_publisher,
        pool_stats_observer,
        get_running_batch,
        get_forward_ct,
        get_running_mbs,
        get_last_batch,
    ) -> None:
        # Owned counters (ownership migration from Scheduler).
        self.num_retracted_reqs: int = 0
        self.num_paused_reqs: int = 0
        # Stash deps + sisters + Callable getters.
        self.ps = ps
        self.server_args = server_args
        self.disaggregation_mode = disaggregation_mode
        self.spec_algorithm = spec_algorithm
        self.metrics_collector = metrics_collector
        self.enable_priority_scheduling = enable_priority_scheduling
        self.enable_lora = enable_lora
        self.enable_hierarchical_cache = enable_hierarchical_cache
        self.max_running_requests = max_running_requests
        self.max_total_num_tokens = max_total_num_tokens
        self.device = device
        self.model_config = model_config
        self.max_running_requests_under_SLO = max_running_requests_under_SLO
        self.waiting_queue = waiting_queue
        self.grammar_manager = grammar_manager
        self.mm_receiver = mm_receiver
        self.tree_cache = tree_cache
        self.tp_worker = tp_worker
        self.draft_worker = draft_worker
        self.disagg_prefill_bootstrap_queue = disagg_prefill_bootstrap_queue
        self.disagg_prefill_inflight_queue = disagg_prefill_inflight_queue
        self.disagg_decode_prealloc_queue = disagg_decode_prealloc_queue
        self.disagg_decode_transfer_queue = disagg_decode_transfer_queue
        self.kv_events_publisher = kv_events_publisher
        self.pool_stats_observer = pool_stats_observer
        self.get_running_batch = get_running_batch
        self.get_forward_ct = get_forward_ct
        self.get_running_mbs = get_running_mbs
        self.get_last_batch = get_last_batch
        # Run the original init_metrics body inline.
        self.init_metrics(tp_rank, pp_rank, dp_rank)

'''


SCHEDULER_INIT_INSERT = """\
        self.metrics_reporter = SchedulerMetricsReporter(
            ps=self.ps,
            server_args=self.server_args,
            disaggregation_mode=DisaggregationMode(self.server_args.disaggregation_mode),
            spec_algorithm=self.spec_algorithm,
            metrics_collector=self.metrics_collector,
            enable_priority_scheduling=self.enable_priority_scheduling,
            enable_lora=self.enable_lora,
            enable_hierarchical_cache=self.enable_hierarchical_cache,
            max_running_requests=self.max_running_requests,
            max_total_num_tokens=self.max_total_num_tokens,
            tp_rank=self.ps.tp_rank,
            pp_rank=self.ps.pp_rank,
            dp_rank=self.ps.dp_rank,
            attn_tp_rank=self.ps.attn_tp_rank,
            moe_ep_rank=self.ps.moe_ep_rank,
            device=getattr(self, "device", ""),
            model_config=self.model_config,
            max_running_requests_under_SLO=getattr(
                self, "max_running_requests_under_SLO", None
            ),
            waiting_queue=self.waiting_queue,
            grammar_manager=self.grammar_manager,
            mm_receiver=getattr(self, "mm_receiver", None),
            tree_cache=self.tree_cache,
            tp_worker=self.tp_worker,
            draft_worker=self.draft_worker,
            disagg_prefill_bootstrap_queue=getattr(
                self, "disagg_prefill_bootstrap_queue", None
            ),
            disagg_prefill_inflight_queue=getattr(
                self, "disagg_prefill_inflight_queue", None
            ),
            disagg_decode_prealloc_queue=getattr(
                self, "disagg_decode_prealloc_queue", None
            ),
            disagg_decode_transfer_queue=getattr(
                self, "disagg_decode_transfer_queue", None
            ),
            kv_events_publisher=self.kv_events_publisher,
            pool_stats_observer=self.pool_stats_observer,
            get_running_batch=lambda: self.running_batch,
            get_forward_ct=lambda: self.forward_ct,
            get_running_mbs=lambda: getattr(self, "running_mbs", []),
            get_last_batch=lambda: self.last_batch,
        )
        # Aliases so call sites that historically read self.X (when init_metrics
        # set those fields directly on Scheduler) still resolve.
        self.stats = self.metrics_reporter.stats

"""


INLINE_CURRENT_METRICS_ENABLED = (
    "        # Computed early because init_ipc_channels reads it; the rest of\n"
    "        # init_metrics now runs inside the metrics_reporter ctor below.\n"
    "        self.enable_metrics = self.server_args.enable_metrics\n"
    "        self.is_stats_logging_rank = self.ps.attn_tp_rank == 0\n"
    "        self.current_scheduler_metrics_enabled = self.enable_metrics and (\n"
    "            self.is_stats_logging_rank\n"
    "            or self.server_args.enable_metrics_for_all_schedulers\n"
    "        )\n"
    "        # init_cache_with_memory_pool reads this before the\n"
    "        # kv_events_publisher is constructed.\n"
    "        self.enable_kv_cache_events = bool(\n"
    "            self.server_args.kv_events_config\n"
    "            and self.ps.attn_tp_rank == 0\n"
    "            and self.ps.attn_cp_rank == 0\n"
    "        )\n"
    "        # init_model_worker calls ``self.metrics_collector.emit_constants(...)``\n"
    "        # early; create the collector here (mirrors original ``init_metrics``\n"
    "        # placement). metrics_reporter then receives the same instance.\n"
    "        self.metrics_collector = None\n"
    "        if self.enable_metrics:\n"
    "            _engine_type = DisaggregationMode.to_engine_type(\n"
    "                self.server_args.disaggregation_mode\n"
    "            )\n"
    "            _labels = {\n"
    "                'model_name': self.server_args.served_model_name,\n"
    "                'engine_type': _engine_type,\n"
    "                'tp_rank': tp_rank,\n"
    "                'pp_rank': pp_rank,\n"
    "                'moe_ep_rank': self.ps.moe_ep_rank,\n"
    "            }\n"
    "            if self.enable_priority_scheduling:\n"
    "                _labels['priority'] = ''\n"
    "            if dp_rank is not None:\n"
    "                _labels['dp_rank'] = dp_rank\n"
    "            if self.server_args.extra_metric_labels:\n"
    "                _labels.update(self.server_args.extra_metric_labels)\n"
    "            self.metrics_collector = SchedulerMetricsCollector(\n"
    "                labels=_labels,\n"
    "                enable_lora=self.enable_lora,\n"
    "                enable_hierarchical_cache=self.enable_hierarchical_cache,\n"
    "                enable_streaming_session=self.server_args.enable_streaming_session,\n"
    "                server_args=self.server_args,\n"
    "            )\n"
)


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    pre = wt / "python/sglang/srt/disaggregation/prefill.py"
    dllm = wt / "python/sglang/srt/dllm/mixin/scheduler.py"

    # 1. Rewrite the mixin file header into the reporter class.
    text = src.read_text()
    text = text.replace("self: Scheduler", "self")
    text = text.replace(
        "    from sglang.srt.managers.scheduler import EmbeddingBatchResult, Scheduler\n",
        "    from sglang.srt.managers.scheduler import EmbeddingBatchResult\n",
    )
    text = text.replace(
        "from sglang.srt.managers.scheduler import ScheduleBatch\n",
        "from sglang.srt.managers.schedule_batch import ScheduleBatch\n",
    )
    if "class SchedulerMetricsMixin:\n" not in text:
        raise RuntimeError("Metrics class header anchor mismatch")
    text = text.replace("class SchedulerMetricsMixin:\n", NEW_CTOR_AND_INIT_PROLOGUE)

    # Callable getter substitutions.
    text = text.replace("self.running_batch", "self.get_running_batch()")
    text = text.replace("self.forward_ct", "self.get_forward_ct()")
    text = text.replace("self.running_mbs", "self.get_running_mbs()")
    text = text.replace("self.last_batch", "self.get_last_batch()")
    text = text.replace(
        "self.get_forward_ct()_decode", "self.forward_ct_decode"
    )

    # Strip the engine_type / metrics_collector creation block from init_metrics
    # (now built on the Scheduler side and passed as a kwarg).
    text = re.sub(
        r"            engine_type = DisaggregationMode\.to_engine_type\(\n"
        r"(?:[^\n]*\n)+?"
        r"            self\.metrics_collector = SchedulerMetricsCollector\(\n"
        r"(?:[^\n]*\n)+?"
        r"            \)\n",
        "",
        text,
    )
    src.write_text(text)

    # 2. Update Scheduler.
    text = sched.read_text()
    # Drop any stale ``SchedulerMetricsMixin`` import block.
    text = re.sub(
        r"from sglang\.srt\.observability\.scheduler_metrics_mixin import \([^)]*\)\n",
        "",
        text,
    )
    text = re.sub(
        r"from sglang\.srt\.observability\.scheduler_metrics_mixin import [^\n]+\n",
        "",
        text,
    )
    # Add the reporter + collector imports.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.load_inquirer import (\n    SchedulerLoadInquirer,\n)\n",
        addition=(
            "from sglang.srt.observability.scheduler_metrics_mixin import (\n"
            "    RECORD_STEP_TIME,\n"
            "    PrefillStats,\n"
            "    SchedulerMetricsReporter,\n"
            ")\n"
            "from sglang.srt.observability.metrics_collector import SchedulerMetricsCollector\n"
        ),
    )
    text = replace_call_site(text, old="    SchedulerMetricsMixin,\n", new="")
    # Replace init_metrics callsite with the inline early-fields block.
    text = text.replace(
        "        self.init_metrics(tp_rank, pp_rank, dp_rank)\n",
        INLINE_CURRENT_METRICS_ENABLED,
    )
    # Insert the reporter ctor after the kv_events_publisher ctor.
    text = insert_after(
        text,
        anchor=(
            "        self.kv_events_publisher = SchedulerKvEventsPublisher(\n"
            "            kv_events_config=self.server_args.kv_events_config,\n"
            "            attn_tp_rank=self.ps.attn_tp_rank,\n"
            "            attn_cp_rank=self.ps.attn_cp_rank,\n"
            "            attn_dp_rank=self.ps.attn_dp_rank,\n"
            "            dp_rank=self.ps.dp_rank,\n"
            "            tree_cache=self.tree_cache,\n"
            "            send_metrics_from_scheduler=self.send_metrics_from_scheduler,\n"
            "            max_running_requests=self.max_running_requests,\n"
            "            max_total_num_tokens=self.max_total_num_tokens,\n"
            "        )\n\n"
        ),
        addition=SCHEDULER_INIT_INSERT,
    )
    # Drop owned counter init lines (now reporter-owned).
    text = text.replace("        self.num_retracted_reqs: int = 0\n", "")
    text = text.replace("        self.num_paused_reqs: int = 0\n", "")
    # ``install_device_timer_on_runners`` Scheduler callsite — drop; the
    # reporter ctor calls it inline post-init_metrics.
    text = text.replace(
        "        self.install_device_timer_on_runners()\n",
        "",
    )
    # Hot-path callsites — route through sister.
    text = text.replace(
        "        self.log_batch_result_stats(batch, result)\n",
        "        self.metrics_reporter.log_batch_result_stats(batch, result)\n",
    )
    text = text.replace(
        "        self.update_device_timer()\n",
        "        self.metrics_reporter.update_device_timer()\n",
    )
    text = text.replace(
        "            self.reset_metrics()\n",
        "            self.metrics_reporter.reset_metrics()\n",
    )
    text = text.replace(
        "        self.reset_device_timer_window()\n",
        "        self.metrics_reporter.reset_device_timer_window()\n",
    )
    # Spec lifetime counters now reporter-owned.
    text = text.replace(
        "self.spec_total_num_accepted_tokens",
        "self.metrics_reporter.spec_total_num_accepted_tokens",
    )
    text = text.replace(
        "self.spec_total_num_forward_ct",
        "self.metrics_reporter.spec_total_num_forward_ct",
    )
    text = text.replace(
        'ret["last_gen_throughput"] = self.last_gen_throughput',
        'ret["last_gen_throughput"] = self.metrics_reporter.last_gen_throughput',
    )
    text = text.replace(
        'ret["step_time_dict"] = self.step_time_dict',
        'ret["step_time_dict"] = self.metrics_reporter.step_time_dict',
    )
    text = text.replace(
        "            self.num_retracted_reqs = len(retracted_reqs)\n",
        "            self.metrics_reporter.num_retracted_reqs = len(retracted_reqs)\n",
    )
    # Patch the reporter ctor body in the mixin file to call
    # install_device_timer_on_runners after init_metrics.
    sched.write_text(text)

    text = src.read_text()
    text = text.replace(
        "        # Run the original init_metrics body inline.\n"
        "        self.init_metrics(tp_rank, pp_rank, dp_rank)\n",
        "        # Run the original init_metrics body inline.\n"
        "        self.init_metrics(tp_rank, pp_rank, dp_rank)\n"
        "        # ``install_device_timer_on_runners`` was originally called\n"
        "        # from Scheduler.__init__ right after init_model_worker; we\n"
        "        # invoke it here so callers don't need a separate hook.\n"
        "        self.install_device_timer_on_runners()\n",
    )
    src.write_text(text)

    # 3. Output processor mixin callsites.
    text = output_mixin.read_text()
    text = text.replace(
        "        self.report_prefill_stats(",
        "        self.metrics_reporter.report_prefill_stats(",
    )
    text = text.replace(
        "            self.update_spec_metrics(",
        "            self.metrics_reporter.update_spec_metrics(",
    )
    text = text.replace(
        "        self.report_decode_stats(",
        "        self.metrics_reporter.report_decode_stats(",
    )
    output_mixin.write_text(text)

    # 4. Disaggregation prefill.
    text = pre.read_text()
    text = text.replace(
        "        self.report_prefill_stats(",
        "        self.metrics_reporter.report_prefill_stats(",
    )
    pre.write_text(text)

    # 5. dllm mixin.
    text = dllm.read_text()
    text = text.replace(
        "        self.report_prefill_stats(",
        "        self.metrics_reporter.report_prefill_stats(",
    )
    dllm.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
