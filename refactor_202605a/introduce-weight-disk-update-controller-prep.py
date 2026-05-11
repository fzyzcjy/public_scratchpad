#!/usr/bin/env python3
"""Prep: empty WeightDiskUpdateController skeleton + composition wiring."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-weight-disk-update-controller-prep"
SUBJECT = "Prep WeightDiskUpdateController: empty skeleton + composition wiring"
BODY = """\
Per MECH_COMMIT_SPLIT: skeleton + composition wiring only. Methods +
__post_init__ + caller rewrites land in the next commit.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, List, Optional

from sglang.srt.managers.pause_controller import PauseController
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils.aio_rwlock import RWLock
from sglang.utils import TypeBasedDispatcher


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
    server_args: ServerArgs
    auto_create_handle_loop: Callable[[], None]
    config: WeightDiskUpdateControllerConfig
    initial_weights_loaded: bool = True
    model_update_result: Optional[Awaitable[Any]] = None
    model_update_tmp: List[Any] = field(default_factory=list)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/weight_disk_update_controller.py"
    new.write_text(SKELETON)

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


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
