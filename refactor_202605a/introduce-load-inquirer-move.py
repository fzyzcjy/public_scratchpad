#!/usr/bin/env python3
"""Mechanical move for ``introduce-load-inquirer``: cut ``get_loads``
@staticmethod from ``SchedulerMetricsMixin``, paste it into the
``SchedulerLoadInquirer`` class body. Drop ``@staticmethod``, simplify
``self: "SchedulerLoadInquirer"`` → bare ``self``, rewrite callers from
``self.get_loads(self.load_inquirer, ...)`` →
``self.load_inquirer.get_loads(...)``.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, rewrite_method_call_site
from _runner import run_pr

ID = "introduce-load-inquirer-move"
SUBJECT = "Move get_loads into SchedulerLoadInquirer class body"
BODY = """\
Mechanical cut + paste for the ``introduce-load-inquirer`` mech move.

Cut ``get_loads`` (@staticmethod after prep) from
``SchedulerMetricsMixin`` and paste it into ``SchedulerLoadInquirer``
class body in ``scheduler_components/load_inquirer.py``.

Drop ``@staticmethod`` decorator; simplify ``self: SchedulerLoadInquirer``
type annotation to bare ``self``. Body otherwise byte-identical.

Callers updated (pure prefix transformation):
- RPC dispatch lambda in ``Scheduler.init_request_dispatcher``
- ``stream_output_generation`` in
  ``scheduler_output_processor_mixin.py``
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _strip_staticmethod_typeflip(method_text: str, *, target_class: str) -> str:
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace(f"self: \"{target_class}\"", "self")
    return text


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_mixin = wt / "python/sglang/srt/managers/scheduler_output_processor_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/load_inquirer.py"

    # Cut get_loads.
    s, e = find_method_lines(
        src.read_text(),
        class_name="SchedulerMetricsMixin",
        method_name="get_loads",
    )
    block = cut_lines(src, s, e)
    block = _strip_staticmethod_typeflip(block, target_class="SchedulerLoadInquirer")

    rtext = target.read_text()
    rtext = rtext.rstrip() + "\n\n" + block.rstrip() + "\n"
    target.write_text(rtext)

    # Caller rewrites — use the robust helper (handles single-line and
    # multi-line black-formatted calls alike).
    for f in (sched, output_mixin):
        ftext = f.read_text()
        try:
            ftext = rewrite_method_call_site(
                ftext, method_name="get_loads", target_attr="load_inquirer"
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
