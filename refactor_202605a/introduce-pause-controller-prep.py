#!/usr/bin/env python3
"""Prep step for introducing PauseController.

Creates managers/pause_controller.py with empty class skeleton (dataclasses
only, no methods) and adds composition wiring to TokenizerManager.__init__.
Methods stay on TokenizerManager in this commit; subsequent commit
``introduce-pause-controller-move`` cuts them over.

Drops is_pause / is_pause_cond field initialization from TM (the fields now
live on PauseController; intermediate state has these missing on TM but
that's accepted per MECH_COMMIT_SPLIT — runtime correctness is only
required at chain HEAD).
"""

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

ID = "introduce-pause-controller-prep"
SUBJECT = "Prep PauseController: empty skeleton + composition wiring"
BODY = """\
Per MECH_COMMIT_SPLIT: split bundled introduce-pause-controller into prep + move.
Prep creates the empty class skeleton (dataclasses with fields only) and
adds composition wiring to TM.__init__. Methods + __post_init__ +
caller rewrites land in the next commit.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from sglang.srt.managers.request_state import ReqState
from sglang.srt.utils.aio_rwlock import RWLock
from sglang.utils import TypeBasedDispatcher


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
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/pause_controller.py"

    new.write_text(SKELETON)

    text = tm.read_text()
    text = replace_call_site(
        text,
        old=(
            "        self.is_pause = False\n"
            "        self.is_pause_cond = asyncio.Condition()\n"
        ),
        new="",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.pause_controller import (\n"
            "    PauseController,\n"
            "    PauseControllerConfig,\n"
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
