#!/usr/bin/env python3
"""Introduce ResponseEmitter owner class.

Move 4 methods (_wait_one_response / create_abort_task /
_handle_abort_finish_reason / _coalesce_streaming_chunks) from
TokenizerManager into a new
@dataclass(slots=True, kw_only=True) ResponseEmitter in
managers/response_emitter.py.

_handle_batch_request stays on facade in this commit; its wait+yield
segment migration is the next commit (extract-handle-batch-request-wait-yield).

Re-wires score handler's wait_one_response Callable to point at the
emitter's _wait_one_response.
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

ID = "introduce-response-emitter"
SUBJECT = "Introduce ResponseEmitter and move client-side wait/abort methods"
BODY = """\
Move 4 methods from TokenizerManager into a new
@dataclass(slots=True, kw_only=True) ResponseEmitter in
managers/response_emitter.py:

  _wait_one_response, create_abort_task, _handle_abort_finish_reason,
  _coalesce_streaming_chunks

_handle_batch_request remains on facade in this commit; its wait+yield
segment migration is the next commit (extract-handle-batch-request-wait-yield).

Fields (direct injection, since all upstream classes already exist in chain):
  rid_to_state, pause_controller, lora_controller, request_log_manager,
  request_metrics_recorder, config (request_state_wait_timeout,
  incremental_streaming_output, enable_lora).

Score handler ctor binding re-wires from
``wait_one_response=self._wait_one_response`` to
``wait_one_response=self.response_emitter._wait_one_response``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Dict, Optional, Union

import fastapi
from fastapi import BackgroundTasks

from sglang.srt.environ import envs
from sglang.srt.managers import logprob_ops
from sglang.srt.managers.lora_controller import LoraController
from sglang.srt.managers.pause_controller import PauseController
from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput
from sglang.srt.managers.request_log_manager import RequestLogManager
from sglang.srt.managers.request_metrics_recorder import (
    RequestMetricsRecorder,
)
from sglang.srt.managers.request_state import ReqState

logger = logging.getLogger(__name__)

_REQUEST_STATE_WAIT_TIMEOUT = envs.SGLANG_REQUEST_STATE_WAIT_TIMEOUT.get()


@dataclass(slots=True, kw_only=True)
class ResponseEmitterConfig:
    incremental_streaming_output: bool
    enable_lora: bool


@dataclass(slots=True, kw_only=True)
class ResponseEmitter:
    """Drains rid_to_state[rid].out_list and yields per-request dicts to HTTP clients."""

    rid_to_state: Dict[str, ReqState]
    pause_controller: PauseController
    lora_controller: LoraController
    request_log_manager: RequestLogManager
    request_metrics_recorder: RequestMetricsRecorder
    config: ResponseEmitterConfig

'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/response_emitter.py"

    method_names = (
        "_wait_one_response",
        "create_abort_task",
        "_handle_abort_finish_reason",
        "_coalesce_streaming_chunks",
    )
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    def rewrite(body: str) -> str:
        body = body.replace(
            "self.server_args.incremental_streaming_output",
            "self.config.incremental_streaming_output",
        )
        body = body.replace(
            "self.server_args.enable_lora",
            "self.config.enable_lora",
        )
        return body

    bodies = [rewrite(cut_blocks[n]) for n in method_names]
    new.write_text(HEADER + "\n\n".join(b.rstrip() for b in bodies) + "\n")

    # ===== Update facade =====
    text = tm.read_text()

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.response_emitter import (\n"
            "    ResponseEmitter,\n"
            "    ResponseEmitterConfig,\n"
            ")\n"
        ),
    )

    # Wire construction (after output_processor).
    text = replace_call_site(
        text,
        old=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
        new=(
            "        # Response emitter\n"
            "        self.response_emitter = ResponseEmitter(\n"
            "            rid_to_state=self.rid_to_state,\n"
            "            pause_controller=self.pause_controller,\n"
            "            lora_controller=self.lora_controller,\n"
            "            request_log_manager=self.request_log_manager,\n"
            "            request_metrics_recorder=self.request_metrics_recorder,\n"
            "            config=ResponseEmitterConfig(\n"
            "                incremental_streaming_output=self.server_args.incremental_streaming_output,\n"
            "                enable_lora=self.server_args.enable_lora,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
    )

    # Caller updates inside facade.
    text = text.replace(
        "self._wait_one_response(",
        "self.response_emitter._wait_one_response(",
    )
    text = text.replace(
        "self._handle_abort_finish_reason(",
        "self.response_emitter._handle_abort_finish_reason(",
    )
    text = text.replace(
        "self._coalesce_streaming_chunks(",
        "self.response_emitter._coalesce_streaming_chunks(",
    )
    # create_abort_task: facade callers
    text = text.replace(
        "self.create_abort_task(",
        "self.response_emitter.create_abort_task(",
    )

    # NOTE: ScoreRequestHandler in this chain uses ``generate_request`` Callable
    # (see introduce-score-request-handler.py docstring) rather than the
    # 3-Callable form (create_tokenized_object / send_one_request /
    # wait_one_response). So no score-handler re-wire is needed here -- the
    # generate_request binding remains valid.

    tm.write_text(text)

    # External entrypoint callers of tokenizer_manager.create_abort_task ->
    # tokenizer_manager.response_emitter.create_abort_task.
    import glob
    import re as _re
    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        t = f.read_text()
        t = _re.sub(
            r"\btokenizer_manager\.create_abort_task\(",
            "tokenizer_manager.response_emitter.create_abort_task(",
            t,
        )
        f.write_text(t)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
