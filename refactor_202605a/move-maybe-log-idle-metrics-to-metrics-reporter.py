#!/usr/bin/env python3
"""Cross-mixin move: cut ``_maybe_log_idle_metrics`` from
``SchedulerRuntimeCheckerMixin`` and paste it into the
``SchedulerMetricsReporter`` class body. Body reads of mode-conditional
Scheduler state are rewritten to ``self.get_X()`` Callable getter calls —
the getter fields were added to the ``SchedulerMetricsReporter`` ctor in the
C14 prep commit. Pool-stats sibling reads (``self.get_pool_stats()`` /
``self._streaming_session_count()`` / ``self._session_held_tokens()``) are
rewritten to the post-C9 form (``self.pool_stats_observer.X()``), since the
mixin file was skipped by C9's body-rewrite pass (which only touched
``scheduler.py``).

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

ID = "move-maybe-log-idle-metrics-to-metrics-reporter"
SUBJECT = "Hand idle-metrics logging over to SchedulerMetricsReporter"
BODY = """\
Cut ``_maybe_log_idle_metrics`` from ``SchedulerRuntimeCheckerMixin`` and
paste it into ``SchedulerMetricsReporter`` body. Body reads of
mode-conditional Scheduler state (``running_batch`` / ``grammar_manager``
/ ``disaggregation_mode`` / 4 disagg queues) become ``self.get_X()``
Callable getter calls — the getter fields were already added to the
reporter ctor in the C14 prep commit. Pool-stats sibling reads
(``self.get_pool_stats()`` / ``self._streaming_session_count()`` /
``self._session_held_tokens()``) are rewritten to the post-C9 form
(``self.pool_stats_observer.X()``), which C9 skipped here because its
rewrite pass only touched ``scheduler.py``.

Single caller (in ``Scheduler.on_idle``, hoisted to the Scheduler main
class by C8) is updated: ``self._maybe_log_idle_metrics()`` →
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
# Reporter already owns ``waiting_queue`` / ``stats`` / ``metrics_collector``
# / ``enable_priority_scheduling`` / ``current_scheduler_metrics_enabled``
# as direct ctor / init_metrics fields, so those reads stay as ``self.X``.
BODY_SUBSTITUTIONS = [
    # Pool-stats sibling reads — C9 didn't rewrite the mixin file, only
    # ``scheduler.py``. Apply the equivalent post-C9 form here.
    ("self.get_pool_stats()", "self.pool_stats_observer.get_pool_stats()"),
    (
        "self.stats.num_streaming_sessions = self._streaming_session_count()",
        "self.stats.num_streaming_sessions = self.pool_stats_observer.streaming_session_count()",
    ),
    (
        "self.stats.streaming_session_held_tokens = self._session_held_tokens()",
        "self.stats.streaming_session_held_tokens = self.pool_stats_observer.session_held_tokens()",
    ),
    # Mutable scheduler state — route through Callable getters (added to the
    # reporter ctor in the C14 prep commit).
    ("self.running_batch.reqs", "self.get_running_batch().reqs"),
    ("len(self.grammar_manager)", "len(self.get_grammar_manager())"),
    ("self.disaggregation_mode", "self.get_disaggregation_mode()"),
    (
        "self.disagg_prefill_bootstrap_queue.queue",
        "self.get_disagg_prefill_bootstrap_queue().queue",
    ),
    (
        "self.disagg_prefill_inflight_queue",
        "self.get_disagg_prefill_inflight_queue()",
    ),
    (
        "self.disagg_decode_prealloc_queue.queue",
        "self.get_disagg_decode_prealloc_queue().queue",
    ),
    (
        "self.disagg_decode_transfer_queue.queue",
        "self.get_disagg_decode_transfer_queue().queue",
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
