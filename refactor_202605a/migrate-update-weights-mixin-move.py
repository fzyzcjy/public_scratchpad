#!/usr/bin/env python3
"""Mechanical move for ``migrate-update-weights-mixin``: cut the 13
prep-form @staticmethods + 2 module-level helpers (``_export_static_state``
/ ``_import_static_state``) from ``scheduler_update_weights_mixin.py`` and
paste them into ``scheduler_components/weight_updater.py``. Drop
``@staticmethod`` decorators; simplify ``self:
"SchedulerWeightUpdaterManager"`` annotation to bare ``self``. Delete the
source file. Drop ``SchedulerUpdateWeightsMixin`` from the Scheduler
inheritance list. Collapse the 10 prep-form dispatch lambdas
``lambda req: self.<method>(self.weight_updater, req)`` → direct refs
``self.weight_updater.<method>`` (pure prefix transformation).
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
from _helpers import cut_lines, find_function_lines, find_method_lines, replace_call_site
from _runner import run_pr

ID = "migrate-update-weights-mixin-move"
SUBJECT = "Move weight-update RPC handlers to SchedulerWeightUpdaterManager"
BODY = """\
Mechanical cut + paste for the ``migrate-update-weights-mixin`` mech move.

Cut the @staticmethods plus the module-level helpers
(``_export_static_state`` / ``_import_static_state``) from
``scheduler_update_weights_mixin.py`` and paste them into the existing
``scheduler_components/weight_updater.py`` (methods into
``SchedulerWeightUpdaterManager`` class body, helpers at module level
after the class). Supporting module-level imports (``logging`` /
``traceback`` / ``torch`` / ``Tuple`` / constants / io_struct symbols)
relocate alongside.

The source file is deleted; ``SchedulerUpdateWeightsMixin`` is dropped
from the Scheduler inheritance list and its import is removed.

Method bodies otherwise byte-identical. ``@staticmethod`` decorators
dropped; ``self: "SchedulerWeightUpdaterManager"`` annotation simplified
to bare ``self``.

The prep-form dispatch lambdas collapse to direct refs (pure prefix
transformation):
  ``lambda req: self.<method>(self.weight_updater, req)`` →
  ``self.weight_updater.<method>``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


METHOD_ORDER = [
    "flush_cache_after_weight_update",
    "update_weights_from_disk",
    "init_weights_update_group",
    "destroy_weights_update_group",
    "update_weights_from_distributed",
    "update_weights_from_tensor",
    "update_weights_from_ipc",
    "get_weights_by_name",
    "release_memory_occupation",
    "resume_memory_occupation",
    "check_weights",
    "save_remote_model",
    "save_sharded_model",
]

HELPER_FUNCTIONS = ["_export_static_state", "_import_static_state"]


# Final supporting module-level prelude relocated from the mixin file. The
# existing target header has only ``from __future__`` + ``Callable``; this
# block fills in everything else (logging / traceback / torch / constants /
# io_struct symbols / module logger).
TARGET_PRELUDE_NEW_IMPORTS = """\
import logging
import traceback
from typing import Tuple

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


"""


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_update_weights_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/weight_updater.py"

    # 1. Cut 13 @staticmethods bottom-up from the mixin.
    # NOTE: cut module-level helpers FIRST (while class body still has methods —
    # ast.parse otherwise rejects the empty class shell). Then cut methods.
    helper_blocks = []
    for name in reversed(HELPER_FUNCTIONS):
        s, e = find_function_lines(mixin.read_text(), function_name=name)
        helper_blocks.append(cut_lines(mixin, s, e))
    helper_blocks.reverse()

    method_blocks = []
    for name in reversed(METHOD_ORDER):
        s, e = find_method_lines(
            mixin.read_text(),
            class_name="SchedulerUpdateWeightsMixin",
            method_name=name,
        )
        block = cut_lines(mixin, s, e)
        block = block.replace("    @staticmethod\n", "", 1)
        block = block.replace('self: "SchedulerWeightUpdaterManager"', "self")
        method_blocks.append(block)
    method_blocks.reverse()

    # 3. Append methods into the SchedulerWeightUpdaterManager class body.
    target_text = target.read_text()
    target_text = target_text.rstrip() + "\n\n" + "".join(method_blocks).rstrip() + "\n"

    # 4. Splice the supporting module-level prelude into the target file.
    import re

    needed_typing = {"Any", "Callable", "Optional"}
    match = re.search(r"^from typing import [^\n]+\n", target_text, re.MULTILINE)
    if not match:
        raise RuntimeError("typing import line not found in target file")
    current_line = match.group(0)
    current_names = set(
        n.strip()
        for n in current_line.removeprefix("from typing import ").rstrip("\n").split(",")
    )
    merged_names = sorted(current_names | needed_typing)
    new_line = "from typing import " + ", ".join(merged_names) + "\n"
    target_text = target_text.replace(current_line, new_line, 1)
    target_text = target_text.replace(
        new_line,
        new_line + "\n" + TARGET_PRELUDE_NEW_IMPORTS,
        1,
    )

    # 5. Append the 2 module-level helpers after the class body.
    target_text = (
        target_text.rstrip() + "\n\n\n" + "".join(helper_blocks).rstrip() + "\n"
    )
    target.write_text(target_text)

    # 6. Delete the now-empty mixin file.
    mixin.unlink()

    # 7. Update Scheduler: drop mixin import + remove from inheritance list.
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

    # 8. Collapse the 10 prep-form lambdas to direct refs (pure prefix
    #    transformation). Robust to single-line and multi-line black
    #    formatting alike.
    text = re.sub(
        r"lambda req: self\.(\w+)\(\s*self\.weight_updater,\s*req\s*\)",
        r"self.weight_updater.\1",
        text,
    )

    # 9. ``save_remote_model`` / ``save_sharded_model`` are NOT dispatched via
    #    the lambda table; they ride the generic ``collective_rpc`` path
    #    which resolves the method via ``getattr(self_scheduler, name)``
    #    inside ``handle_rpc_request``. Now that the mixin is retired those
    #    two attributes are gone from Scheduler, so any
    #    ``Engine.save_remote_model(...)`` / ``Engine.save_sharded_model(...)``
    #    call would AttributeError at the dispatch point.
    #
    #    Re-expose them as thin Scheduler shims that forward to the
    #    weight_updater. The shim takes ``**kwargs`` (matching the way
    #    ``handle_rpc_request`` unpacks ``recv_req.parameters``) and re-packs
    #    into the single positional dict that the weight_updater methods
    #    expect.
    text = replace_call_site(
        text,
        old="        return RpcReqOutput(success, \"\" if not exec else str(exec))\n"
        "\n"
        "    def abort_request(self, recv_req: AbortReq):\n",
        new="        return RpcReqOutput(success, \"\" if not exec else str(exec))\n"
        "\n"
        "    def save_remote_model(self, **kwargs):\n"
        "        return self.weight_updater.save_remote_model(kwargs)\n"
        "\n"
        "    def save_sharded_model(self, **kwargs):\n"
        "        return self.weight_updater.save_sharded_model(kwargs)\n"
        "\n"
        "    def abort_request(self, recv_req: AbortReq):\n",
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
