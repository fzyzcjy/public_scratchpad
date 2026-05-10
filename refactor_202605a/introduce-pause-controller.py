#!/usr/bin/env python3
"""Introduce PauseController owner class.

Move 4 methods (pause_generation / continue_generation / abort_request /
_handle_abort_req) plus 2 fields (is_pause, is_pause_cond) from
TokenizerManager into a new managers/control/pause_controller.py module.

PauseController.__post_init__ registers AbortReq on the dispatcher
(created early in #15).

Caller updates for residual references in tokenizer_manager.py /
tokenizer_control_mixin.py / multi_tokenizer_mixin.py:
  self.is_pause       -> self.pause_controller.is_pause
  self.is_pause_cond  -> self.pause_controller.is_pause_cond
  self.abort_request  -> self.pause_controller.abort_request
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
from _helpers import (
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "introduce-pause-controller"
SUBJECT = "Introduce PauseController and move pause/abort methods"
BODY = """\
Move 4 methods (pause_generation, continue_generation, abort_request,
_handle_abort_req) from TokenizerManager into a new
@dataclass(slots=True, kw_only=True) PauseController in
managers/control/pause_controller.py. is_pause / is_pause_cond fields
move along with them.

frozen=False because is_pause mutates. __post_init__ registers AbortReq
on self.dispatcher.

External references to self.is_pause / self.is_pause_cond /
self.abort_request rewrite to self.pause_controller.<X> in:
  - tokenizer_manager.py (residual call sites in generate_request etc.)
  - tokenizer_control_mixin.py (3 sites in update-related methods)
  - multi_tokenizer_mixin.py (5 sites in TokenizerWorker pause/continue
    overrides that stay as Ch2 deliverables)

Per md ch3.1 PR1 form: method/field names retained; subclass extension
point + is_paused property + wait_until_resumed + pause/continue rename
are deferred to Ch2.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from sglang.srt.managers import logprob_ops
from sglang.srt.managers.io_struct import (
    AbortReq,
    ContinueGenerationReqInput,
    PauseGenerationReqInput,
)
from sglang.srt.managers.request_state import ReqState
from sglang.srt.utils.aio_rwlock import RWLock
from sglang.utils import TypeBasedDispatcher

logger = logging.getLogger(__name__)


@dataclass(slots=True, kw_only=True)
class PauseControllerConfig:
    enable_metrics: bool
    skip_tokenizer_init: bool
    weight_version: Optional[str]


@dataclass(slots=True, kw_only=True)
class PauseController:
    """Pause / resume / abort state machine + AbortReq dispatcher handler."""

    send_to_scheduler: Any
    dispatcher: TypeBasedDispatcher
    rid_to_state: Dict[str, ReqState]
    model_update_lock: RWLock
    metrics_collector: Optional[Any]
    tokenizer: Optional[Any]
    config: PauseControllerConfig
    is_pause: bool = False
    is_pause_cond: asyncio.Condition = field(default_factory=asyncio.Condition)

    def __post_init__(self) -> None:
        self.dispatcher.register(AbortReq, self._handle_abort_req)

'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    multi_mixin = wt / "python/sglang/srt/managers/multi_tokenizer_mixin.py"
    new = wt / "python/sglang/srt/managers/control/pause_controller.py"

    # Cut bottom-up.
    method_names = (
        "pause_generation",
        "continue_generation",
        "abort_request",
        "_handle_abort_req",
    )
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    # Compose new file (keep original method order: pause -> continue -> abort -> _handle_abort_req).
    bodies = [cut_blocks[n] for n in method_names]
    new.write_text(HEADER + "\n\n".join(b.rstrip() for b in bodies) + "\n")

    # ===== Drop is_pause/is_pause_cond fields from init_running_status =====
    text = tm.read_text()
    text = replace_call_site(
        text,
        old=(
            "        self.is_pause = False\n"
            "        self.is_pause_cond = asyncio.Condition()\n"
        ),
        new="",
    )

    # ===== Add import =====
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.control.pause_controller import (\n"
            "    PauseController,\n"
            "    PauseControllerConfig,\n"
            ")\n"
        ),
    )

    # ===== Wire construction =====
    text = replace_call_site(
        text,
        old=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
        new=(
            "        # Pause controller\n"
            "        self.pause_controller = PauseController(\n"
            "            send_to_scheduler=self.send_to_scheduler,\n"
            "            dispatcher=self._result_dispatcher,\n"
            "            rid_to_state=self.rid_to_state,\n"
            "            model_update_lock=self.model_update_lock,\n"
            "            metrics_collector=self.request_metrics_recorder.metrics_collector,\n"
            "            tokenizer=self.raw_tokenizer_wrapper.tokenizer,\n"
            "            config=PauseControllerConfig(\n"
            "                enable_metrics=self.enable_metrics,\n"
            "                skip_tokenizer_init=self.server_args.skip_tokenizer_init,\n"
            "                weight_version=self.server_args.weight_version,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
    )

    # ===== Caller substitutions =====
    def rewire(text: str) -> str:
        text = re.sub(r"\bself\.is_pause_cond\b", "self.pause_controller.is_pause_cond", text)
        text = re.sub(r"\bself\.is_pause\b", "self.pause_controller.is_pause", text)
        text = re.sub(r"\bself\.abort_request\(", "self.pause_controller.abort_request(", text)
        return text

    text = rewire(text)
    tm.write_text(text)

    text = control_mixin.read_text()
    text = rewire(text)
    control_mixin.write_text(text)

    text = multi_mixin.read_text()
    text = rewire(text)
    multi_mixin.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
