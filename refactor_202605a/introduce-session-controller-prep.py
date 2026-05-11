#!/usr/bin/env python3
"""Prep: SessionController skeleton + composition wiring + init_request_dispatcher restructure.

The dispatcher restructure must happen in prep so subsequent owner-class ctors
(PauseController / WeightDiskUpdateController / LoraController / CorpusController)
can find self._result_dispatcher and self.init_communicators() already done.
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

ID = "introduce-session-controller-prep"
SUBJECT = "Prep SessionController: skeleton + composition + init_request_dispatcher restructure"
BODY = "Per MECH_COMMIT_SPLIT: skeleton + composition + restructure. Methods + __post_init__ + callers in next commit."
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict

from sglang.utils import TypeBasedDispatcher


@dataclass(slots=True, kw_only=True)
class SessionControllerConfig:
    enable_streaming_session: bool


@dataclass(slots=True, kw_only=True)
class SessionController:
    """open_session / close_session endpoints + OpenSessionReqOutput dispatcher handler."""

    send_to_scheduler: Any
    dispatcher: TypeBasedDispatcher
    config: SessionControllerConfig
    session_futures: Dict[str, asyncio.Future] = field(default_factory=dict)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/session_controller.py"
    new.write_text(SKELETON)

    text = tm.read_text()

    # Drop session_futures = {} from init_running_status.
    text = replace_call_site(
        text,
        old=(
            "        # Session\n"
            "        self.session_futures = {}  # session_id -> asyncio event\n"
            "\n"
        ),
        new="",
    )

    # Restructure init_request_dispatcher: pull dispatcher creation + init_communicators earlier.
    text = replace_call_site(
        text,
        old=(
            "    def init_request_dispatcher(self):\n"
            "        self._result_dispatcher = TypeBasedDispatcher(\n"
            "            [\n"
            "                (AbortReq, self._handle_abort_req),\n"
            "                (OpenSessionReqOutput, self._handle_open_session_req_output),\n"
            "                (\n"
            "                    UpdateWeightFromDiskReqOutput,\n"
            "                    self._handle_update_weights_from_disk_req_output,\n"
            "                ),\n"
            "                (FreezeGCReq, lambda x: None),\n"
            "                # For handling case when scheduler skips detokenizer and forwards back to the tokenizer manager, we ignore it.\n"
            "                (HealthCheckOutput, lambda x: None),\n"
            "                (ActiveRanksOutput, self.update_active_ranks),\n"
            "            ]\n"
            "        )\n"
            "        self.init_communicators(self.server_args)\n"
            "\n"
            "        self.sampling_params_class = SamplingParams\n"
            "        self.signal_handler_class = SignalHandler\n"
        ),
        new=(
            "    def init_request_dispatcher(self):\n"
            "        self.sampling_params_class = SamplingParams\n"
            "        self.signal_handler_class = SignalHandler\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        self.init_metric_collector_watchdog()\n",
        new=(
            "        self.init_metric_collector_watchdog()\n"
            "\n"
            "        # Result dispatcher (created early so controllers can register handlers in __post_init__)\n"
            "        self._result_dispatcher = TypeBasedDispatcher(\n"
            "            [\n"
            "                (FreezeGCReq, lambda x: None),\n"
            "                (HealthCheckOutput, lambda x: None),\n"
            "                (ActiveRanksOutput, self.update_active_ranks),\n"
            "            ]\n"
            "        )\n"
            "\n"
            "        # Communicators (RPC fan-out) -- needed by owner-class ctors below.\n"
            "        self.init_communicators(self.server_args)\n"
        ),
    )

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.session_controller import (\n"
            "    SessionController,\n"
            "    SessionControllerConfig,\n"
            ")\n"
        ),
    )

    text = replace_call_site(
        text,
        old="        # Init request dispatcher\n        self.init_request_dispatcher()",
        new=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
            "            send_to_scheduler=self.send_to_scheduler,\n"
            "            dispatcher=self._result_dispatcher,\n"
            "            config=SessionControllerConfig(\n"
            "                enable_streaming_session=self.server_args.enable_streaming_session,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Init request dispatcher\n"
            "        self.init_request_dispatcher()"
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
