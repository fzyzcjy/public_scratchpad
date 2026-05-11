#!/usr/bin/env python3
"""Move ``on_idle`` and ``_maybe_log_idle_metrics`` from
``scheduler_runtime_checker_mixin.py`` to the Scheduler main class. Per
``components/scheduler/index.md`` these stay on Scheduler proper rather than
splitting into the upcoming pool_stats_observer / invariant_checker sisters.

Bodies are byte-identical apart from dropping the ``: Scheduler`` parameter
annotation.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "move-on-idle-to-scheduler-main"
SUBJECT = "Move on_idle and _maybe_log_idle_metrics from runtime_checker mixin to Scheduler main class"
BODY = """\
Move ``on_idle`` (the idle housekeeping orchestrator) and
``_maybe_log_idle_metrics`` (its 30-second metric flush helper) from
``scheduler_runtime_checker_mixin.py`` into the Scheduler main class
(``scheduler.py``), per the explicit human decision on these two methods'
ownership in ``components/scheduler/index.md``.

The two methods are placed immediately before ``Scheduler.is_fully_idle`` to
keep the idle-related cluster contiguous. Bodies are byte-identical apart
from dropping the ``self: Scheduler`` parameter annotation (now redundant
since the methods live on Scheduler directly).

No behavior change. Subsequent commits (``introduce-pool-stats-observer`` /
``introduce-invariant-checker`` / ``introduce-kv-events-publisher`` /
``introduce-metrics-reporter``) will rewire the cross-class calls these
bodies make (``self.get_pool_stats()`` / ``self._check_all_pools`` /
``self._publish_kv_events`` / ``self.reset_device_timer_window`` etc.) to
the new sister components.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"

    # Cut bottom-up so earlier line ranges stay valid.
    s, e = find_method_lines(
        src.read_text(),
        class_name="SchedulerRuntimeCheckerMixin",
        method_name="on_idle",
    )
    on_idle_text = cut_lines(src, s, e)

    s, e = find_method_lines(
        src.read_text(),
        class_name="SchedulerRuntimeCheckerMixin",
        method_name="_maybe_log_idle_metrics",
    )
    log_idle_text = cut_lines(src, s, e)

    # Drop ``: Scheduler`` annotations.
    on_idle_text = on_idle_text.replace("self: Scheduler", "self")
    log_idle_text = log_idle_text.replace("self: Scheduler", "self")

    # Insert into Scheduler main class just before ``def is_fully_idle``.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="    def is_fully_idle(self, for_health_check=False) -> bool:\n",
        new=log_idle_text
        + on_idle_text
        + "    def is_fully_idle(self, for_health_check=False) -> bool:\n",
    )
    # ``_maybe_log_idle_metrics`` body uses ``QueueCount.from_reqs(...)`` —
    # add the import (was previously transitively pulled in via the
    # runtime_checker mixin).
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components import kv_cache\n",
        addition="from sglang.srt.observability.metrics_collector import QueueCount\n",
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
