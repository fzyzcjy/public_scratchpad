#!/usr/bin/env python3
"""1:N split #3 of ``SchedulerMetricsMixin``: the remaining 14 reporter
methods + ``PrefillStats`` dataclass move to ``SchedulerMetricsReporter`` at
``scheduler_components/observability/metrics_reporter.py``. The metrics
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
``scheduler_components/observability/metrics_reporter.py``. Scheduler holds
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
            server_args=self.server_args,
            disaggregation_mode=self.disaggregation_mode,
            spec_algorithm=self.spec_algorithm,
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
        server_args,
        disaggregation_mode,
        spec_algorithm,
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
    ) -> None:
        # Owned counters (ownership migration from Scheduler).
        self.num_retracted_reqs: int = 0
        self.num_paused_reqs: int = 0
        # Stash deps + sisters + Callable getters.
        self.server_args = server_args
        self.disaggregation_mode = disaggregation_mode
        self.spec_algorithm = spec_algorithm
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
        # Run the original init_metrics body inline.
        self.init_metrics(tp_rank, pp_rank, dp_rank)

'''


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    pre = wt / "python/sglang/srt/disaggregation/prefill.py"
    dllm = wt / "python/sglang/srt/dllm/mixin/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/observability/metrics_reporter.py"

    text = src.read_text()

    # Drop ``: Scheduler`` annotations.
    text = text.replace("self: Scheduler", "self")

    # The ``if TYPE_CHECKING:`` block has multiple imports (Scheduler, Req,
    # PrefillAdder, etc.). Drop only the Scheduler import line — keep the
    # block + the ``TYPE_CHECKING`` typing import intact for the others.
    text = text.replace(
        "    from sglang.srt.managers.scheduler import Scheduler\n",
        "",
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

    # The original init_metrics body has ``self.forward_ct_decode = 0`` —
    # the previous text.replace turned this into
    # ``self.get_forward_ct()_decode = 0`` which is broken. Rewrite back.
    text = text.replace(
        "self.get_forward_ct()_decode", "self.forward_ct_decode"
    )
    # Same for ``self.get_forward_ct()_decode % self.server_args.decode_log_interval``
    # and any other ``self.forward_ct_*`` field — restore the field-access form.

    target.write_text(text)
    src.unlink()

    # Update Scheduler.
    text = sched.read_text()
    text = text.replace(
        "from sglang.srt.observability.scheduler_metrics_mixin import (\n"
        "    SchedulerMetricsMixin,\n"
        ")\n",
        "",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.observability.load_inquirer import (\n    SchedulerLoadInquirer,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.observability.metrics_reporter import (\n"
            "    SchedulerMetricsReporter,\n"
            ")\n"
        ),
    )
    text = replace_call_site(text, old="    SchedulerMetricsMixin,\n", new="")
    text = replace_call_site(
        text,
        old="        self.is_initializing = False\n",
        new=SCHEDULER_INIT_INSERT + "        self.is_initializing = False\n",
    )
    # Drop the 2 owned counter init lines (now manager-owned).
    text = text.replace("        self.num_retracted_reqs: int = 0\n", "")
    text = text.replace("        self.num_paused_reqs: int = 0\n", "")
    # Drop ``self.init_metrics(tp_rank, pp_rank, dp_rank)`` (now in manager ctor).
    text = text.replace(
        "        self.init_metrics(tp_rank, pp_rank, dp_rank)\n",
        "",
    )
    # ``install_device_timer_on_runners`` callsite.
    text = text.replace(
        "        self.install_device_timer_on_runners()\n",
        "        self.metrics_reporter.install_device_timer_on_runners()\n",
    )
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

    # Update dllm/mixin/scheduler.py: 1 callsite.
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
