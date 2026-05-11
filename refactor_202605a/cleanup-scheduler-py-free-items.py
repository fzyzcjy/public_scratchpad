#!/usr/bin/env python3
"""Non-mech cleanup of two ``scheduler.py``-related items split out from the
preceding mech move (``move-free-items-from-scheduler-py``).

1. Delete dead-code function ``is_work_request`` in ``scheduler.py``
   (codebase-wide grep shows 0 callers).
2. Rename ``SenderWrapper`` → ``SchedulerOutputSender`` to resolve the
   namesake collision with ``multi_tokenizer_mixin.SenderWrapper`` (a
   different class with a different signature, used by ``tokenizer_manager``).

Bundled because both are tiny non-mech edits on the same surface.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_function_lines, replace_call_site
from _runner import run_pr

ID = "cleanup-scheduler-py-free-items"
SUBJECT = "Drop dead is_work_request and rename SenderWrapper for namesake-collision resolution"
BODY = """\
Two non-mech cleanups bundled into one commit:

1. **Delete** ``is_work_request`` in ``scheduler.py`` — codebase-wide grep
   shows zero callers. Dead code from a now-defunct dispatch path.

2. **Rename** ``SenderWrapper`` → ``SchedulerOutputSender`` (in the new
   ``scheduler_components/output_sender.py`` introduced by the preceding
   mech move). Motivation: ``multi_tokenizer_mixin`` has a different class
   *also* named ``SenderWrapper`` with a different signature, used by
   ``tokenizer_manager``. Two distinct entities with the same name is a
   readability hazard. The new name expresses the actual role (scheduler →
   tokenizer / detokenizer output sender).

Caller-site impact:
- ``is_work_request``: pure deletion, no callers to update.
- ``SchedulerOutputSender``: 4 callsites in ``scheduler.py`` + 1 import.
"""
AREA = "mech_scheduler_followup"
BASE = "tom_refactor_202605a/followup/mech_scheduler_followup_a"
AREA_BRANCH = f"tom_refactor_202605a/followup/{AREA}_b"


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    output_sender = wt / "python/sglang/srt/managers/scheduler_components/output_sender.py"

    # 1. Delete dead function is_work_request.
    s, e = find_function_lines(sched.read_text(), function_name="is_work_request")
    cut_lines(sched, s, e)

    # 2. Rename SenderWrapper → SchedulerOutputSender in output_sender.py.
    text = output_sender.read_text()
    text = replace_call_site(
        text,
        old="class SenderWrapper:",
        new="class SchedulerOutputSender:",
    )
    # Drop the rename-pending note from the module docstring.
    text = replace_call_site(
        text,
        old=(
            "Note: there is a separate ``SenderWrapper`` class in\n"
            "``multi_tokenizer_mixin`` with a different signature. The namesake\n"
            "collision is resolved by a follow-up commit which renames this one\n"
            "to ``SchedulerOutputSender``.\n"
        ),
        new=(
            "Note: ``multi_tokenizer_mixin`` has a different class also formerly\n"
            "named ``SenderWrapper`` (different signature, used by\n"
            "``tokenizer_manager``); this class was renamed from ``SenderWrapper``\n"
            "to ``SchedulerOutputSender`` to disambiguate.\n"
        ),
    )
    output_sender.write_text(text)

    # 3. Rename uses in scheduler.py.
    sched_text = sched.read_text()
    sched_text = replace_call_site(
        sched_text,
        old="from sglang.srt.managers.scheduler_components.output_sender import SenderWrapper\n",
        new="from sglang.srt.managers.scheduler_components.output_sender import SchedulerOutputSender\n",
    )
    sched_text = sched_text.replace("SenderWrapper(", "SchedulerOutputSender(")
    sched.write_text(sched_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
