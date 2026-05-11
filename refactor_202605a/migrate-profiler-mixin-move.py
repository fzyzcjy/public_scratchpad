#!/usr/bin/env python3
"""Mechanical move for ``migrate-profiler-mixin``: cut the 6 prep-form
@staticmethods (and supporting module-level statements: NPU patch block +
logger) from ``scheduler_profiler_mixin.py`` and paste them into
``scheduler_components/profiler_manager.py``. Drop ``@staticmethod``
decorators; simplify ``self: "SchedulerProfilerManager"`` annotation to
bare ``self``. Delete the source file. Drop ``SchedulerProfilerMixin``
from the Scheduler inheritance list. Collapse the 2 prep-form callers
``self._profile_batch_predicate(self.profiler_manager, ...)`` →
``self.profiler_manager._profile_batch_predicate(...)`` (pure prefix
transformation).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, replace_call_site, rewrite_method_call_site
from _runner import run_pr

ID = "migrate-profiler-mixin-move"
SUBJECT = "Hand profiler controls over to SchedulerProfilerManager"
BODY = """\
Mechanical cut + paste for the ``migrate-profiler-mixin`` mech move.

Cut the 6 @staticmethods (``_init_profile`` / ``_start_profile`` /
``_merge_profile_traces`` / ``_stop_profile`` / ``_profile_batch_predicate``
/ ``_profile``) from ``scheduler_profiler_mixin.py`` and paste them into
``SchedulerProfilerManager`` class body in
``scheduler_components/profiler_manager.py``. The NPU platform-patch
block + module logger relocate alongside as supporting module-level
statements. The source file is deleted; ``SchedulerProfilerMixin`` is
dropped from the Scheduler inheritance list and its import from
``scheduler.py`` is removed.

Method bodies otherwise byte-identical. ``@staticmethod`` decorators
dropped; ``self: "SchedulerProfilerManager"`` annotation simplified to
bare ``self``.

Callers updated (pure prefix transformation):
  ``self._profile_batch_predicate(self.profiler_manager, ...)`` →
  ``self.profiler_manager._profile_batch_predicate(...)``
  ``self._profile(self.profiler_manager, ...)`` →
  ``self.profiler_manager._profile(...)``

Test fixture rewires ``SchedulerProfilerMixin._init_profile`` import to
``SchedulerProfilerManager._init_profile`` at its new path.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


METHOD_ORDER = [
    "_init_profile",
    "_start_profile",
    "_merge_profile_traces",
    "_stop_profile",
    "_profile_batch_predicate",
    "_profile",
]


# Supporting module-level statements relocated from the mixin file to the
# new target file. NPU patch block + logger; we drop the
# ``Path / typing / sglang.srt.environ / ProfileManager`` imports because
# the target header already has them.
TARGET_PRELUDE_NEW_IMPORTS = """\
import logging
import os
import time

import torch

from sglang.srt.managers.io_struct import ProfileReq, ProfileReqOutput, ProfileReqType
from sglang.srt.model_executor.forward_batch_info import ForwardMode
from sglang.srt.server_args import get_global_server_args
from sglang.srt.utils import is_npu
from sglang.srt.utils.profile_merger import ProfileMerger

if TYPE_CHECKING:
    from sglang.srt.managers.schedule_batch import ScheduleBatch

_is_npu = is_npu()
if _is_npu:
    import torch_npu

    patches = [
        ["profiler.profile", torch_npu.profiler.profile],
        ["profiler.ProfilerActivity.CUDA", torch_npu.profiler.ProfilerActivity.NPU],
        ["profiler.ProfilerActivity.CPU", torch_npu.profiler.ProfilerActivity.CPU],
    ]
    torch_npu._apply_patches(patches)

logger = logging.getLogger(__name__)


"""


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_profiler_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/profiler_manager.py"
    test_profile = wt / "test/registered/unit/utils/test_profile_merger.py"

    # 1. Cut 6 @staticmethods bottom-up from the mixin.
    method_blocks = []
    for name in reversed(METHOD_ORDER):
        s, e = find_method_lines(
            mixin.read_text(),
            class_name="SchedulerProfilerMixin",
            method_name=name,
        )
        block = cut_lines(mixin, s, e)
        # Drop @staticmethod + simplify type-flip annotation.
        block = block.replace("    @staticmethod\n", "", 1)
        block = block.replace('self: "SchedulerProfilerManager"', "self")
        method_blocks.append(block)
    method_blocks.reverse()

    # 2. Append into the SchedulerProfilerManager class body. The skeleton's
    #    ctor ends at the last ``self.rpd_profiler = None`` line — append
    #    methods after (methods already have 4-space class-body indent).
    target_text = target.read_text()
    target_text = target_text.rstrip() + "\n\n" + "".join(method_blocks).rstrip() + "\n"

    # 3. Splice the supporting module-level prelude (NPU patches, logger,
    #    extra imports) into the target file, between the existing imports
    #    block and the class declaration.
    #    Target file currently starts with: imports header (no TYPE_CHECKING)
    #    then ``class SchedulerProfilerManager:``. We add ``TYPE_CHECKING``
    #    to the typing import and insert the prelude.
    target_text = target_text.replace(
        "from typing import Callable, List, Optional",
        "from typing import TYPE_CHECKING, Callable, List, Optional",
    )
    target_text = target_text.replace(
        "from sglang.srt.environ import envs  # noqa: F401\n",
        "from sglang.srt.environ import envs  # noqa: F401\n"
        + TARGET_PRELUDE_NEW_IMPORTS.lstrip("\n"),
        1,
    )
    target.write_text(target_text)

    # 4. Delete the now-empty mixin file.
    mixin.unlink()

    # 5. Update Scheduler: drop mixin import + remove from inheritance list.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="from sglang.srt.managers.scheduler_profiler_mixin import SchedulerProfilerMixin\n",
        new="",
    )
    text = replace_call_site(
        text,
        old="    SchedulerProfilerMixin,\n",
        new="",
    )
    # 6. Caller rewrites — pure prefix transformation. Use the robust helper
    #    so single-line and multi-line black-formatted calls both work.
    for method in ("_profile_batch_predicate", "_profile"):
        try:
            text = rewrite_method_call_site(
                text, method_name=method, target_attr="profiler_manager"
            )
        except ValueError:
            pass
    sched.write_text(text)

    # 7. Test fixture: switch import + symbol to the new class location.
    test_text = test_profile.read_text()
    test_text = replace_call_site(
        test_text,
        old="from sglang.srt.managers.scheduler_profiler_mixin import SchedulerProfilerMixin\n"
        "\n"
        "        sig = inspect.signature(SchedulerProfilerMixin._init_profile)\n",
        new="from sglang.srt.managers.scheduler_components.profiler_manager import (\n"
        "            SchedulerProfilerManager,\n"
        "        )\n"
        "\n"
        "        sig = inspect.signature(SchedulerProfilerManager._init_profile)\n",
    )
    test_profile.write_text(test_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
