#!/usr/bin/env python3
"""Move ``on_idle`` from ``scheduler_runtime_checker_mixin.py`` to the
Scheduler main class. Per ``components/scheduler/index.md`` this stays on
Scheduler proper rather than splitting into the upcoming pool_stats_observer
/ invariant_checker sisters.

Body byte-identical apart from dropping the ``: Scheduler`` parameter
annotation.

Note: ``_maybe_log_idle_metrics`` (``on_idle``'s 30-second metric flush
helper) stays in ``SchedulerRuntimeCheckerMixin`` for now; a downstream
commit (``move-maybe-log-idle-metrics-to-metrics-reporter``) cuts it
directly from the mixin into ``SchedulerMetricsReporter`` after C14 builds
the reporter class. ``self._maybe_log_idle_metrics()`` from ``on_idle``
still resolves via mixin inheritance until that later commit rewrites the
caller.
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

ID = "move-on-idle-to-scheduler-main"
SUBJECT = "Move on_idle from runtime_checker mixin into Scheduler"
BODY = """\
Move ``on_idle`` (the idle housekeeping orchestrator) from
``scheduler_runtime_checker_mixin.py`` into the Scheduler main class
(``scheduler.py``), per the explicit human decision on this method's
ownership in ``components/scheduler/index.md``.

The method is placed immediately before ``Scheduler.is_fully_idle`` to
keep the idle-related cluster contiguous. Body is byte-identical apart
from dropping the ``self: Scheduler`` parameter annotation (now redundant
since it lives on Scheduler directly).

``_maybe_log_idle_metrics`` (``on_idle``'s metric flush helper) is
intentionally NOT moved here. It is a metrics-collection routine, not an
orchestrator, so it gets relocated directly from
``SchedulerRuntimeCheckerMixin`` into ``SchedulerMetricsReporter`` by a
downstream commit (``move-maybe-log-idle-metrics-to-metrics-reporter``).
Until that commit runs, ``self._maybe_log_idle_metrics()`` inside
``on_idle`` continues to resolve via mixin inheritance.

No behavior change. Subsequent commits (``introduce-pool-stats-observer`` /
``introduce-invariant-checker`` / ``introduce-kv-events-publisher`` /
``introduce-metrics-reporter``) will rewire the cross-class calls this
body makes (``self.get_pool_stats()`` / ``self._check_all_pools`` /
``self._publish_kv_events`` / ``self.reset_device_timer_window`` etc.) to
the new sister components.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"

    s, e = find_method_lines(
        src.read_text(),
        class_name="SchedulerRuntimeCheckerMixin",
        method_name="on_idle",
    )
    on_idle_text = cut_lines(src, s, e)

    # Drop ``: Scheduler`` annotation.
    on_idle_text = on_idle_text.replace("self: Scheduler", "self")

    # Insert into Scheduler main class just before ``def is_fully_idle``.
    # Also annotate ``for_health_check`` with its inferred type.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="    def is_fully_idle(self, for_health_check=False) -> bool:\n",
        new=on_idle_text
        + "    def is_fully_idle(self, for_health_check: bool = False) -> bool:\n",
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
