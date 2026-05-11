#!/usr/bin/env python3
"""Mechanical move for ``introduce-metrics-reporter``: rename the
``observability/scheduler_metrics_mixin.py`` file to
``managers/scheduler_components/metrics_reporter.py``. No method bodies
change. Update remaining ``from sglang.srt.observability.scheduler_metrics_mixin``
imports (in scheduler.py, dllm/mixin/scheduler.py, schedule_batch.py)
to the new module path.

Because the prep step already turned the contents into
``SchedulerMetricsReporter`` and wired all hot-path callers through the
sister handle, this commit is a pure file-relocation + import-rewrite —
the doc's "纯 file 重命名 / 整文件移动" single-commit exception in
spirit, but kept as a separate commit so the prep + move pairing is
preserved.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _runner import run_pr

ID = "introduce-metrics-reporter-move"
SUBJECT = "Move metrics_reporter file into scheduler_components/; delete metrics mixin"
BODY = """\
Mechanical file relocation for the ``introduce-metrics-reporter`` mech
move.

- Rename ``python/sglang/srt/observability/scheduler_metrics_mixin.py``
  to ``python/sglang/srt/managers/scheduler_components/metrics_reporter.py``.
  Contents are byte-identical to the post-prep state.
- Update imports in 3 files
  (``scheduler.py``, ``dllm/mixin/scheduler.py``, ``schedule_batch.py``)
  to point at the new module path.
- Remove ``scheduler_metrics_mixin`` from the module tree.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/metrics_reporter.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    dllm = wt / "python/sglang/srt/dllm/mixin/scheduler.py"
    schedule_batch = wt / "python/sglang/srt/managers/schedule_batch.py"

    # Relocate (cut + paste — file contents byte-identical).
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(src.read_text())
    src.unlink()

    # Rewrite the 3 import sites to the new module path.
    text = sched.read_text()
    text = text.replace(
        "from sglang.srt.observability.scheduler_metrics_mixin import (\n"
        "    RECORD_STEP_TIME,\n"
        "    PrefillStats,\n"
        "    SchedulerMetricsReporter,\n"
        ")\n",
        "from sglang.srt.managers.scheduler_components.metrics_reporter import (\n"
        "    RECORD_STEP_TIME,\n"
        "    PrefillStats,\n"
        "    SchedulerMetricsReporter,\n"
        ")\n",
    )
    sched.write_text(text)

    text = dllm.read_text()
    text = text.replace(
        "from sglang.srt.observability.scheduler_metrics_mixin import PrefillStats",
        "from sglang.srt.managers.scheduler_components.metrics_reporter import PrefillStats",
    )
    dllm.write_text(text)

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
