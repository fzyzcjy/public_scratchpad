#!/usr/bin/env python3
"""Introduce SessionController owner class.

Move open_session / close_session (from TokenizerControlMixin) plus
_handle_open_session_req_output (from TokenizerManager) into a new
@dataclass(slots=True, kw_only=True) SessionController.

Also reshapes init_request_dispatcher: dispatcher creation moves earlier
in __init__ (so SessionController.__post_init__ can register
OpenSessionReqOutput on it). Remaining body of init_request_dispatcher
(communicators + class-vars) keeps its place. The
(OpenSessionReqOutput, ...) entry is dropped from the early-created
dispatcher entry list because SessionController registers it itself.

session_futures dict moves from facade to SessionController.
"""

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

ID = "introduce-session-controller"
SUBJECT = "Introduce SessionController and split init_request_dispatcher"
BODY = """\
Move three methods (open_session, close_session, _handle_open_session_req_output)
into a new @dataclass(slots=True, kw_only=True) SessionController in
managers/control/session_controller.py. session_futures dict moves with
them.

Reshapes facade __init__: a new self._result_dispatcher = TypeBasedDispatcher([...])
block is added BEFORE owner-class construction (with FreezeGCReq /
HealthCheckOutput / ActiveRanksOutput entries; AbortReq /
OpenSessionReqOutput / UpdateWeightFromDiskReqOutput entries are dropped
because their handlers will register via __post_init__ in
PauseController / SessionController / WeightDiskUpdateController).
init_request_dispatcher now contains only init_communicators +
sampling_params_class + signal_handler_class assignments (no dispatcher
creation, no entry list).

This is ctor wiring reorganization (allowed by EXECUTION_GUIDE), not
control-flow rearrangement.

Caller updates:
  TokenizerManager: drop session_futures = {} from init_running_status.
  http_server.py / engine.py: tokenizer_manager.{open,close}_session
    -> tokenizer_manager.session_controller.{open_session,close_session}.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import fastapi

from sglang.srt.managers.io_struct import (
    CloseSessionReqInput,
    OpenSessionReqInput,
    OpenSessionReqOutput,
)
from sglang.utils import TypeBasedDispatcher

logger = logging.getLogger(__name__)


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

    def __post_init__(self) -> None:
        self.dispatcher.register(
            OpenSessionReqOutput, self._handle_open_session_req_output
        )

    async def open_session(
        self,
        obj: OpenSessionReqInput,
        request: Optional[fastapi.Request] = None,
    ):
        if obj.streaming:
            if not self.config.enable_streaming_session:
                raise ValueError(
                    "Streaming sessions are disabled. "
                    "Please relaunch with --enable-streaming-session."
                )

        if obj.session_id is None:
            obj.session_id = uuid.uuid4().hex
        elif obj.session_id in self.session_futures:
            return None

        future = asyncio.Future()
        self.session_futures[obj.session_id] = future
        self.send_to_scheduler.send_pyobj(obj)

        try:
            return await future
        finally:
            self.session_futures.pop(obj.session_id, None)

    async def close_session(
        self,
        obj: CloseSessionReqInput,
        request: Optional[fastapi.Request] = None,
    ):
        await self.send_to_scheduler.send_pyobj(obj)

    def _handle_open_session_req_output(self, recv_obj):
        future = self.session_futures.get(recv_obj.session_id)
        if future is not None:
            future.set_result(recv_obj.session_id if recv_obj.success else None)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    control_dir = wt / "python/sglang/srt/managers/control"
    control_dir.mkdir(exist_ok=True)
    (control_dir / "__init__.py").write_text("")
    new = control_dir / "session_controller.py"

    # Cut _handle_open_session_req_output from facade.
    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="_handle_open_session_req_output",
    )
    cut_lines(tm, s, e)

    # Cut open_session and close_session from TokenizerControlMixin (bottom-up).
    s, e = find_method_lines(
        control_mixin.read_text(),
        class_name="TokenizerControlMixin",
        method_name="close_session",
    )
    cut_lines(control_mixin, s, e)
    s, e = find_method_lines(
        control_mixin.read_text(),
        class_name="TokenizerControlMixin",
        method_name="open_session",
    )
    cut_lines(control_mixin, s, e)

    new.write_text(HEADER)

    # ===== Update tokenizer_manager.py: dispatcher restructure + ctor wiring + session_futures =====
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

    # Reshape init_request_dispatcher: drop the dispatcher creation block.
    # The new minimal body contains only init_communicators + sampling_params + signal_handler.
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
            "        self.init_communicators(self.server_args)\n"
            "\n"
            "        self.sampling_params_class = SamplingParams\n"
            "        self.signal_handler_class = SignalHandler\n"
        ),
    )

    # Insert dispatcher creation early -- right after init_metric_collector_watchdog().
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
        ),
    )

    # Add SessionController construction (last block before init_request_dispatcher).
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.control.session_controller import (\n"
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

    # ===== Update entrypoint callers =====
    engine = wt / "python/sglang/srt/entrypoints/engine.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"

    text = engine.read_text()
    text = text.replace(
        "self.tokenizer_manager.open_session(",
        "self.tokenizer_manager.session_controller.open_session(",
    )
    text = text.replace(
        "self.tokenizer_manager.close_session(",
        "self.tokenizer_manager.session_controller.close_session(",
    )
    engine.write_text(text)

    text = http_server.read_text()
    text = text.replace(
        "_global_state.tokenizer_manager.open_session(",
        "_global_state.tokenizer_manager.session_controller.open_session(",
    )
    text = text.replace(
        "_global_state.tokenizer_manager.close_session(",
        "_global_state.tokenizer_manager.session_controller.close_session(",
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
