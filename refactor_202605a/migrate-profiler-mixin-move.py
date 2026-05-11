#!/usr/bin/env python3
"""Mechanical move for ``migrate-profiler-mixin``: cut 6 @staticmethods from
``scheduler_profiler_mixin.py``, paste them into ``SchedulerProfilerManager``
at ``scheduler_components/profiler_manager.py``. Drop the source file, drop
``SchedulerProfilerMixin`` from the Scheduler inheritance list, and update
the 2 hot-path callers to ``self.profiler_manager.<method>(...)`` form
(pure prefix transformation).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site, rewrite_method_call_site
from _runner import run_pr

ID = "migrate-profiler-mixin-move"
SUBJECT = "Move 6 methods into SchedulerProfilerManager class body"
BODY = """\
Mechanical cut + paste for the ``migrate-profiler-mixin`` mech move.

Cut the 6 @staticmethods (after prep: ``_init_profile`` / ``_start_profile``
/ ``_merge_profile_traces`` / ``_stop_profile`` / ``_profile_batch_predicate``
/ ``_profile``) from ``scheduler_profiler_mixin.py`` and paste them into
``SchedulerProfilerManager`` class body in
``scheduler_components/profiler_manager.py``.

Module-level NPU patch block, logger, and supporting imports relocate to
the new file. The source file is deleted, the ``SchedulerProfilerMixin``
entry is dropped from the Scheduler inheritance list, and its ``from``
import is dropped from ``scheduler.py``.

Method bodies otherwise byte-identical. ``@staticmethod`` decorators
dropped; ``self: "SchedulerProfilerManager"`` annotation simplified to bare
``self``.

Callers updated (pure prefix transformation):
  ``self._profile_batch_predicate(self.profiler_manager, ...)`` →
  ``self.profiler_manager._profile_batch_predicate(...)``
  ``self._profile(self.profiler_manager, ...)`` →
  ``self.profiler_manager._profile(...)``

Test fixture rewires the ``SchedulerProfilerMixin._init_profile`` import to
``SchedulerProfilerManager._init_profile``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_profiler_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/profiler_manager.py"
    test_profile = wt / "test/registered/unit/utils/test_profile_merger.py"

    # The mixin file at this point contains: imports, NPU patch block, logger,
    # ``class SchedulerProfilerMixin:`` (with 6 @staticmethods inside). We need
    # to relocate everything to the target file, preserving the methods'
    # 4-space indent (since they're going into ``SchedulerProfilerManager``
    # class body, which has matching indent).

    mixin_text = mixin.read_text()
    target_text = target.read_text()

    # Anchor: split mixin file at ``class SchedulerProfilerMixin:`` line.
    class_anchor = "class SchedulerProfilerMixin:\n"
    if class_anchor not in mixin_text:
        raise RuntimeError("SchedulerProfilerMixin class anchor missing")
    pre_class, _, class_body_with_methods = mixin_text.partition(class_anchor)
    # ``class_body_with_methods`` starts with the methods (4-space indented).

    # Strip out the ``from sglang.srt.environ import envs`` /
    # ``ProfileManager`` / ``Path`` / ``Optional, List`` imports we already
    # have in the target header (avoid dup imports). Everything else (NPU
    # patches, logger, other imports) prepends as supporting module-level
    # code BEFORE the class. We do this by composing a fresh target file.

    # Compose target file. Move all imports + module-level statements from the
    # mixin file (minus the class declaration), then prepend the existing
    # target-file class skeleton + its imports.
    #
    # The current target file structure (from prep):
    #   line 1+: imports header
    #   blank line
    #   class SchedulerProfilerManager:
    #     ...ctor...
    #
    # We append the 6 methods to the class body. Mixin module-level statements
    # (NPU patches, ``_is_npu``, ``logger``) need to be merged into the
    # target's module-level section, deduplicated.

    # Strategy: dedupe imports and module-level statements by simple substring
    # check. Build a new target file from scratch with the canonical layout.

    methods_block = class_body_with_methods  # 4-space indented @staticmethods

    # Drop ``@staticmethod`` decorators and simplify type-flip on all methods.
    methods_block = methods_block.replace("    @staticmethod\n", "")
    methods_block = methods_block.replace(
        'self: "SchedulerProfilerManager"',
        "self",
    )

    new_target_text = '''from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import torch

from sglang.srt.environ import envs
from sglang.srt.managers.io_struct import ProfileReq, ProfileReqOutput, ProfileReqType
from sglang.srt.model_executor.forward_batch_info import ForwardMode
from sglang.srt.server_args import get_global_server_args
from sglang.srt.utils import is_npu
from sglang.srt.utils.profile_merger import ProfileMerger
from sglang.srt.utils.profile_utils import ProfileManager

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


class SchedulerProfilerManager:
    """torch profiler / RPD / cuda profiler lifecycle. Composition target on
    Scheduler (``self.profiler_manager``). Owns 19 mutable runtime fields."""

    def __init__(
        self,
        *,
        ps,
        dp_tp_cpu_group,
    ) -> None:
        self.ps = ps
        self.dp_tp_cpu_group = dp_tp_cpu_group

        if envs.SGLANG_PROFILE_V2.get():
            self._profile_manager = ProfileManager(
                ps=self.ps,
                cpu_group=self.dp_tp_cpu_group,
            )
            return

        self.torch_profiler = None
        self.torch_profiler_output_dir: Optional[Path] = None
        self.profiler_activities: Optional[List[str]] = None
        self.profile_id: Optional[str] = None

        self.profiler_start_forward_ct: Optional[int] = None
        self.profiler_target_forward_ct: Optional[int] = None

        self.profiler_prefill_ct: Optional[int] = None
        self.profiler_decode_ct: Optional[int] = None
        self.profiler_target_prefill_ct: Optional[int] = None
        self.profiler_target_decode_ct: Optional[int] = None

        self.profile_by_stage: bool = False
        self.profile_in_progress: bool = False
        self.merge_profiles = False

        # For ROCM
        self.rpd_profiler = None

'''
    # methods_block already includes a leading 4-space indented line for the
    # first method (since it was inside ``class SchedulerProfilerMixin:`` body).
    # We add an explicit blank line between ctor close and first method.
    new_target_text = new_target_text + methods_block.rstrip() + "\n"

    target.write_text(new_target_text)

    # Delete the old mixin file.
    mixin.unlink()

    # Update Scheduler: drop mixin import + remove from inheritance list.
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

    # Caller rewrites — use the robust helper (handles single-line and
    # multi-line black-formatted calls alike).
    for method in ("_profile_batch_predicate", "_profile"):
        try:
            text = rewrite_method_call_site(
                text, method_name=method, target_attr="profiler_manager"
            )
        except ValueError:
            pass
    sched.write_text(text)

    # Test fixture: switch import + symbol to the new class location.
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
