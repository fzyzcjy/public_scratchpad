#!/usr/bin/env python3
"""Non-mech cleanup tail commit for the scheduler.py free-item relocation.

Deletes ``is_work_request`` in ``scheduler.py`` — codebase-wide grep shows
zero callers (dead code from a now-defunct dispatch path).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_function_lines
from _runner import run_pr

ID = "cleanup-scheduler-py-free-items"
SUBJECT = "Delete dead is_work_request from scheduler.py"
BODY = """\
Non-mech cleanup tail commit for the preceding free-item relocation.

Deletes ``is_work_request`` in ``scheduler.py`` — codebase-wide grep
shows zero callers (dead code from a now-defunct dispatch path).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"

    s, e = find_function_lines(sched.read_text(), function_name="is_work_request")
    cut_lines(sched, s, e)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
