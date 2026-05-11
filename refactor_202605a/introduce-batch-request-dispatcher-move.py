#!/usr/bin/env python3
"""Move (pure cut/paste): relocate ``_handle_batch_request_dispatch`` from
TokenizerManager to ``BatchRequestDispatcher.dispatch``. Apply minimal
self-field rewrites (``_send_*`` callable kwargs, ``server_args.enable_trace``
+ ``disaggregation_mode`` config redirects). Flip TM's facade call to the
controller. Drop orphan imports from TM.
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

ID = "introduce-batch-request-dispatcher-move"
SUBJECT = "Hand batch-request dispatch over to BatchRequestDispatcher"
BODY = """\
Pure cut/paste move per MECH_COMMIT_SPLIT. Cut
``TokenizerManager._handle_batch_request_dispatch`` (an async method that
returns ``Tuple[List[AsyncGenerator], List[str]]``); paste into
BatchRequestDispatcher as ``dispatch`` (privacy-flip rename, scope-induced).

Minimal self-field rewrites inside the moved body:
  - ``self._send_one_request`` → ``self.send_one_request`` (Callable kwarg)
  - ``self._send_batch_request`` → ``self.send_batch_request``
  - ``self.server_args.enable_trace`` → ``self.config.enable_trace``
  - ``self.disaggregation_mode`` → ``self.config.disaggregation_mode``
  - ``self.request_preparer`` / ``self.response_emitter`` /
    ``self.rid_to_state`` / ``self.send_to_scheduler``: byte-equivalent
    (dataclass fields on BatchRequestDispatcher carry the same names)

TM facade ``_handle_batch_request`` now calls
``self.batch_request_dispatcher.dispatch(...)`` instead of the local helper.
Orphan imports (``copy`` / ``nullcontext`` /
``input_blocker_guard_region``) drop from TM since the body that needed
them has moved out.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = """import asyncio
import copy
import logging
from contextlib import nullcontext
from typing import AsyncGenerator, List, Optional, Tuple, Union

import fastapi

from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput
from sglang.srt.managers.tokenizer_manager_components.request_state import init_req
from sglang.srt.managers.scheduler_input_blocker import input_blocker_guard_region
from sglang.srt.utils import get_bool_env_var

logger = logging.getLogger(__name__)
"""


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    brd = wt / "python/sglang/srt/managers/tokenizer_manager_components/batch_request_dispatcher.py"

    # ---- 1. Cut the helper out of TM.
    s, e = find_method_lines(
        tm.read_text(),
        class_name="TokenizerManager",
        method_name="_handle_batch_request_dispatch",
    )
    method_text = cut_lines(tm, s, e)

    # ---- 2. Privacy-flip rename + minimal self-field rewrites.
    method_text = method_text.replace(
        "    async def _handle_batch_request_dispatch(\n"
        "        self,\n"
        "        obj: Union[GenerateReqInput, EmbeddingReqInput],\n"
        "        request: Optional[fastapi.Request] = None,\n"
        "    ):\n",
        "    async def dispatch(\n"
        "        self,\n"
        "        obj: Union[GenerateReqInput, EmbeddingReqInput],\n"
        "        request: Optional[fastapi.Request],\n"
        "    ) -> Tuple[List[AsyncGenerator], List[str]]:\n",
    )
    method_text = method_text.replace("self._send_one_request", "self.send_one_request")
    method_text = method_text.replace("self._send_batch_request", "self.send_batch_request")
    method_text = method_text.replace(
        "self.server_args.enable_trace", "self.config.enable_trace"
    )
    method_text = method_text.replace(
        "self.disaggregation_mode", "self.config.disaggregation_mode"
    )

    # ---- 3. Paste into BatchRequestDispatcher class body. Inject EXTRA_IMPORTS
    # after the existing ``from sglang.srt.managers.tokenizer_manager_components.response_emitter import ResponseEmitter``
    # block (last skeleton import).
    # The long import path gets black-wrapped to a 3-line form. Inject
    # EXTRA_IMPORTS right after that block.
    brd_text = brd.read_text()
    wrapped_anchor = (
        "from sglang.srt.managers.tokenizer_manager_components.response_emitter import (\n"
        "    ResponseEmitter,\n"
        ")\n"
    )
    if wrapped_anchor in brd_text:
        brd_text = brd_text.replace(
            wrapped_anchor, wrapped_anchor + "\n" + EXTRA_IMPORTS
        )
    else:
        brd_text = brd_text.replace(
            "from sglang.srt.managers.tokenizer_manager_components.response_emitter import ResponseEmitter\n",
            "from sglang.srt.managers.tokenizer_manager_components.response_emitter import ResponseEmitter\n\n"
            + EXTRA_IMPORTS,
        )
    # Append method at the end of the BatchRequestDispatcher class body. Anchor
    # on the last skeleton field declaration.
    brd_text = brd_text.replace(
        "    config: BatchRequestDispatcherConfig\n",
        "    config: BatchRequestDispatcherConfig\n\n" + method_text.rstrip() + "\n",
    )
    brd.write_text(brd_text)

    # ---- 4. Flip TM facade call: ``self._handle_batch_request_dispatch(...)`` →
    # ``self.batch_request_dispatcher.dispatch(...)``.
    text = tm.read_text()
    text = replace_call_site(
        text,
        old="        generators, rids = await self._handle_batch_request_dispatch(obj, request)\n",
        new="        generators, rids = await self.batch_request_dispatcher.dispatch(\n"
        "            obj, request\n"
        "        )\n",
    )

    # ---- 5. Drop orphan imports from TM (body that used them has moved out).
    text = replace_call_site(text, old="import copy\n", new="")
    text = replace_call_site(text, old="from contextlib import nullcontext\n", new="")
    text = replace_call_site(
        text,
        old="from sglang.srt.managers.scheduler_input_blocker import input_blocker_guard_region\n",
        new="",
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
