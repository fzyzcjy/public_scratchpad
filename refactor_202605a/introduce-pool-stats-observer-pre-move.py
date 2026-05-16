#!/usr/bin/env python3
"""Pure dataclass move pre-move for ``introduce-pool-stats-observer``:
cut the ``PoolStats`` dataclass from
``scheduler_runtime_checker_mixin.py`` and paste it verbatim into the
new ``scheduler_components/pool_stats_observer.py``. Rewire the mixin
to re-import ``PoolStats`` from the new module, and update the one test
that imports ``PoolStats`` directly.

This is a standalone cross-file move per ``MECH_COMMIT_SPLIT.md`` §"例外"
(move a dataclass between modules; body byte-identical). The follow-up
``introduce-pool-stats-observer-prep`` adds the ``SchedulerPoolStatsObserver``
class skeleton + ctor wiring + method type-flips.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_class_lines, insert_after
from _runner import run_pr

ID = "introduce-pool-stats-observer-pre-move"
SUBJECT = "Move PoolStats dataclass to scheduler_components.pool_stats_observer"
BODY = """\
Pure dataclass move pre-move for ``introduce-pool-stats-observer``.

Cut the ``PoolStats`` dataclass body byte-identical from
``scheduler_runtime_checker_mixin.py`` and paste it into the new
module ``scheduler_components/pool_stats_observer.py``. Rewire the
mixin to re-import ``PoolStats`` from the new module so existing
references continue to resolve. The test
``test/registered/unit/managers/test_scheduler_pause_generation.py``
also imports ``PoolStats`` directly; its import path is updated in this
commit.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


TARGET_FILE_HEADER = '''\
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple


class SchedulerStats: ...  # type: ignore[no-redef]


'''


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_runtime_checker_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/pool_stats_observer.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"

    src_text = src.read_text()

    # 1. Cut PoolStats dataclass from mixin file (verbatim move to target).
    s, e = find_class_lines(src_text, class_name="PoolStats")
    lines = src_text.splitlines(keepends=True)
    pool_stats_block = "".join(lines[s:e]).rstrip() + "\n"
    del lines[s:e]
    src_text = "".join(lines)

    # 2. Add PoolStats import to mixin (it now lives in the new module).
    src_text = insert_after(
        src_text,
        anchor="from sglang.srt.utils.watchdog import WatchdogRaw\n",
        addition="\nfrom sglang.srt.managers.scheduler_components.pool_stats_observer import PoolStats\n",
    )
    src.write_text(src_text)

    # 3. Build the new target file: header + PoolStats dataclass.
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    if not pkg_init.exists():
        pkg_init.write_text("")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_FILE_HEADER + pool_stats_block)

    # 4. Test file: update the PoolStats import to the new module.
    test_pause = wt / "test/registered/unit/managers/test_scheduler_pause_generation.py"
    if test_pause.exists():
        ttext = test_pause.read_text()
        ttext = ttext.replace(
            "from sglang.srt.managers.scheduler_runtime_checker_mixin import PoolStats\n",
            "from sglang.srt.managers.scheduler_components.pool_stats_observer import PoolStats\n",
        )
        test_pause.write_text(ttext)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
