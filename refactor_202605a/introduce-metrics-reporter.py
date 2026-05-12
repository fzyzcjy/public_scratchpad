#!/usr/bin/env python3
"""1:N split #3 of ``SchedulerMetricsMixin``: the remaining 14 reporter
methods + ``PrefillStats`` dataclass move to ``SchedulerMetricsReporter`` at
``scheduler_components/metrics_reporter.py``. The metrics
mixin file is then deleted.

- Ctor narrow kwargs (per CLAUDE.md ch4): server_args + 4 typed configs +
  5 rank fields + 3 device/SLO + 6 collaborators + 4 disagg queues + 2
  sisters (kv_events_publisher, pool_stats_observer) + 3 Callable getters
  (get_running_batch / get_forward_ct / get_running_mbs).
- 2 privacy flips: ``update_lora_metrics`` → ``_update_lora_metrics`` /
  ``calculate_utilization`` → ``_calculate_utilization``.
- Ownership migration: ``num_retracted_reqs`` / ``num_paused_reqs`` move
  from Scheduler.__init__ owned fields to the manager. The single external
  write site in ``Scheduler.run_batch``-area code is rewritten to
  ``self.metrics_reporter.num_retracted_reqs = ...``.
- Body's ``self.running_batch`` / ``self.forward_ct`` / ``self.running_mbs``
  references switch to ``self.get_running_batch()`` / etc. (Callable getter
  form, since these are mutable Scheduler scalars).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-metrics-reporter"
SUBJECT = "Introduce SchedulerMetricsReporter (split #3 of metrics mixin); delete metrics mixin file"
BODY = """\
Pull the remaining 14 methods + ``PrefillStats`` dataclass out of
``SchedulerMetricsMixin`` into ``SchedulerMetricsReporter`` at
``scheduler_components/metrics_reporter.py``. Scheduler holds
it as ``self.metrics_reporter``. The metrics mixin file is deleted.

Ctor narrow kwargs (per CLAUDE.md ch4):
- ``server_args`` (整传, narrow abstraction exception per CLAUDE.md ch4)
- 4 typed/runtime-adjusted configs (``disaggregation_mode``,
  ``spec_algorithm``, ``max_running_requests``, ``max_total_num_tokens``)
- 5 rank/topology (``tp_rank``, ``pp_rank``, ``dp_rank``, ``attn_tp_rank``,
  ``moe_ep_rank``) — kept individually rather than through ``ps`` since the
  original ``init_metrics`` body uses them as direct args
- 3 device/SLO (``device``, ``model_config``, ``max_running_requests_under_SLO``)
- 6 collaborators (waiting_queue, grammar_manager, mm_receiver, tree_cache,
  tp_worker, draft_worker)
- 4 disagg queue refs (Optional)
- 2 sisters (``kv_events_publisher``, ``pool_stats_observer``)
- 3 ``Callable`` getters for mutable Scheduler scalars (``get_running_batch``,
  ``get_forward_ct``, ``get_running_mbs``)

2 privacy flips: ``update_lora_metrics`` → ``_update_lora_metrics`` /
``calculate_utilization`` → ``_calculate_utilization``.

Ownership migration: ``num_retracted_reqs`` / ``num_paused_reqs`` move from
``Scheduler.__init__`` to manager-owned. The single external writer in
``Scheduler.run_batch``-area code is updated to
``self.metrics_reporter.num_retracted_reqs = len(retracted_reqs)``.

Body substitutions:
- ``self.running_batch`` → ``self.get_running_batch()`` (Callable getter)
- ``self.forward_ct`` → ``self.get_forward_ct()``
- ``self.running_mbs`` → ``self.get_running_mbs()``

Callsite updates: 6 callsites — ``Scheduler.__init__`` (``init_metrics`` /
``install_device_timer_on_runners``), ``Scheduler.run_batch``
(``log_batch_result_stats`` / ``update_device_timer``),
``Scheduler.process_input_requests`` (``reset_metrics``),
``scheduler_output_processor_mixin.py`` (``report_prefill_stats`` /
``report_decode_stats`` / ``update_spec_metrics``), ``disaggregation/prefill.py``
+ ``dllm/mixin/scheduler.py`` (``report_prefill_stats``).

No method renames beyond the 2 privacy flips. ``spec_*_accepted_*``
spec-naming rename and the 4 base-residue self-getattr/hasattr fixes
(``getattr(self, "device", "")`` etc.) stay Ch2.

No behavior change.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


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

