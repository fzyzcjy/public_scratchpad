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
SUBJECT = "Stage session lifecycle for handoff to SessionController"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds SessionController skeleton; wires composition in
TokenizerManager.__init__; converts open_session + close_session
(TokenizerControlMixin) and _handle_open_session_req_output
(TokenizerManager) to @staticmethod with self: "SessionController" typing;
applies body rewrites (self.server_args.enable_streaming_session →
self.config.enable_streaming_session); drops the
(OpenSessionReqOutput, ...) entry from init_request_dispatcher body and
registers it on the dispatcher in __post_init__ via lambda forwarder to
TM's staticmethod; drops session_futures from init_running_status;
rewrites entrypoint callers (engine.py, http_server.py) to
TokenizerManager.<method>(self.tokenizer_manager.session_controller, ...)
form. Methods stay on their source classes in this commit; the next
commit's pure cut/paste + caller prefix replacement + lambda→direct flip
completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Dict


@dataclass(slots=True, kw_only=True)
class SessionControllerConfig:
    enable_streaming_session: bool


@dataclass(slots=True, kw_only=True)
class SessionController:
    """open_session / close_session endpoints + OpenSessionReqOutput dispatcher handler."""

    send_to_scheduler: Any
    auto_create_handle_loop: Callable[[], None]
    config: SessionControllerConfig
    session_futures: Dict[str, asyncio.Future] = field(default_factory=dict)
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
    def handle_open_session_req_output(self: "SessionController", recv_obj):
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
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/session_controller.py"
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

    # Rewrite the OpenSessionReqOutput entry in init_request_dispatcher in place:
    # point at a lambda forwarder that runs the @staticmethod (still on TM)
    # with self.session_controller as the self arg. The follow-up -move commit
    # flips this lambda to a direct method ref once the body lives on
    # SessionController.
    text = replace_call_site(
        text,
        old="                (OpenSessionReqOutput, self._handle_open_session_req_output),\n",
        new=(
            "                (\n"
            "                    OpenSessionReqOutput,\n"
            "                    lambda recv_obj: TokenizerManager.handle_open_session_req_output(\n"
            "                        self.session_controller, recv_obj\n"
            "                    ),\n"
            "                ),\n"
        ),
    )

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_components.session_controller import (\n"
            "    SessionController,\n"
            "    SessionControllerConfig,\n"
            ")\n"
        ),
    )

    # Composition wiring. Anchor on the RequestMetricsRecorder block (closed by
    # ``)\n\n``) and insert AFTER it. Going *after* keeps request_metrics_recorder
    # above the Stage-4 controllers — subsequent preps (pause/wdu/lora/corpus)
    # anchor on ``# Session controller`` and insert BEFORE it, so they end up
    # between RequestMetricsRecorder and SessionController in textual order.
    # That's required because PauseController's ctor takes
    # ``metrics_collector=self.request_metrics_recorder.metrics_collector``.
    import re as _re

    _anchor_pat = _re.compile(
        r"        # Request metrics recorder\n"
        r"        self\.request_metrics_recorder = RequestMetricsRecorder\([^)]*?\)\n",
        _re.DOTALL,
    )
    _m = _anchor_pat.search(text)
    if _m is None:
        raise RuntimeError("RequestMetricsRecorder anchor not found")
    addition = (
        "\n"
        "        # Session controller\n"
        "        self.session_controller = SessionController(\n"
        "            send_to_scheduler=self.send_to_scheduler,\n"
        "            auto_create_handle_loop=self.auto_create_handle_loop,\n"
        "            config=SessionControllerConfig(\n"
        "                enable_streaming_session=self.server_args.enable_streaming_session,\n"
        "            ),\n"
        "        )\n"
    )
    text = text[: _m.end()] + addition + text[_m.end() :]

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
    # the mixin needs a TYPE_CHECKING import to satisfy static checkers. Insert
    # in alphabetical order (session_controller < tokenizer_manager).
    mixin_text = replace_call_site(
        mixin_text,
        old="    from sglang.srt.managers.tokenizer_manager import TokenizerManager\n",
        new=(
            "    from sglang.srt.managers.tokenizer_manager_components.session_controller import SessionController\n"
            "    from sglang.srt.managers.tokenizer_manager import TokenizerManager\n"
        ),
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
