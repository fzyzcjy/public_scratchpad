#!/usr/bin/env python3
"""Mechanical move for ``introduce-load-inquirer``: cut ``get_loads``
and ``_get_num_pending_tokens`` (both @staticmethod after prep) from
``SchedulerMetricsMixin``, paste them into the ``SchedulerLoadInquirer``
class body. Drop ``@staticmethod``, simplify
``self: "SchedulerLoadInquirer"`` → bare ``self``, rewrite callers from
``self.<method>(self.load_inquirer, ...)`` →
``self.load_inquirer.<method>(...)``.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import (
    cut_lines,
    ensure_bare_imports,
    ensure_imports,
    find_method_lines,
    rewrite_method_call_site,
)
from _runner import run_pr

ID = "introduce-load-inquirer-move"
SUBJECT = "Move queue-load reporting to SchedulerLoadInquirer"
BODY = """\
Mechanical cut + paste for the ``introduce-load-inquirer`` mech move.

Cut ``get_loads`` and ``_get_num_pending_tokens`` (both @staticmethod
after prep) from ``SchedulerMetricsMixin`` and paste them into
``SchedulerLoadInquirer`` class body in
``scheduler_components/load_inquirer.py``.

Drop ``@staticmethod`` decorator; simplify ``self: SchedulerLoadInquirer``
type annotation to bare ``self``. Body otherwise byte-identical.

Callers updated (pure prefix transformation):
- RPC dispatch lambda in ``Scheduler.init_request_dispatcher``
- ``stream_output_generation`` in
  ``scheduler_output_processor_mixin.py``
- ``_get_new_batch_prefill_raw`` in ``Scheduler``
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _strip_staticmethod_typeflip(method_text: str, *, target_class: str) -> str:
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace(f"self: \"{target_class}\"", "self")
    import re
    text = re.sub(
        r"self\.(\w+)\(\s*self\.load_inquirer\s*(?:,\s*)?",
        r"self.\1(",
        text,
        flags=re.DOTALL,
    )
    return text


def _cut_method_to_target(src: Path, target: Path, *, method_name: str) -> None:
    s, e = find_method_lines(
        src.read_text(),
        class_name="SchedulerMetricsMixin",
        method_name=method_name,
    )
    block = cut_lines(src, s, e)
    block = _strip_staticmethod_typeflip(block, target_class="SchedulerLoadInquirer")

    rtext = target.read_text()
    rtext = rtext.rstrip() + "\n\n" + block.rstrip() + "\n"
    target.write_text(rtext)


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/load_inquirer.py"

    # Cut _get_num_pending_tokens first (preserves line numbers for get_loads).
    _cut_method_to_target(src, target, method_name="_get_num_pending_tokens")
    _cut_method_to_target(src, target, method_name="get_loads")

    # Re-inject imports the method bodies need (prep wrote these; ruff F401
    # stripped them while the bodies were absent).
    rtext = target.read_text()
    rtext = ensure_bare_imports(rtext, ["import time\n"])
    rtext = ensure_imports(
        rtext,
        runtime={
            "sglang.srt.disaggregation.utils": "DisaggregationMode",
            "sglang.srt.managers.io_struct": (
                "DisaggregationMetrics",
                "GetLoadsReqInput",
                "GetLoadsReqOutput",
                "LoRAMetrics",
                "MemoryMetrics",
                "QueueMetrics",
                "SpeculativeMetrics",
            ),
        },
    )
    target.write_text(rtext)

    # Caller rewrites — use the robust helper (handles single-line and
    # multi-line black-formatted calls alike).
    for f in (sched, output_mixin):
        ftext = f.read_text()
        for method_name in ("get_loads", "_get_num_pending_tokens"):
            try:
                ftext = rewrite_method_call_site(
                    ftext, method_name=method_name, target_attr="load_inquirer"
                )
            except ValueError:
                pass
        f.write_text(ftext)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
