#!/usr/bin/env python3
"""Prep: SessionController skeleton + composition wiring + init_request_dispatcher
restructure + 3 methods to @staticmethod with self: "SessionController" typing +
body rewrites + __post_init__ lambda forwarder + entrypoint caller rewrites.

Per MECH_COMMIT_SPLIT §"拆 class 场景": ALL semantic work happens here. The
follow-up -move commit is pure cut/paste + caller prefix replacement +
lambda→direct flip in __post_init__.

The dispatcher restructure must happen in prep so subsequent owner-class ctors
(PauseController / WeightDiskUpdateController / LoraController / CorpusController)
can find self._result_dispatcher and self.init_communicators() already done.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import ast
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-session-controller-prep"
SUBJECT = "Prep SessionController: skeleton + composition + staticmethod conversion + caller rewrites"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds SessionController skeleton; restructures init_request_dispatcher
(early dispatcher creation + init_communicators, needed before owner-class
ctors); wires composition in TokenizerManager.__init__; converts
open_session + close_session (TokenizerControlMixin) and
_handle_open_session_req_output (TokenizerManager) to @staticmethod with
self: "SessionController" typing; applies body rewrites
(self.server_args.enable_streaming_session →
self.config.enable_streaming_session); registers OpenSessionReqOutput on
the dispatcher in __post_init__ via lambda forwarder to TM's staticmethod;
drops session_futures from init_running_status; rewrites entrypoint
callers (engine.py, http_server.py) to TokenizerManager.<method>(
self.tokenizer_manager.session_controller, ...) form. Methods stay on
their source classes in this commit; the next commit's pure cut/paste +
caller prefix replacement + lambda→direct flip completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict

from sglang.srt.managers.io_struct import OpenSessionReqOutput
from sglang.utils import TypeBasedDispatcher


@dataclass(slots=True, kw_only=True)
class SessionControllerConfig:
    enable_streaming_session: bool


@dataclass(slots=True, kw_only=True)
class SessionController:
    """open_session / close_session endpoints + OpenSessionReqOutput dispatcher handler."""

    send_to_scheduler: Any
    dispatcher: TypeBasedDispatcher
    auto_create_handle_loop: Callable[[], None]
    config: SessionControllerConfig
    session_futures: Dict[str, asyncio.Future] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Lambda forwarder: during prep the handler still lives on TokenizerManager
        # as a @staticmethod with ``self: "SessionController"`` typing. The
        # follow-up -move commit cuts the method into this class and flips this
        # registration to a direct method reference.
        from sglang.srt.managers.tokenizer_manager import TokenizerManager

        self.dispatcher._mapping[OpenSessionReqOutput] = (
            lambda recv_obj: TokenizerManager._handle_open_session_req_output(
                self, recv_obj
            )
        )
'''


def _method_ranges(text: str, class_name: str, method_name: str):
    tree = ast.parse(text)
    func_types = (ast.FunctionDef, ast.AsyncFunctionDef)
    for cls in ast.walk(tree):
        if isinstance(cls, ast.ClassDef) and cls.name == class_name:
            for i, node in enumerate(cls.body):
                if isinstance(node, func_types) and node.name == method_name:
                    start = node.lineno - 1
                    if node.decorator_list:
                        start = node.decorator_list[0].lineno - 1
                    body_start = node.body[0].lineno - 1
                    if i + 1 < len(cls.body):
                        end = cls.body[i + 1].lineno - 1
                        nxt = cls.body[i + 1]
                        if isinstance(nxt, func_types + (ast.ClassDef,)) and nxt.decorator_list:
                            end = nxt.decorator_list[0].lineno - 1
                    else:
                        end = node.end_lineno
                    return start, body_start, end
    raise ValueError(f"{class_name}.{method_name} not found")


# New headers: @staticmethod + self: "SessionController" typing. async preserved
# for the two coroutines.
NEW_OPEN_HEADER = '''    @staticmethod
    async def open_session(
        self: "SessionController",
        obj: OpenSessionReqInput,
        request: Optional[fastapi.Request] = None,
    ):
'''

NEW_CLOSE_HEADER = '''    @staticmethod
    async def close_session(
        self: "SessionController",
        obj: CloseSessionReqInput,
        request: Optional[fastapi.Request] = None,
    ):
'''

NEW_HANDLE_HEADER = '''    @staticmethod
    def _handle_open_session_req_output(self: "SessionController", recv_obj):
'''


def _rewrite_method(text: str, class_name: str, method_name: str, new_header: str) -> str:
    """Replace [decorator..signature) of class_name.method_name with new_header;
    apply body rewrites (server_args.enable_streaming_session → config.*).
    Body stays in source class."""
    s, body_s, e = _method_ranges(text, class_name, method_name)
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])
    body_text = body_text.replace(
        "self.server_args.enable_streaming_session",
        "self.config.enable_streaming_session",
    )
    return "".join(lines[:s]) + new_header + body_text + "".join(lines[e:])


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    engine = wt / "python/sglang/srt/entrypoints/engine.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"
    new = wt / "python/sglang/srt/managers/session_controller.py"
    new.write_text(SKELETON)

    text = tm.read_text()

    # Drop session_futures = {} from init_running_status (now lives on SessionController).
    text = replace_call_site(
        text,
        old=(
            "        # Session\n"
            "        self.session_futures = {}  # session_id -> asyncio event\n"
            "\n"
        ),
        new="",
    )

    # Restructure init_request_dispatcher: pull dispatcher creation + init_communicators
    # earlier so owner-class ctors can find them. Strip AbortReq /
    # OpenSessionReqOutput / UpdateWeightFromDiskReqOutput entries from the early
    # dispatcher — they get re-registered post-construction by their owner classes
    # (SessionController registers OpenSessionReqOutput in __post_init__).
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
            "                (AbortReq, self._handle_abort_req),\n"
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
            "            auto_create_handle_loop=self.auto_create_handle_loop,\n"
            "            config=SessionControllerConfig(\n"
            "                enable_streaming_session=self.server_args.enable_streaming_session,\n"
            "            ),\n"
            "        )\n"
            "\n"
            "        # Init request dispatcher\n"
            "        self.init_request_dispatcher()"
        ),
    )

    # Convert _handle_open_session_req_output to @staticmethod with
    # self: "SessionController" typing; body stays in TM.
    text = _rewrite_method(
        text,
        class_name="TokenizerManager",
        method_name="_handle_open_session_req_output",
        new_header=NEW_HANDLE_HEADER,
    )

    tm.write_text(text)

    # Convert open_session + close_session in TokenizerControlMixin to @staticmethod
    # with self: "SessionController" typing; bodies stay in the mixin.
    mixin_text = control_mixin.read_text()
    mixin_text = _rewrite_method(
        mixin_text,
        class_name="TokenizerControlMixin",
        method_name="close_session",
        new_header=NEW_CLOSE_HEADER,
    )
    mixin_text = _rewrite_method(
        mixin_text,
        class_name="TokenizerControlMixin",
        method_name="open_session",
        new_header=NEW_OPEN_HEADER,
    )
    # SessionController is referenced as a forward-ref string in annotations, so
    # the mixin needs a TYPE_CHECKING import to satisfy static checkers.
    mixin_text = insert_after(
        mixin_text,
        anchor="    from sglang.srt.managers.tokenizer_manager import TokenizerManager\n",
        addition="    from sglang.srt.managers.session_controller import SessionController\n",
    )
    control_mixin.write_text(mixin_text)

    # Entrypoint caller rewrites: class-qualified call, ``self`` arg = the
    # composed SessionController instance. Write black-clean output so the
    # follow-up -move's pre-image is stable through pre-commit.
    engine_text = engine.read_text()
    engine_text = replace_call_site(
        engine_text,
        old=(
            "        return self.loop.run_until_complete(\n"
            "            self.tokenizer_manager.open_session(obj, None)\n"
            "        )\n"
        ),
        new=(
            "        return self.loop.run_until_complete(\n"
            "            TokenizerManager.open_session(\n"
            "                self.tokenizer_manager.session_controller, obj, None\n"
            "            )\n"
            "        )\n"
        ),
    )
    engine_text = replace_call_site(
        engine_text,
        old="        self.loop.run_until_complete(self.tokenizer_manager.close_session(obj, None))\n",
        new=(
            "        self.loop.run_until_complete(\n"
            "            TokenizerManager.close_session(\n"
            "                self.tokenizer_manager.session_controller, obj, None\n"
            "            )\n"
            "        )\n"
        ),
    )
    engine.write_text(engine_text)

    http_text = http_server.read_text()
    http_text = replace_call_site(
        http_text,
        old="        session_id = await _global_state.tokenizer_manager.open_session(obj, request)\n",
        new=(
            "        session_id = await TokenizerManager.open_session(\n"
            "            _global_state.tokenizer_manager.session_controller, obj, request\n"
            "        )\n"
        ),
    )
    http_text = replace_call_site(
        http_text,
        old="        await _global_state.tokenizer_manager.close_session(obj, request)\n",
        new=(
            "        await TokenizerManager.close_session(\n"
            "            _global_state.tokenizer_manager.session_controller, obj, request\n"
            "        )\n"
        ),
    )
    http_server.write_text(http_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
