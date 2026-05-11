#!/usr/bin/env python3
"""Mechanical move step for ``extract-get-draft-kv-pool``: cut the
``get_draft_kv_pool`` @staticmethod from Scheduler, paste it as a free
function in ``scheduler_components/kv_cache.py``. Drop ``@staticmethod``,
dedent 4 spaces, rewrite 2 callers ``Scheduler.foo(...)`` → ``kv_cache.foo(...)``,
add module import.

This commit is **body-byte-equivalent** with respect to the prep commit
(``extract-get-draft-kv-pool-prep``); ``git --color-moved-ws=allow-indentation-change``
should mark the entire function body as moved.
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
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-get-draft-kv-pool-move"
SUBJECT = "Move get_draft_kv_pool to scheduler_components/kv_cache.py"
BODY = """\
Mechanical cut + paste for the ``extract-get-draft-kv-pool`` mech move.

Cut ``Scheduler.get_draft_kv_pool`` (a @staticmethod after the prep
commit) and paste it as a module-level free function in
``python/sglang/srt/managers/scheduler_components/kv_cache.py`` (new
package). Drop ``@staticmethod`` decorator; body bytes unchanged.

2 caller sites updated: ``Scheduler.get_draft_kv_pool(...)`` →
``kv_cache.get_draft_kv_pool(...)`` (pure prefix replacement). Add import
``from sglang.srt.managers.scheduler_components import kv_cache``.

Verify via ``git --color-moved-ws=allow-indentation-change``: the entire
function body should be marked as moved.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations


'''


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"
    kvc = wt / "python/sglang/srt/managers/scheduler_components/kv_cache.py"

    # Create the new package skeleton.
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    pkg_init.write_text("")

    # Cut the @staticmethod from Scheduler.
    s, e = find_method_lines(
        sched.read_text(),
        class_name="Scheduler",
        method_name="get_draft_kv_pool",
    )
    method_text = cut_lines(sched, s, e)

    # Drop @staticmethod decorator (first occurrence, leading indent stripped
    # together with the rest in the dedent step below).
    function_text = method_text.replace("    @staticmethod\n", "", 1)
    function_text = dedent_method_to_function(function_text)

    kvc.write_text(HEADER + function_text)

    # Pure-prefix rewrite of callers.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="Scheduler.get_draft_kv_pool(",
        new="kv_cache.get_draft_kv_pool(",
    )

    # Add import. Anchor: the stable ``scheduler_input_blocker`` line in the
    # alphabetically-sorted scheduler_* import block.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_input_blocker import SchedulerInputBlocker\n",
        addition="from sglang.srt.managers.scheduler_components import kv_cache\n",
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
