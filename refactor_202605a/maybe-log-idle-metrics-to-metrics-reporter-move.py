#!/usr/bin/env python3
"""Cross-mixin move: cut ``_maybe_log_idle_metrics`` from
``SchedulerRuntimeCheckerMixin`` and paste it into the
``SchedulerMetricsReporter`` class body. Body reads of Scheduler state
are rewritten to ``self.scheduler.X`` form, matching the back-reference
ctor introduced in the C14 prep commit. Pool-stats sibling reads
(``self.get_pool_stats()`` / ``self._streaming_session_count()`` /
``self._session_held_tokens()``) are rewritten to the post-C9 form
(``self.scheduler.pool_stats_observer.X()``).

The sole caller in ``Scheduler.on_idle`` (now on the Scheduler main class
since C8) is rewired from ``self._maybe_log_idle_metrics()`` →
``self.metrics_reporter._maybe_log_idle_metrics()``.

This commit walks ``MECH_COMMIT_SPLIT.md``'s "trivial 单 method 跨类移动"
single-commit exception (not the prep+move two-step) — body bytes are
mechanically substituted via a fixed lookup table; there is no signature
redesign or behavior change.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, replace_call_site
from _runner import run_pr

ID = "maybe-log-idle-metrics-to-metrics-reporter-move"
SUBJECT = "Move idle-metrics logging to SchedulerMetricsReporter"
BODY = """\
Cut ``_maybe_log_idle_metrics`` from ``SchedulerRuntimeCheckerMixin`` and
paste it into ``SchedulerMetricsReporter`` body. Body reads of Scheduler
state (``running_batch`` / ``waiting_queue`` / ``grammar_manager`` /
``disaggregation_mode`` / disagg queues / ``enable_priority_scheduling``)
become ``self.scheduler.X``, matching the back-reference ctor introduced
in the metrics-reporter prep commit. Pool-stats sibling reads
(``self.get_pool_stats()`` / ``self._streaming_session_count()`` /
``self._session_held_tokens()``) are rewritten to the
pool-stats-observer form
(``self.scheduler.pool_stats_observer.X()``).

Single caller (in ``Scheduler.on_idle``, hoisted to the Scheduler main
class by the on-idle move commit) is updated:
``self._maybe_log_idle_metrics()`` →
``self.metrics_reporter._maybe_log_idle_metrics()``.

This is a pure relocation — no behavior change.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Body-text substitutions applied to the cut method before it lands inside
# ``SchedulerMetricsReporter``. Each (old, new) pair MUST appear in the body
# at least once (no silent no-ops).
#
# Reporter owns ``stats`` / ``metrics_collector`` /
# ``current_scheduler_metrics_enabled`` (direct ctor / init_metrics fields),
# so those reads stay as ``self.X``. Everything else is a Scheduler field
# accessed via the ``scheduler`` back-reference.
BODY_SUBSTITUTIONS = [
    # Pool-stats sibling reads — pool_stats_observer is on Scheduler (C9
    # introduced it as a sister class), reached via the back-reference.
    # Note: pre-move source body already references
    # ``self.pool_stats_observer.X()`` (the C9 cascade rewrote the
    # legacy ``self.get_pool_stats()`` / ``self._streaming_session_count()``
    # / ``self._session_held_tokens()`` form), so the substitution here
    # only inserts the ``scheduler`` back-reference hop.
    (
        "self.pool_stats_observer.get_pool_stats()",
        "self.scheduler.pool_stats_observer.get_pool_stats()",
    ),
    (
        "self.pool_stats_observer.streaming_session_count()",
        "self.scheduler.pool_stats_observer.streaming_session_count()",
    ),
    (
        "self.pool_stats_observer.session_held_tokens()",
        "self.scheduler.pool_stats_observer.session_held_tokens()",
    ),
    # Scheduler-owned state — route through the back-reference.
    ("self.running_batch.reqs", "self.scheduler.running_batch.reqs"),
    ("len(self.grammar_manager)", "len(self.scheduler.grammar_manager)"),
    (
        "priority_enabled = self.enable_priority_scheduling",
        "priority_enabled = self.scheduler.enable_priority_scheduling",
    ),
    (
        "self.waiting_queue, priority_enabled",
        "self.scheduler.waiting_queue, priority_enabled",
    ),
    (
        "if self.disaggregation_mode == DisaggregationMode.PREFILL:",
        "if self.scheduler.disaggregation_mode == DisaggregationMode.PREFILL:",
    ),
    (
        "if self.disaggregation_mode == DisaggregationMode.DECODE:",
        "if self.scheduler.disaggregation_mode == DisaggregationMode.DECODE:",
    ),
    (
        "self.disagg_prefill_bootstrap_queue.queue",
        "self.scheduler.disagg_prefill_bootstrap_queue.queue",
    ),
    (
        "self.disagg_prefill_inflight_queue, priority_enabled",
        "self.scheduler.disagg_prefill_inflight_queue, priority_enabled",
    ),
    (
        "self.disagg_decode_prealloc_queue.queue",
        "self.scheduler.disagg_decode_prealloc_queue.queue",
    ),
    (
        "self.disagg_decode_transfer_queue.queue",
        "self.scheduler.disagg_decode_transfer_queue.queue",
    ),
]


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/metrics_reporter.py"

    # 1. Cut _maybe_log_idle_metrics from the runtime_checker mixin.
    s, e = find_method_lines(
        src.read_text(),
        class_name="SchedulerRuntimeCheckerMixin",
        method_name="_maybe_log_idle_metrics",
    )
    method_text = cut_lines(src, s, e)

    # 2. Drop the ``: Scheduler`` annotation (now lives on the reporter).
    method_text = method_text.replace("self: Scheduler", "self")

    # 3. Apply body substitutions. Each pair must match (fail-loud).
    for old, new in BODY_SUBSTITUTIONS:
        if old not in method_text:
            raise ValueError(f"body-substitution anchor not found: {old!r}")
        method_text = method_text.replace(old, new)

    # 4. Append the rewritten method to SchedulerMetricsReporter's class
    #    body. Anchor on the class header so we land inside the class.
    target_text = target.read_text()
    # Place the method at the end of the class body. Since the file ends
    # with the class's last method, appending to file end with a leading
    # blank line is equivalent to appending to the class body (no module-
    # level content follows the class).
    target.write_text(target_text.rstrip() + "\n\n" + method_text.rstrip() + "\n")

    # 5. Rewrite the single caller in Scheduler.on_idle (lives in scheduler.py
    #    main since C8).
    sched_text = sched.read_text()
    sched_text = replace_call_site(
        sched_text,
        old="        self._maybe_log_idle_metrics()\n",
        new="        self.metrics_reporter._maybe_log_idle_metrics()\n",
    )

    # 6. With the last method gone, retire the runtime_checker mixin: drop
    #    ``SchedulerRuntimeCheckerMixin`` from the inheritance list / import
    #    block in ``scheduler.py``, then delete the file. (The earlier
    #    ``introduce-invariant-checker-move`` deferred this cleanup so that
    #    ``_maybe_log_idle_metrics`` could continue to resolve via the mixin
    #    inheritance until now.)
    sched_text = replace_call_site(
        sched_text,
        old=(
            "from sglang.srt.managers.scheduler_runtime_checker_mixin import (\n"
            "    SchedulerRuntimeCheckerMixin,\n"
            ")\n"
        ),
        new="",
    )
    sched_text = replace_call_site(
        sched_text, old="    SchedulerRuntimeCheckerMixin,\n", new=""
    )
    sched.write_text(sched_text)
    src.unlink()


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
