#!/usr/bin/env python3
"""Pre-rename for ``introduce-metrics-reporter``: add the leading ``_``
on 2 methods so they become private inside the upcoming
``SchedulerMetricsReporter`` (they are only called intra-class).

- ``update_lora_metrics`` → ``_update_lora_metrics``
- ``calculate_utilization`` → ``_calculate_utilization``

This commit is **rename only** — method bodies are byte-identical. All
internal callsites (within the mixin) are updated in the same commit so
the tree stays runnable.
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

ID = "introduce-metrics-reporter-pre-rename"
SUBJECT = "Add leading _ on update_lora_metrics / calculate_utilization (pre-rename for metrics-reporter)"
BODY = """\
Privacy flip pre-rename for the ``introduce-metrics-reporter`` mech
move. Two ``SchedulerMetricsMixin`` methods are made private because
they are intra-class helpers; the upcoming reporter class will expose
them as ``_*`` to clarify the boundary.

- ``update_lora_metrics`` → ``_update_lora_metrics``
- ``calculate_utilization`` → ``_calculate_utilization``

Body byte-identical. Callsites updated within the mixin body.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"

    text = src.read_text()
    text = text.replace(
        "    def update_lora_metrics(self: Scheduler):",
        "    def _update_lora_metrics(self: Scheduler):",
    )
    text = text.replace(
        "    def calculate_utilization(self: Scheduler):",
        "    def _calculate_utilization(self: Scheduler):",
    )
    text = text.replace("self.update_lora_metrics(", "self._update_lora_metrics(")
    text = text.replace("self.calculate_utilization(", "self._calculate_utilization(")
    src.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
