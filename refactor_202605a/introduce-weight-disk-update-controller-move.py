#!/usr/bin/env python3
"""Move weight-disk-update methods to WeightDiskUpdateController."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines
from _runner import run_pr

ID = "introduce-weight-disk-update-controller-move"
SUBJECT = "Move weight-disk-update methods to WeightDiskUpdateController"
BODY = """\
Cut 4 methods from TokenizerManager + 1 from TokenizerControlMixin.
Paste into WeightDiskUpdateController. Add __post_init__ (registers
UpdateWeightFromDiskReqOutput on dispatcher). Body rewrites:
self.server_args.dp_size -> self.config.dp_size.

External entrypoint callers (engine.py, http_server.py) rewired through
``tokenizer_manager.weight_disk_update_controller``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import asyncio
import logging
from contextlib import nullcontext
from typing import Tuple, Union

import fastapi

from sglang.srt.managers.io_struct import (
    UpdateWeightFromDiskReqInput,
    UpdateWeightFromDiskReqOutput,
)

logger = logging.getLogger(__name__)
'''


POST_INIT = '''
    def __post_init__(self) -> None:
        if self.config.checkpoint_engine_wait_weights_before_ready:
            self.initial_weights_loaded = False
        # TypeBasedDispatcher has no public register(); poke private _mapping.
        self.dispatcher._mapping[UpdateWeightFromDiskReqOutput] = (
            self._handle_update_weights_from_disk_req_output
        )
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    wd = wt / "python/sglang/srt/managers/weight_disk_update_controller.py"

    # Cut bottom-up from facade.
    method_names = (
        "update_weights_from_disk",
        "_update_model_path_info",
        "_wait_for_model_update_from_disk",
        "_handle_update_weights_from_disk_req_output",
    )
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    # Cut _update_weight_version_if_provided from control_mixin.
    s, e = find_method_lines(
        control_mixin.read_text(),
        class_name="TokenizerControlMixin",
        method_name="_update_weight_version_if_provided",
    )
    update_version_text = cut_lines(control_mixin, s, e)
    update_version_text = update_version_text.replace(
        "def _update_weight_version_if_provided(\n        self: TokenizerManager, weight_version: Optional[str]\n    ) -> None:",
        "def _update_weight_version_if_provided(\n        self, weight_version: Optional[str]\n    ) -> None:",
    )

    def rewrite(body: str) -> str:
        body = body.replace("self.server_args.dp_size", "self.config.dp_size")
        body = body.replace("self.served_model_name = ", "self.server_args.served_model_name = ")
        body = body.replace("self.model_path = model_path", "self.server_args.model_path = model_path")
        return body

    rewritten = {n: rewrite(cut_blocks[n]) for n in method_names}
    bodies = [rewritten[n] for n in method_names]
    bodies.append(update_version_text)
    methods_text = POST_INIT + "\n" + "\n\n".join(b.rstrip() for b in bodies) + "\n"

    wd_text = wd.read_text()
    wd_text = wd_text.replace(
        "from dataclasses import dataclass, field\n",
        "from dataclasses import dataclass, field\n\n" + EXTRA_IMPORTS,
    )
    wd.write_text(wd_text.rstrip() + "\n" + methods_text)

    # External entrypoints.
    engine = wt / "python/sglang/srt/entrypoints/engine.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"

    text = engine.read_text()
    text = text.replace(
        "self.tokenizer_manager.update_weights_from_disk(",
        "self.tokenizer_manager.weight_disk_update_controller.update_weights_from_disk(",
    )
    engine.write_text(text)

    text = http_server.read_text()
    text = text.replace(
        "_global_state.tokenizer_manager.update_weights_from_disk(",
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
