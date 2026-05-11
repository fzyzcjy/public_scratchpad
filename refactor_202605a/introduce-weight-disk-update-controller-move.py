#!/usr/bin/env python3
"""Move (pure cut/paste): WeightDiskUpdateController methods relocate from TM + ControlMixin to target class."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, rewrite_intra_class_calls
from _runner import run_pr

ID = "introduce-weight-disk-update-controller-move"
SUBJECT = "Hand disk-based weight reload over to WeightDiskUpdateController"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut 4 @staticmethod methods
(``update_weights_from_disk``, ``_update_model_path_info``,
``_wait_for_model_update_from_disk``, ``_handle_update_weights_from_disk_req_output``)
from TokenizerManager and 1 @staticmethod method
(``_update_weight_version_if_provided``) from TokenizerControlMixin; paste
into WeightDiskUpdateController (drop @staticmethod, replace
``self: "WeightDiskUpdateController"`` → plain ``self``). Flip the
``__post_init__`` dispatcher entry from the lambda forwarder + late-TM-import
to a direct method reference. Caller prefix replacement:
``TokenizerManager.<method>(self.weight_disk_update_controller, ...)`` →
``self.weight_disk_update_controller.<method>(...)`` (TM + mixin sibling
methods + entrypoints); ditto for the
``TokenizerControlMixin._update_weight_version_if_provided`` call sites.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import asyncio
import logging
from contextlib import nullcontext
from typing import Tuple

import fastapi

from sglang.srt.managers.io_struct import UpdateWeightFromDiskReqInput

logger = logging.getLogger(__name__)
'''


_MOVED_METHODS = (
    "update_weights_from_disk",
    "_update_model_path_info",
    "_wait_for_model_update_from_disk",
    "handle_update_weights_from_disk_req_output",
    "_update_weight_version_if_provided",
)


def _strip_static_prefix(body: str) -> str:
    """Remove @staticmethod decorator, replace self: "WeightDiskUpdateController" → plain self,
    and flip intra-class qualifier on cross-method calls (prep rewrote them to
    ``TokenizerManager.<m>(self, ...)`` / ``TokenizerControlMixin.<m>(self, ...)``;
    after move both classes' methods live on WeightDiskUpdateController)."""
    body = body.replace("    @staticmethod\n", "", 1)
    body = body.replace('self: "WeightDiskUpdateController",', "self,")
    body = body.replace('self: "WeightDiskUpdateController"\n', "self\n")
    body = rewrite_intra_class_calls(
        body,
        source_classes=["TokenizerManager", "TokenizerControlMixin"],
        target_class="WeightDiskUpdateController",
        methods=list(_MOVED_METHODS),
    )
    return body


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    wd = wt / "python/sglang/srt/managers/weight_disk_update_controller.py"

    # Cut 4 methods from TM, bottom-up (highest start line first). The handler
    # method was privacy-flipped in prep.
    tm_methods = (
        "update_weights_from_disk",
        "_update_model_path_info",
        "_wait_for_model_update_from_disk",
        "handle_update_weights_from_disk_req_output",
    )
    name_to_range = {}
    for n in tm_methods:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = s
    cut_blocks_tm = {}
    for n in sorted(tm_methods, key=lambda nn: -name_to_range[nn]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks_tm[n] = cut_lines(tm, s, e)

    # Cut _update_weight_version_if_provided from TokenizerControlMixin.
    s, e = find_method_lines(
        control_mixin.read_text(),
        class_name="TokenizerControlMixin",
        method_name="_update_weight_version_if_provided",
    )
    cut_block_mixin = cut_lines(control_mixin, s, e)

    # Assemble in canonical order. Body bytes unchanged except @staticmethod stripped + self typing.
    bodies = [
        _strip_static_prefix(cut_blocks_tm["update_weights_from_disk"]),
        _strip_static_prefix(cut_blocks_tm["_update_model_path_info"]),
        _strip_static_prefix(cut_blocks_tm["_wait_for_model_update_from_disk"]),
        _strip_static_prefix(cut_blocks_tm["handle_update_weights_from_disk_req_output"]),
        _strip_static_prefix(cut_block_mixin),
    ]

    wd_text = wd.read_text()
    wd_text = wd_text.replace(
        "from dataclasses import dataclass, field\n",
        "from dataclasses import dataclass, field\n\n" + EXTRA_IMPORTS,
    )

    wd.write_text(wd_text.rstrip() + "\n\n" + "\n".join(b.rstrip() + "\n" for b in bodies))

    # Collapse the prep-stage lambda forwarder in TM's init_request_dispatcher
    # entry to a direct method ref on the controller.
    text = tm.read_text()
    text = text.replace(
        "                (\n"
        "                    UpdateWeightFromDiskReqOutput,\n"
        "                    lambda x: TokenizerManager.handle_update_weights_from_disk_req_output(\n"
        "                        self.weight_disk_update_controller, x\n"
        "                    ),\n"
        "                ),\n",
        "                (\n"
        "                    UpdateWeightFromDiskReqOutput,\n"
        "                    self.weight_disk_update_controller.handle_update_weights_from_disk_req_output,\n"
        "                ),\n",
    )
    tm.write_text(text)

    # ---- Caller prefix replacement: TM facade + sibling mixin callers ----
    # TokenizerManager.<method>(self.weight_disk_update_controller, ... ) →
    # self.weight_disk_update_controller.<method>(...).
    # The only remaining TM-internal call site is in update_weights_from_disk (now
    # cut), so TM has no residual class-qualified calls; mixin holds the 3 sibling
    # callers of _update_weight_version_if_provided.
    text = control_mixin.read_text()
    text = text.replace(
        "TokenizerControlMixin._update_weight_version_if_provided(self.weight_disk_update_controller, ",
        "self.weight_disk_update_controller._update_weight_version_if_provided(",
    )
    control_mixin.write_text(text)

    # ---- Caller prefix replacement in entrypoints ----
    engine = wt / "python/sglang/srt/entrypoints/engine.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"

    text = engine.read_text()
    text = text.replace(
        "TokenizerManager.update_weights_from_disk(self.tokenizer_manager.weight_disk_update_controller, ",
        "self.tokenizer_manager.weight_disk_update_controller.update_weights_from_disk(",
    )
    engine.write_text(text)

    text = http_server.read_text()
    text = text.replace(
        "TokenizerManager.update_weights_from_disk(_global_state.tokenizer_manager.weight_disk_update_controller, ",
        "_global_state.tokenizer_manager.weight_disk_update_controller.update_weights_from_disk(",
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
