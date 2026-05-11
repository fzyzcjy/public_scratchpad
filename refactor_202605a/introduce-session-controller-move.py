#!/usr/bin/env python3
"""Move (pure cut/paste): SessionController methods relocate from source classes.

Per MECH_COMMIT_SPLIT §"拆 class 场景": this commit is purely physical.
All semantic work (skeleton, composition, staticmethod conversion, body
rewrites, __post_init__ forwarder, entrypoint caller rewrites) happened
in the prep commit. Here we only:

  - cut @staticmethod open_session / close_session out of
    TokenizerControlMixin
  - cut @staticmethod _handle_open_session_req_output out of
    TokenizerManager
  - paste all three into SessionController (drop @staticmethod, swap
    ``self: "SessionController"`` → plain ``self``)
  - caller prefix replacement at the entrypoint sites
  - lambda → direct flip in __post_init__ (and drop the now-unused
    local TokenizerManager import)
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, replace_call_site
from _runner import run_pr

ID = "introduce-session-controller-move"
SUBJECT = "Move session methods to SessionController: pure cut/paste + caller prefix replacement"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT §"拆 class 场景". Cut
@staticmethod open_session + close_session from TokenizerControlMixin and
@staticmethod _handle_open_session_req_output from TokenizerManager;
paste into SessionController (drop @staticmethod, replace
``self: "SessionController"`` → plain ``self``). Entrypoint callers
(engine.py, http_server.py) get pure prefix replacement:
``TokenizerManager.<method>(...session_controller, ...)`` →
``...session_controller.<method>(...)``. __post_init__ flips the lambda
forwarder to a direct method reference (and drops the now-unused
TokenizerManager local import).
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
)

logger = logging.getLogger(__name__)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    sc = wt / "python/sglang/srt/managers/session_controller.py"
    engine = wt / "python/sglang/srt/entrypoints/engine.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"

    # Cut bottom-up so earlier line numbers stay valid.
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

    def strip_staticmethod(body: str) -> str:
        body = body.replace("    @staticmethod\n", "", 1)
        body = body.replace('self: "SessionController",', "self,")
        body = body.replace('self: "SessionController"', "self")
        return body

    methods = (
        strip_staticmethod(open_text).rstrip()
        + "\n\n"
        + strip_staticmethod(close_text).rstrip()
        + "\n\n"
        + strip_staticmethod(handle_text).rstrip()
        + "\n"
    )

    sc_text = sc.read_text()
    sc_text = sc_text.replace(
        "from dataclasses import dataclass, field\n",
        "from dataclasses import dataclass, field\n\n" + EXTRA_IMPORTS,
    )
    # Flip lambda forwarder → direct method reference; drop the TokenizerManager
    # local import that only existed to support the forwarder.
    sc_text = replace_call_site(
        sc_text,
        old=(
            "    def __post_init__(self) -> None:\n"
            "        # Lambda forwarder: during prep the handler still lives on TokenizerManager\n"
            "        # as a @staticmethod with ``self: \"SessionController\"`` typing. The\n"
            "        # follow-up -move commit cuts the method into this class and flips this\n"
            "        # registration to a direct method reference.\n"
            "        from sglang.srt.managers.tokenizer_manager import TokenizerManager\n"
            "\n"
            "        self.dispatcher._mapping[OpenSessionReqOutput] = (\n"
            "            lambda recv_obj: TokenizerManager._handle_open_session_req_output(\n"
            "                self, recv_obj\n"
            "            )\n"
            "        )\n"
        ),
        new=(
            "    def __post_init__(self) -> None:\n"
            "        # TypeBasedDispatcher exposes only ``__init__(mapping)`` and ``__iadd__``;\n"
            "        # assign to its private ``_mapping`` to register a single (Type, handler)\n"
            "        # entry post-construction.\n"
            "        self.dispatcher._mapping[OpenSessionReqOutput] = self._handle_open_session_req_output\n"
        ),
    )
    sc.write_text(sc_text.rstrip() + "\n\n" + methods)

    # Drop the SessionController TYPE_CHECKING import added in prep — no longer
    # referenced now that the method bodies have moved out of the mixin.
    mixin_text = control_mixin.read_text()
    mixin_text = replace_call_site(
        mixin_text,
        old="    from sglang.srt.managers.session_controller import SessionController\n",
        new="",
    )
    control_mixin.write_text(mixin_text)

    # Caller prefix replacement at entrypoints. Pre-image is the black-clean
    # multi-line form that the prep commit wrote.
    engine_text = engine.read_text()
    engine_text = replace_call_site(
        engine_text,
        old=(
            "        return self.loop.run_until_complete(\n"
            "            TokenizerManager.open_session(\n"
            "                self.tokenizer_manager.session_controller, obj, None\n"
            "            )\n"
            "        )\n"
        ),
        new=(
            "        return self.loop.run_until_complete(\n"
            "            self.tokenizer_manager.session_controller.open_session(obj, None)\n"
            "        )\n"
        ),
    )
    engine_text = replace_call_site(
        engine_text,
        old=(
            "        self.loop.run_until_complete(\n"
            "            TokenizerManager.close_session(\n"
            "                self.tokenizer_manager.session_controller, obj, None\n"
            "            )\n"
            "        )\n"
        ),
        new=(
            "        self.loop.run_until_complete(\n"
            "            self.tokenizer_manager.session_controller.close_session(obj, None)\n"
            "        )\n"
        ),
    )
    engine.write_text(engine_text)

    http_text = http_server.read_text()
    http_text = replace_call_site(
        http_text,
        old=(
            "        session_id = await TokenizerManager.open_session(\n"
            "            _global_state.tokenizer_manager.session_controller, obj, request\n"
            "        )\n"
        ),
        new=(
            "        session_id = (\n"
            "            await _global_state.tokenizer_manager.session_controller.open_session(\n"
            "                obj, request\n"
            "            )\n"
            "        )\n"
        ),
    )
    http_text = replace_call_site(
        http_text,
        old=(
            "        await TokenizerManager.close_session(\n"
            "            _global_state.tokenizer_manager.session_controller, obj, request\n"
            "        )\n"
        ),
        new=(
            "        await _global_state.tokenizer_manager.session_controller.close_session(\n"
            "            obj, request\n"
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
