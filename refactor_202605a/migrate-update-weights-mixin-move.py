#!/usr/bin/env python3
"""Mechanical move for ``migrate-update-weights-mixin``: cut 12 @staticmethods
+ 2 module-level helpers (``_export_static_state``, ``_import_static_state``)
from ``scheduler_update_weights_mixin.py``, paste them into
``SchedulerWeightUpdaterManager`` class body / module-level area at
``scheduler_components/weight_updater.py``. Drop the source file, drop
``SchedulerUpdateWeightsMixin`` from the Scheduler inheritance list, and
update the 10 RPC dispatch lambdas to direct ``self.weight_updater.<method>``
references (pure prefix transformation).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "migrate-update-weights-mixin-move"
SUBJECT = "Move 12 methods into SchedulerWeightUpdaterManager class body"
BODY = """\
Mechanical cut + paste for the ``migrate-update-weights-mixin`` mech move.

Cut the 12 @staticmethods + 2 module-level helpers
(``_export_static_state`` / ``_import_static_state``) from
``scheduler_update_weights_mixin.py`` and paste them into the new file
``scheduler_components/weight_updater.py`` (methods into
``SchedulerWeightUpdaterManager`` class body, helpers at module level).

The source file is deleted, the ``SchedulerUpdateWeightsMixin`` entry is
dropped from the Scheduler inheritance list, and its ``from`` import is
dropped from ``scheduler.py``.

Method bodies otherwise byte-identical. ``@staticmethod`` decorators
dropped; ``self: "SchedulerWeightUpdaterManager"`` annotation simplified to
bare ``self``.

10 RPC dispatch lambdas in ``init_request_dispatcher`` collapse to direct
``self.weight_updater.<method>`` references (pure prefix transformation).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_update_weights_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/weight_updater.py"

    # Split mixin file at ``class SchedulerUpdateWeightsMixin:`` and at the
    # end of class body (where module-level helpers start).
    mixin_text = mixin.read_text()
    class_anchor = "class SchedulerUpdateWeightsMixin:\n"
    if class_anchor not in mixin_text:
        raise RuntimeError("SchedulerUpdateWeightsMixin class anchor missing")
    pre_class, _, class_body_and_after = mixin_text.partition(class_anchor)

    # The module-level helpers ``_export_static_state`` and
    # ``_import_static_state`` come AFTER the class body. Split on the first
    # ``def _export_static_state(model):`` (which is at module level — 0 indent).
    helper_anchor = "def _export_static_state(model):\n"
    if helper_anchor not in class_body_and_after:
        raise RuntimeError("_export_static_state helper anchor missing")
    class_body, _, helpers_block = class_body_and_after.partition(helper_anchor)
    helpers_block = helper_anchor + helpers_block  # re-include the def line

    # class_body now contains the 12 @staticmethods (4-space indented).
    methods_block = class_body
    # Drop @staticmethod decorators + simplify type-flip annotation.
    methods_block = methods_block.replace("    @staticmethod\n", "")
    methods_block = methods_block.replace(
        'self: "SchedulerWeightUpdaterManager"',
        "self",
    )

    # Compose the new target file. Take the existing class skeleton (from
    # prep) and append methods to its body; append module-level helpers after
    # the class.

    new_target_text = '''from __future__ import annotations

import logging
import traceback
from typing import Callable, Tuple

import torch

from sglang.srt.constants import (
    GPU_MEMORY_ALL_TYPES,
    GPU_MEMORY_TYPE_CUDA_GRAPH,
    GPU_MEMORY_TYPE_KV_CACHE,
    GPU_MEMORY_TYPE_WEIGHTS,
)
from sglang.srt.managers.io_struct import (
    CheckWeightsReqInput,
    CheckWeightsReqOutput,
    DestroyWeightsUpdateGroupReqInput,
    DestroyWeightsUpdateGroupReqOutput,
    GetWeightsByNameReqInput,
    GetWeightsByNameReqOutput,
    InitWeightsUpdateGroupReqInput,
    InitWeightsUpdateGroupReqOutput,
    ReleaseMemoryOccupationReqInput,
    ReleaseMemoryOccupationReqOutput,
    ResumeMemoryOccupationReqInput,
    ResumeMemoryOccupationReqOutput,
    UpdateWeightFromDiskReqInput,
    UpdateWeightFromDiskReqOutput,
    UpdateWeightsFromDistributedReqInput,
    UpdateWeightsFromDistributedReqOutput,
    UpdateWeightsFromIPCReqInput,
    UpdateWeightsFromIPCReqOutput,
    UpdateWeightsFromTensorReqInput,
    UpdateWeightsFromTensorReqOutput,
)

logger = logging.getLogger(__name__)


class SchedulerWeightUpdaterManager:
    """Hot weight-update / memory-occupation / model-save / weight-inspection
    control surface. Composition target on Scheduler
    (``self.weight_updater``)."""

    def __init__(
        self,
        *,
        tp_worker,
        draft_worker,
        tp_cpu_group,
        memory_saver_adapter,
        flush_cache: Callable[..., bool],
        is_fully_idle: Callable[..., bool],
    ) -> None:
        self.tp_worker = tp_worker
        self.draft_worker = draft_worker
        self.tp_cpu_group = tp_cpu_group
        self.memory_saver_adapter = memory_saver_adapter
        self.flush_cache = flush_cache
        self.is_fully_idle = is_fully_idle
        self.offload_tags: set = set()

''' + methods_block.rstrip() + "\n\n\n" + helpers_block.rstrip() + "\n"

    target.write_text(new_target_text)

    # Delete the old mixin file.
    mixin.unlink()

    # Update Scheduler: drop mixin import + remove from inheritance list.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="from sglang.srt.managers.scheduler_update_weights_mixin import (\n"
        "    SchedulerUpdateWeightsMixin,\n"
        ")\n",
        new="",
    )
    text = replace_call_site(
        text,
        old="    SchedulerUpdateWeightsMixin,\n",
        new="",
    )

    # 10 RPC dispatch lambdas → direct ``self.weight_updater.<method>``
    # references. Robust to black formatting (single-line or multi-line).
    # ``lambda req: self.<method>(self.weight_updater, req)`` →
    # ``self.weight_updater.<method>``.
    text = re.sub(
        r"lambda req: self\.(\w+)\(\s*self\.weight_updater,\s*req\s*\)",
        r"self.weight_updater.\1",
        text,
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
