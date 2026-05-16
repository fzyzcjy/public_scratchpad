#!/usr/bin/env python3
"""Pure dataclass move pre-move for ``introduce-kv-events-publisher``:
cut the ``KvMetrics`` dataclass from
``observability/scheduler_metrics_mixin.py`` and paste it verbatim into
the new ``scheduler_components/kv_events_publisher.py``. Rewire the
mixin to re-import ``KvMetrics`` from the new module so the existing
``KvMetrics()`` reference in ``emit_kv_metrics`` continues to resolve.

This is a standalone cross-file move per ``MECH_COMMIT_SPLIT.md`` §"例外"
(move a dataclass between modules; body byte-identical). The follow-up
``introduce-kv-events-publisher-prep`` adds the
``SchedulerKvEventsPublisher`` class skeleton + ctor wiring + method
type-flips.
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

ID = "introduce-kv-events-publisher-pre-move"
SUBJECT = "Move KvMetrics dataclass to scheduler_components.kv_events_publisher"
BODY = """\
Pure dataclass move pre-move for ``introduce-kv-events-publisher``.

Cut the ``KvMetrics`` dataclass body byte-identical from
``observability/scheduler_metrics_mixin.py`` and paste it into the new
module ``scheduler_components/kv_events_publisher.py``. Rewire the
mixin to re-import ``KvMetrics`` from the new module so the existing
``KvMetrics()`` reference in ``emit_kv_metrics`` continues to resolve.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


TARGET_FILE_HEADER = '''\
from __future__ import annotations

import dataclasses
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sglang.srt.disaggregation.kv_events import EventPublisherFactory, KVEventBatch


class SchedulerStats: ...  # type: ignore[no-redef]


'''


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/observability/scheduler_metrics_mixin.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/kv_events_publisher.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"

    # 1. Cut the KvMetrics dataclass out of the mixin (verbatim move to target).
    src_text = src.read_text()
    s, e = find_class_lines(src_text, class_name="KvMetrics")
    kv_metrics_block = "".join(src_text.splitlines(keepends=True)[s:e]).rstrip() + "\n"
    lines = src_text.splitlines(keepends=True)
    del lines[s:e]
    src_text = "".join(lines)

    # 2. Re-import KvMetrics from the new module so the existing
    #    ``KvMetrics()`` reference inside the mixin still resolves.
    src_text = insert_after(
        src_text,
        anchor="from sglang.srt.utils.scheduler_status_logger import SchedulerStatusLogger\n",
        addition="from sglang.srt.managers.scheduler_components.kv_events_publisher import KvMetrics\n",
    )
    src.write_text(src_text)

    # 3. Build the new target file: header + KvMetrics dataclass.
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    if not pkg_init.exists():
        pkg_init.write_text("")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(TARGET_FILE_HEADER + kv_metrics_block)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