"""


# Header inserted at the top of the new metrics_reporter.py file (above the
# class). The body of the metrics_mixin file is then appended (with header
# replacements done via text.replace).
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


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    pre = wt / "python/sglang/srt/disaggregation/prefill.py"
    dllm = wt / "python/sglang/srt/dllm/mixin/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/metrics_reporter.py"

    text = src.read_text()

    # Drop ``: Scheduler`` annotations.
    text = text.replace("self: Scheduler", "self")

    # The ``if TYPE_CHECKING:`` block has multiple imports (Scheduler, Req,
    # PrefillAdder, etc.). Drop only the Scheduler reference (keep the rest).
    text = text.replace(
        "    from sglang.srt.managers.scheduler import EmbeddingBatchResult, Scheduler\n",
        "    from sglang.srt.managers.scheduler import EmbeddingBatchResult\n",
    )
    # Avoid circular import: scheduler.py imports metrics_reporter.py, so we
    # cannot import ScheduleBatch from sglang.srt.managers.scheduler at module
    # level. Use the canonical schedule_batch module instead.
    text = text.replace(
        "from sglang.srt.managers.scheduler import ScheduleBatch\n",
        "from sglang.srt.managers.schedule_batch import ScheduleBatch\n",
    )

    # Replace the class header. The original file's class line is the only
    # ``class SchedulerMetricsMixin:\n`` occurrence; replace with new class
    # header + ctor.
    if "class SchedulerMetricsMixin:\n" not in text:
        raise RuntimeError("Metrics class header anchor mismatch")
    text = text.replace("class SchedulerMetricsMixin:\n", NEW_CTOR_AND_INIT_PROLOGUE)

    # Privacy flips (definitions + internal cross-method calls).
    text = text.replace(
        "    def update_lora_metrics(self):", "    def _update_lora_metrics(self):"
    )
    text = text.replace(
        "    def calculate_utilization(self):", "    def _calculate_utilization(self):"
    )
    text = text.replace("self.update_lora_metrics(", "self._update_lora_metrics(")
    text = text.replace("self.calculate_utilization(", "self._calculate_utilization(")

    # Mutable Scheduler scalar references → Callable getter form.
    text = text.replace("self.running_batch", "self.get_running_batch()")
    text = text.replace("self.forward_ct", "self.get_forward_ct()")
    text = text.replace("self.running_mbs", "self.get_running_mbs()")
    text = text.replace("self.last_batch", "self.get_last_batch()")

    # The original init_metrics body has ``self.forward_ct_decode = 0`` —
    # the previous text.replace turned this into
    # ``self.get_forward_ct()_decode = 0`` which is broken. Rewrite back.
    text = text.replace(
        "self.get_forward_ct()_decode", "self.forward_ct_decode"
    )
    # Same for ``self.get_forward_ct()_decode % self.server_args.decode_log_interval``
    # and any other ``self.forward_ct_*`` field — restore the field-access form.

    # The metrics_collector is now created on the Scheduler side (see
    # INLINE_CURRENT_METRICS_ENABLED in this transform) and passed in via the
    # ctor kwarg. Strip the engine_type / labels dict / SchedulerMetricsCollector
    # creation from the init_metrics body — those reference Scheduler-only
    # fields (``enable_priority_scheduling``) that the manager does not carry.
    # Keep the ``enable_mfu_metrics`` setup (it still belongs on the manager).
    import re as _re_metrics
    text = _re_metrics.sub(
        r"            engine_type = DisaggregationMode\.to_engine_type\(\n"
        r"(?:[^\n]*\n)+?"
        r"            self\.metrics_collector = SchedulerMetricsCollector\(\n"
        r"(?:[^\n]*\n)+?"
        r"            \)\n",
        "",
        text,
    )

    target.write_text(text)
    src.unlink()

    # Update Scheduler.
    text = sched.read_text()
    # Drop any stale ``from sglang.srt.observability.scheduler_metrics_mixin``
    # import block (whatever shape isort settled on after previous trims).
    import re as _re
    text = _re.sub(
        r"from sglang\.srt\.observability\.scheduler_metrics_mixin import \([^)]*\)\n",
        "",
        text,
    )
    text = _re.sub(
        r"from sglang\.srt\.observability\.scheduler_metrics_mixin import [^\n]+\n",
        "",
        text,
    )
    # Re-export ``RECORD_STEP_TIME`` and ``PrefillStats`` from the new
    # metrics_reporter module (scheduler.py uses both as module-level refs).
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.load_inquirer import (\n    SchedulerLoadInquirer,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.metrics_reporter import (\n"
            "    RECORD_STEP_TIME,\n"
            "    PrefillStats,\n"
            ")\n"
        ),
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.load_inquirer import (\n    SchedulerLoadInquirer,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.metrics_reporter import (\n"
            "    SchedulerMetricsReporter,\n"
            ")\n"
            "from sglang.srt.observability.metrics_collector import SchedulerMetricsCollector\n"
        ),
    )
    text = replace_call_site(text, old="    SchedulerMetricsMixin,\n", new="")
    # The manager ctor needs many Scheduler fields that are set late
    # (``max_running_requests`` from init_model_worker; ``disaggregation_mode``
    # plus disagg queues from init_disaggregation; ``tree_cache``,
    # ``waiting_queue`` from init_cache / init_running_status; etc.). So we
    # insert the ctor AT THE END of ``__init__`` (just before
    # ``self.is_initializing = False``) — by which time everything is set.
    #
    # The original ``init_metrics`` call site additionally set
    # ``self.current_scheduler_metrics_enabled``, which ``init_ipc_channels``
    # reads early. Replace the call site with an inline compute of just that
    # one field; the rest moves to the late ctor.
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
    text = text.replace(
        "        self.init_metrics(tp_rank, pp_rank, dp_rank)\n",
        INLINE_CURRENT_METRICS_ENABLED,
    )
    METRICS_ALIAS_SETUP = (
        SCHEDULER_INIT_INSERT
        + "        # Aliases so call sites that historically read self.X (when init_metrics\n"
        + "        # set those fields directly on Scheduler) still resolve.\n"
        + "        # ``self.metrics_collector`` is already set in the early inline block\n"
        + "        # above (passed as a kwarg to the metrics_reporter ctor), so no alias.\n"
        + "        self.stats = self.metrics_reporter.stats\n"
    )
    # Insert AFTER the kv_events_publisher ctor (sister) so dep resolves.
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
            "        )\n\n"
        ),
        addition=METRICS_ALIAS_SETUP,
    )
    # Drop the 2 owned counter init lines (now manager-owned).
    text = text.replace("        self.num_retracted_reqs: int = 0\n", "")
    text = text.replace("        self.num_paused_reqs: int = 0\n", "")
    # ``install_device_timer_on_runners`` callsite — drop entirely.
    # The manager ctor (inserted later in __init__) calls it internally as
    # part of its post-``init_metrics`` setup; calling it from __init__
    # before the ctor exists would AttributeError.
    text = text.replace(
        "        self.install_device_timer_on_runners()\n",
        "",
    )
    # Patch the manager ctor body to call install_device_timer_on_runners()
    # after init_metrics().
    target_text = target.read_text()
    target_text = target_text.replace(
        "        # Run the original init_metrics body inline.\n"
        "        self.init_metrics(tp_rank, pp_rank, dp_rank)\n",
        "        # Run the original init_metrics body inline.\n"
        "        self.init_metrics(tp_rank, pp_rank, dp_rank)\n"
        "        # ``install_device_timer_on_runners`` was originally called\n"
        "        # from Scheduler.__init__ right after init_model_worker; we\n"
        "        # invoke it here so callers don't need a separate hook.\n"
        "        self.install_device_timer_on_runners()\n",
    )
    target.write_text(target_text)
    # Hot-path callsites.
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
    # ``spec_total_num_*`` lifetime counters now live on metrics_reporter.
    # Rewrite every read/write in scheduler.py — covers the lambda kwargs in
    # the C13 RPC dispatch + the C16 streamer init insert + the local reads
    # in get_internal_state / set_internal_state.
    text = text.replace(
        "self.spec_total_num_accept_tokens",
        "self.metrics_reporter.spec_total_num_accept_tokens",
    )
    text = text.replace(
        "self.spec_total_num_forward_ct",
        "self.metrics_reporter.spec_total_num_forward_ct",
    )
    # ``last_gen_throughput`` and ``step_time_dict`` are read by
    # ``get_internal_state`` in scheduler.py; both moved to metrics_reporter.
    text = text.replace(
        'ret["last_gen_throughput"] = self.last_gen_throughput',
        'ret["last_gen_throughput"] = self.metrics_reporter.last_gen_throughput',
    )
    text = text.replace(
        'ret["step_time_dict"] = self.step_time_dict',
        'ret["step_time_dict"] = self.metrics_reporter.step_time_dict',
    )
    # Ownership migration: ``self.num_retracted_reqs = len(retracted_reqs)``.
    text = text.replace(
        "            self.num_retracted_reqs = len(retracted_reqs)\n",
        "            self.metrics_reporter.num_retracted_reqs = len(retracted_reqs)\n",
    )
    sched.write_text(text)

    # Update output_processor_mixin: 3 callsites.
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

    # Update disaggregation/prefill.py: 1 callsite.
    text = pre.read_text()
    text = text.replace(
        "        self.report_prefill_stats(",
        "        self.metrics_reporter.report_prefill_stats(",
    )
    pre.write_text(text)

    # Update dllm/mixin/scheduler.py: 1 callsite + 1 local import.
    text = dllm.read_text()
    text = text.replace(
        "        self.report_prefill_stats(",
        "        self.metrics_reporter.report_prefill_stats(",
    )
    text = text.replace(
        "from sglang.srt.observability.scheduler_metrics_mixin import PrefillStats",
        "from sglang.srt.managers.scheduler_components.metrics_reporter import PrefillStats",
    )
    dllm.write_text(text)

    # Update schedule_batch.py: TYPE_CHECKING import of PrefillStats.
    schedule_batch = wt / "python/sglang/srt/managers/schedule_batch.py"
    text = schedule_batch.read_text()
    text = text.replace(
        "from sglang.srt.observability.scheduler_metrics_mixin import PrefillStats",
        "from sglang.srt.managers.scheduler_components.metrics_reporter import PrefillStats",
    )
    schedule_batch.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
