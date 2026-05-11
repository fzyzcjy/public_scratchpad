#!/usr/bin/env python3
"""Move session methods to SessionController."""

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

ID = "introduce-session-controller-move"
SUBJECT = "Move session methods to SessionController"
BODY = """\
Cut open_session + close_session from TokenizerControlMixin and
_handle_open_session_req_output from TokenizerManager. Paste into
SessionController. Add __post_init__ that registers OpenSessionReqOutput
on the dispatcher.

Body rewrites: self.server_args.enable_streaming_session ->
self.config.enable_streaming_session. Entrypoint callers (engine.py,
http_server.py) rewired through self.tokenizer_manager.session_controller.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import logging
import uuid
from typing import Optional

import fastapi

from sglang.srt.managers.io_struct import (
    CloseSessionReqInput,
    OpenSessionReqInput,
    OpenSessionReqOutput,
)

logger = logging.getLogger(__name__)
'''


POST_INIT = '''
    def __post_init__(self) -> None:
        # TypeBasedDispatcher exposes only ``__init__(mapping)`` and ``__iadd__``;
        # assign to its private ``_mapping`` to register a single (Type, handler)
        # entry post-construction.
        self.dispatcher._mapping[OpenSessionReqOutput] = self._handle_open_session_req_output
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    sc = wt / "python/sglang/srt/managers/session_controller.py"

    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="_handle_open_session_req_output",
    )
    handle_text = cut_lines(tm, s, e)

    s, e = find_method_lines(
        control_mixin.read_text(),
        class_name="TokenizerControlMixin",
        method_name="close_session",
    )
    close_text = cut_lines(control_mixin, s, e)
    s, e = find_method_lines(
        control_mixin.read_text(),
        class_name="TokenizerControlMixin",
        method_name="open_session",
    )
    open_text = cut_lines(control_mixin, s, e)

    def rewrite(body: str) -> str:
        body = body.replace("self: TokenizerManager,", "self,").replace(
            "self: TokenizerManager\n", "self\n"
        )
        body = body.replace(
            "self.server_args.enable_streaming_session",
            "self.config.enable_streaming_session",
        )
        return body

    methods = (
        POST_INIT
        + "\n"
        + rewrite(open_text).rstrip()
        + "\n\n"
        + rewrite(close_text).rstrip()
        + "\n\n"
        + rewrite(handle_text).rstrip()
        + "\n"
    )

    sc_text = sc.read_text()
    sc_text = sc_text.replace(
        "from dataclasses import dataclass, field\n",
        "from dataclasses import dataclass, field\n\n" + EXTRA_IMPORTS,
    )
    sc.write_text(sc_text.rstrip() + "\n" + methods)

    # Entrypoint callers.
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
