#!/usr/bin/env python3
"""Introduce WeightDiskUpdateController owner class."""

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
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "introduce-weight-disk-update-controller"
SUBJECT = "Introduce WeightDiskUpdateController and move disk weight update methods"
BODY = """\
Move 4 TokenizerManager methods (update_weights_from_disk,
_update_model_path_info, _wait_for_model_update_from_disk,
_handle_update_weights_from_disk_req_output) plus
_update_weight_version_if_provided from TokenizerControlMixin into a new
@dataclass(slots=True, kw_only=True) WeightDiskUpdateController in
managers/weight_disk_update_controller.py.

Fields:
  send_to_scheduler / dispatcher (registers UpdateWeightFromDiskReqOutput)
  pause_controller (for pause-aware lock + abort_request)
  model_update_lock
  server_args (R4 transitional -- _update_model_path_info / _update_weight_version_if_provided
    write back model_path / load_format / weight_version on it)
  served_model_name_holder: list[str] (transitional one-cell list to mutate
    served_model_name from outside facade -- avoids R4 violation by NOT
    holding facade ref; consumer reads holder[0]).

Actually: PR1 keeps it simple by holding a Callable on_path_updated so
facade does the writes. md ch3.1 specifies this transitional pattern.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import asyncio
import logging
from contextlib import nullcontext
from dataclasses import dataclass, field
from typing import Any, Awaitable, List, Optional, Tuple, Union

import fastapi

from typing import Callable

from sglang.srt.managers.pause_controller import PauseController
from sglang.srt.managers.io_struct import (
    UpdateWeightFromDiskReqInput,
    UpdateWeightFromDiskReqOutput,
)
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils.aio_rwlock import RWLock
from sglang.utils import TypeBasedDispatcher

logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True)
class WeightDiskUpdateControllerConfig:
    dp_size: int
    initial_load_format: str
    checkpoint_engine_wait_weights_before_ready: bool


@dataclass(slots=True, kw_only=True)
class WeightDiskUpdateController:
    """update_weights_from_disk endpoint + UpdateWeightFromDiskReqOutput dispatcher handler."""

    send_to_scheduler: Any
    dispatcher: TypeBasedDispatcher
    pause_controller: PauseController
    model_update_lock: RWLock
    server_args: ServerArgs  # R4 transitional: directly mutates model_path/load_format/weight_version
    auto_create_handle_loop: Callable[[], None]
    config: WeightDiskUpdateControllerConfig
    initial_weights_loaded: bool = True
    model_update_result: Optional[Awaitable[UpdateWeightFromDiskReqOutput]] = None
    model_update_tmp: List[Any] = field(default_factory=list)

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
    new = wt / "python/sglang/srt/managers/weight_disk_update_controller.py"

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
    # Strip the type-hint hack ``self: TokenizerManager`` -> ``self``.
    update_version_text = update_version_text.replace(
        "def _update_weight_version_if_provided(\n        self: TokenizerManager, weight_version: Optional[str]\n    ) -> None:",
        "def _update_weight_version_if_provided(\n        self, weight_version: Optional[str]\n    ) -> None:",
    )

    # Apply self.X rewrites in moved bodies.
    def rewrite(body: str) -> str:
        body = body.replace("self.server_args.dp_size", "self.config.dp_size")
        body = body.replace("self.served_model_name = ", "self.server_args.served_model_name = ")
        body = body.replace("self.model_path = model_path", "self.server_args.model_path = model_path")
        # auto_create_handle_loop kept as Callable injection (no deletion -- Ch1 forbids).
        return body

    rewritten = {n: rewrite(cut_blocks[n]) for n in method_names}

    # Compose new file in original method order.
    bodies = [rewritten[n] for n in method_names]
    bodies.append(update_version_text)
    new.write_text(HEADER + "\n\n".join(b.rstrip() for b in bodies) + "\n")

    # ===== Drop the weight-update fields from init_weight_update =====
    text = tm.read_text()
    text = replace_call_site(
        text,
        old=(
            "    def init_weight_update(self):\n"
            "        # Initial weights status\n"
            "        self.initial_weights_loaded = True\n"
            "        if self.server_args.checkpoint_engine_wait_weights_before_ready:\n"
            "            self.initial_weights_loaded = False\n"
            "\n"
            "        # Weight updates\n"
            "        # The event to notify the weight sync is finished.\n"
            "        self.model_update_lock = RWLock()\n"
            "        self.model_update_result: Optional[Awaitable[UpdateWeightFromDiskReqOutput]] = (\n"
            "            None\n"
            "        )\n"
        ),
        new=(
            "    def init_weight_update(self):\n"
            "        # The event to notify the weight sync is finished.\n"
            "        self.model_update_lock = RWLock()\n"
        ),
    )

    # ===== Add import =====
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.weight_disk_update_controller import (\n"
            "    WeightDiskUpdateController,\n"
            "    WeightDiskUpdateControllerConfig,\n"
            ")\n"
        ),
    )

    # ===== Wire construction (after pause_controller) =====
    text = replace_call_site(
        text,
        old=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
        new=(
            "        # Weight disk update controller\n"
            "        self.weight_disk_update_controller = WeightDiskUpdateController(\n"
            "            send_to_scheduler=self.send_to_scheduler,\n"
            "            dispatcher=self._result_dispatcher,\n"
            "            pause_controller=self.pause_controller,\n"
            "            model_update_lock=self.model_update_lock,\n"
            "            server_args=self.server_args,\n"
            "            auto_create_handle_loop=self.auto_create_handle_loop,\n"
            "            config=WeightDiskUpdateControllerConfig(\n"
            "                dp_size=self.server_args.dp_size,\n"
            "                initial_load_format=self.server_args.load_format,\n"
            "                checkpoint_engine_wait_weights_before_ready=self.server_args.checkpoint_engine_wait_weights_before_ready,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
    )

    tm.write_text(text)

    # ===== entrypoint callers =====
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
