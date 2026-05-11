#!/usr/bin/env python3
"""Mechanical move for ``introduce-invariant-checker``: delete the
``scheduler_runtime_checker_mixin.py`` file. After the prep commit, the file
hosts only 10 orphaned check methods (no caller references them — the new
``SchedulerInvariantChecker`` class with the re-shaped bodies is already
installed in ``scheduler_components/invariant_checker.py``, callers all
dispatch through ``self.invariant_checker.*``). Deleting the file is the
"removal half" of the 1:N split's last commit.

This is the documented exception to Template B's cut+paste pattern: C10 is
the final split commit whose new class body was hand-rewritten in the prep
commit (different signatures, kwarg-only conversion, ownership migration of
counter fields), so the move commit just deletes the orphan code rather than
cutting + pasting bodies — semantically equivalent to "the methods moved
out, the file is empty, delete it".
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

ID = "introduce-invariant-checker-move"
SUBJECT = "Delete scheduler_runtime_checker_mixin.py (10 orphaned check methods)"
BODY = """\
Mechanical removal for the ``introduce-invariant-checker`` mech move (split
#2 of ``SchedulerRuntimeCheckerMixin``, the tail commit).

After the prep commit, ``scheduler_runtime_checker_mixin.py`` hosts only
10 orphaned check methods — no caller in the codebase references them:
- ``SchedulerInvariantChecker`` is fully wired up
  (``scheduler_components/invariant_checker.py``);
- ``Scheduler`` no longer inherits ``SchedulerRuntimeCheckerMixin``;
- ``create_scheduler_watchdog`` lives in ``scheduler.py``;
- all callsites dispatch through ``self.invariant_checker.*``.

This commit just deletes the now-orphaned mixin file. Equivalent to the
"removal half" of Template B's cut+paste, but the bodies were re-shaped in
the prep commit (kwarg-only signatures, ownership migration of counter
fields, ``self.last_batch`` / ``self.running_batch`` reads → per-call
kwargs) so there is nothing to byte-faithfully paste; the orphan code is
simply discarded.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    if src.exists():
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
