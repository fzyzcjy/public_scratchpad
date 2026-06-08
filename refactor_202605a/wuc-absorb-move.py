#!/usr/bin/env python3
"""Move (pure cut/paste): fold the remaining weight ops into WeightUpdaterController."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import re as _re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, rewrite_intra_class_calls
from _runner import run_pr

ID = "wuc-absorb-move"
SUBJECT = "Hand the remaining weight ops over to WeightUpdaterController"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut the @staticmethod weight methods
(``init_weights_update_group`` / ``destroy_weights_update_group`` /
``update_weights_from_distributed`` / ``update_weights_from_tensor`` /
``update_weights_from_ipc`` / ``get_weights_by_name`` /
``release_memory_occupation`` / ``resume_memory_occupation`` /
``check_weights``) from TokenizerControlMixin and paste into
WeightUpdaterController (drop @staticmethod, replace
``self: "WeightUpdaterController"`` -> plain ``self``, fold the class-qualified
version-bump call back to the sibling ``self._update_weight_version_if_provided``).
Add the imports the moved bodies need. Caller prefix replacement:
``TokenizerManager.<method>(<facade>.weight_updater_controller, ...)`` ->
``<facade>.weight_updater_controller.<method>(...)`` in engine.py and
http_server.py.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_METHODS = (
    "init_weights_update_group",
    "destroy_weights_update_group",
    "update_weights_from_distributed",
    "update_weights_from_tensor",
    "update_weights_from_ipc",
    "get_weights_by_name",
    "release_memory_occupation",
    "resume_memory_occupation",
    "check_weights",
)

EXTRA_IMPORTS = '''import hashlib

from sglang.srt.managers.communicator import FanOutCommunicator
from sglang.srt.managers.io_struct import (
    CheckWeightsReqInput,
    DestroyWeightsUpdateGroupReqInput,
    GetWeightsByNameReqInput,
    InitWeightsUpdateGroupReqInput,
    ReleaseMemoryOccupationReqInput,
    ResumeMemoryOccupationReqInput,
    UpdateWeightFromDiskReqInput,
    UpdateWeightsFromDistributedReqInput,
    UpdateWeightsFromIPCReqInput,
    UpdateWeightsFromTensorReqInput,
)
'''


def _strip_static_prefix(body: str) -> str:
    """Remove @staticmethod, restore plain self, fold the class-qualified
    version-bump call back to the sibling form."""
    body = body.replace("    @staticmethod\n", "", 1)
    body = body.replace('self: "WeightUpdaterController",', "self,")
    body = rewrite_intra_class_calls(
        body,
        source_classes=["WeightUpdaterController"],
        target_class="WeightUpdaterController",
        methods=["_update_weight_version_if_provided"],
    )
    return body


def transform(wt: Path) -> None:
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    controller = (
        wt
        / "python/sglang/srt/managers/tokenizer_manager_components/weight_updater_controller.py"
    )

    # Cut the 9 methods from the mixin, bottom-up (highest start line first).
    name_to_start = {}
    for n in _METHODS:
        s, e = find_method_lines(
            control_mixin.read_text(), class_name="TokenizerControlMixin", method_name=n
        )
        name_to_start[n] = s
    cut_blocks = {}
    for n in sorted(_METHODS, key=lambda nn: -name_to_start[nn]):
        s, e = find_method_lines(
            control_mixin.read_text(), class_name="TokenizerControlMixin", method_name=n
        )
        cut_blocks[n] = cut_lines(control_mixin, s, e)

    bodies = [_strip_static_prefix(cut_blocks[n]) for n in _METHODS]

    # Paste into the controller, adding the imports the moved bodies need.
    ctrl_text = controller.read_text()
    ctrl_text = ctrl_text.replace(
        "from sglang.srt.managers.io_struct import UpdateWeightFromDiskReqInput\n",
        EXTRA_IMPORTS,
    )
    ctrl_text = ctrl_text.replace("from typing import Tuple\n", "from typing import Dict, Tuple\n", 1)
    controller.write_text(
        ctrl_text.rstrip() + "\n\n" + "\n".join(b.rstrip() + "\n" for b in bodies)
    )

    # ---- Caller prefix replacement in entrypoints (regex absorbs the
    # single-line and the black-wrapped multi-line forms). ----
    engine = wt / "python/sglang/srt/entrypoints/engine.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"

    text = engine.read_text()
    for m in _METHODS:
        text = _re.sub(
            rf"TokenizerManager\.{m}\(\s*self\.tokenizer_manager\.weight_updater_controller,\s*",
            f"self.tokenizer_manager.weight_updater_controller.{m}(",
            text,
        )
    engine.write_text(text)

    text = http_server.read_text()
    for m in _METHODS:
        text = _re.sub(
            rf"TokenizerManager\.{m}\(\s*_global_state\.tokenizer_manager\.weight_updater_controller,\s*",
            f"_global_state.tokenizer_manager.weight_updater_controller.{m}(",
            text,
        )
    http_server.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
