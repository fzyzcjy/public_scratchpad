#!/usr/bin/env python3
"""Move ``_get_num_pending_tokens`` from ``SchedulerMetricsMixin`` to the
Scheduler main class. Per ``components/scheduler/index.md`` this method's
sole caller (``_get_new_batch_prefill_raw``) is in the R3 待定区, so the
method stays on Scheduler proper.

Body byte-identical apart from dropping the ``: Scheduler`` annotation.
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

ID = "move-num-pending-tokens-to-scheduler-main"
SUBJECT = "Move _get_num_pending_tokens from metrics mixin to Scheduler main class"
BODY = """\
Move ``_get_num_pending_tokens`` from ``SchedulerMetricsMixin`` to the
Scheduler main class. Body byte-identical apart from dropping the
``: Scheduler`` annotation. Sole caller (``_get_new_batch_prefill_raw``)
remains on Scheduler — no callsite update needed.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"

    s, e = find_method_lines(
        src.read_text(),
        class_name="SchedulerMetricsMixin",
        method_name="_get_num_pending_tokens",
    )
    method_text = cut_lines(src, s, e)
    method_text = method_text.replace("self: Scheduler", "self")

    # Insert into Scheduler main class just before ``def is_fully_idle`` (the
    # idle/health cluster anchor used by the previous moves).
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="    def is_fully_idle(self, for_health_check=False) -> bool:\n",
        new=method_text + "    def is_fully_idle(self, for_health_check=False) -> bool:\n",
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
