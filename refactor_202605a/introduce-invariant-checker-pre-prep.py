#!/usr/bin/env python3
"""Pre-prep for ``introduce-invariant-checker``: cross-file move of the
``create_scheduler_watchdog`` module-level free function from
``scheduler_runtime_checker_mixin.py`` into ``scheduler.py`` (placed just
before ``class Scheduler(``). Pure mechanical block move — no body rewrites
except the ``Scheduler`` forward-reference quoting (the function is now
defined above ``class Scheduler``, so we use a string annotation to avoid
``F821 Undefined name``).

This satisfies the ``MECH_COMMIT_SPLIT.md`` rule that cross-file relocations
of existing module-level free functions belong in a separate single-commit
move — the only true ``pre-prep`` candidate for C10.

The ``count_*_leak_warnings`` ownership migration that was previously also
flagged for pre-prep cannot land here: those counters are dynamically
created via ``setattr(obj, counter_name, ...)`` in ``raise_error_or_warn``
and have no static definition on ``Scheduler`` to relocate. They will be
introduced as fresh fields on ``SchedulerInvariantChecker.__init__`` in the
``-prep`` commit, since that is the first commit where their migration
target exists.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_function_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-invariant-checker-pre-prep"
SUBJECT = "Move create_scheduler_watchdog from runtime_checker mixin to scheduler.py"
BODY = """\
Pre-prep for the ``introduce-invariant-checker`` mech split.

Cut ``create_scheduler_watchdog`` (module-level free function) from
``scheduler_runtime_checker_mixin.py`` and paste verbatim just before
``class Scheduler(`` in ``scheduler.py``. Wrap the ``scheduler: Scheduler``
annotation in a string forward reference (``scheduler: "Scheduler"``)
because ``Scheduler`` is defined later in the same module.

Imports updated:
- ``scheduler.py``: drop ``create_scheduler_watchdog`` from the grouped
  ``from sglang.srt.managers.scheduler_runtime_checker_mixin import (...)``
  block; add ``from sglang.srt.utils.watchdog import WatchdogRaw``.
- ``scheduler_runtime_checker_mixin.py``: drop the now-unused
  ``from sglang.srt.utils.watchdog import WatchdogRaw`` import.

Body otherwise byte-identical (``git --color-moved=dimmed-zebra`` shows the
moved function as a single hunk). This is a pure mechanical relocation of
an already-existing free function (per MECH_COMMIT_SPLIT.md \"何时不拆\"
single-commit exception).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"

    # 1. Cut ``create_scheduler_watchdog`` from the mixin file.
    s, e = find_function_lines(src.read_text(), function_name="create_scheduler_watchdog")
    watchdog_text = cut_lines(src, s, e)
    # ``Scheduler`` is defined later in scheduler.py, so use a string forward
    # reference to avoid an ``F821 Undefined name`` lint error.
    watchdog_text = watchdog_text.replace(
        "scheduler: Scheduler,", 'scheduler: "Scheduler",'
    )

    # 2. Drop now-unused WatchdogRaw import from the mixin.
    src_text = src.read_text()
    src_text = replace_call_site(
        src_text,
        old="from sglang.srt.utils.watchdog import WatchdogRaw\n",
        new="",
    )
    src.write_text(src_text)

    # 3. Update scheduler.py imports: drop ``create_scheduler_watchdog`` from
    # the grouped import block; add ``WatchdogRaw``.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old=(
            "from sglang.srt.managers.scheduler_runtime_checker_mixin import (\n"
            "    SchedulerRuntimeCheckerMixin,\n"
            "    create_scheduler_watchdog,\n"
            ")\n"
        ),
        new=(
            "from sglang.srt.managers.scheduler_runtime_checker_mixin import (\n"
            "    SchedulerRuntimeCheckerMixin,\n"
            ")\n"
        ),
    )
    # Add WatchdogRaw import alongside the existing scheduler-component imports.
    # Anchor on the SchedulerRuntimeCheckerMixin import block so the new line
    # is unambiguously placed.
    text = insert_after(
        text,
        anchor=(
            "from sglang.srt.managers.scheduler_runtime_checker_mixin import (\n"
            "    SchedulerRuntimeCheckerMixin,\n"
            ")\n"
        ),
        addition="from sglang.srt.utils.watchdog import WatchdogRaw\n",
    )

    # 4. Insert ``create_scheduler_watchdog`` immediately before ``class Scheduler(``.
    text = replace_call_site(
        text,
        old="class Scheduler(\n",
        new=watchdog_text.rstrip() + "\n\n\nclass Scheduler(\n",
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
