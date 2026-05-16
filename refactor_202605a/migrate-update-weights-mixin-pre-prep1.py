#!/usr/bin/env python3
"""Pure block-move pre-prep1 for ``migrate-update-weights-mixin``: relocate
the ``self.offload_tags = set()`` assignment within ``Scheduler.__init__``
to the spot where the upcoming ``self.weight_updater`` ctor will land,
i.e. immediately before ``self.init_request_dispatcher()``. The next
commit (``-prep``) lifts this assignment into
``SchedulerWeightUpdaterManager.__init__`` as ``self.offload_tags = set()``.

This is a standalone block-relocation commit per
``MECH_COMMIT_SPLIT.md`` §"例外" (move a hunk within the same class). The
field semantics are unchanged: ``self.offload_tags`` still lives on the
Scheduler instance, and the ``dp_attn_adapter`` ctor still reads it via
``offload_tags=self.offload_tags``.

Diff is one delete from
``Scheduler.init_watch_dog_memory_saver_input_blocker`` plus one insert
into ``Scheduler.__init__`` just before
``self.init_request_dispatcher()``.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "migrate-update-weights-mixin-pre-prep1"
SUBJECT = "Relocate self.offload_tags assignment near future weight_updater ctor (block move)"
BODY = """\
Pure block-move pre-prep1 for ``migrate-update-weights-mixin``.

Move ``self.offload_tags = set()`` out of
``Scheduler.init_watch_dog_memory_saver_input_blocker`` and into
``Scheduler.__init__`` immediately before
``self.init_request_dispatcher()`` — the spot where the upcoming
``self.weight_updater = SchedulerWeightUpdaterManager(...)`` ctor will
land in ``-prep``. The next commit migrates the field's ownership into
``SchedulerWeightUpdaterManager.__init__``.

Diff is one delete plus one insert. Field semantics unchanged:
``self.offload_tags`` still lives on Scheduler in this commit, and the
``dp_attn_adapter`` ctor's ``offload_tags=self.offload_tags`` kwarg still
resolves.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    text = sched.read_text()

    # 1. Cut the offload_tags assignment from
    #    init_watch_dog_memory_saver_input_blocker.
    text = replace_call_site(
        text,
        old="        self.memory_saver_adapter = TorchMemorySaverAdapter.create(\n"
        "            enable=self.server_args.enable_memory_saver\n"
        "        )\n"
        "        self.offload_tags = set()\n",
        new="        self.memory_saver_adapter = TorchMemorySaverAdapter.create(\n"
        "            enable=self.server_args.enable_memory_saver\n"
        "        )\n",
    )

    # 2. Insert at the new home — right before init_request_dispatcher().
    text = replace_call_site(
        text,
        old="        # Init request dispatcher\n"
        "        self.init_request_dispatcher()\n",
        new="        self.offload_tags = set()\n"
        "\n"
        "        # Init request dispatcher\n"
        "        self.init_request_dispatcher()\n",
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
