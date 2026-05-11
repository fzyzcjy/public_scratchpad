#!/usr/bin/env python3
"""Move client-side wait/abort methods to ResponseEmitter."""

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

ID = "introduce-response-emitter-move"
SUBJECT = "Move 4 methods to ResponseEmitter"
BODY = """\
Cut 4 methods (_wait_one_response, create_abort_task,
_handle_abort_finish_reason, _coalesce_streaming_chunks) from TM. Body
rewrites self.server_args.X -> self.config.X. Callers + entrypoints rewired.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import asyncio
import logging
from http import HTTPStatus
from typing import Any, Optional, Union

import fastapi
from fastapi import BackgroundTasks

from sglang.srt.environ import envs
from sglang.srt.managers import logprob_ops
from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput

logger = logging.getLogger(__name__)

_REQUEST_STATE_WAIT_TIMEOUT = envs.SGLANG_REQUEST_STATE_WAIT_TIMEOUT.get()
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    re_ = wt / "python/sglang/srt/managers/response_emitter.py"

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

    re_text = re_.read_text()
    re_text = re_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    re_.write_text(re_text.rstrip() + "\n\n" + "\n\n".join(b.rstrip() for b in bodies) + "\n")

    text = tm.read_text()
    text = text.replace("self._wait_one_response(", "self.response_emitter._wait_one_response(")
    text = text.replace("self._handle_abort_finish_reason(", "self.response_emitter._handle_abort_finish_reason(")
    text = text.replace("self._coalesce_streaming_chunks(", "self.response_emitter._coalesce_streaming_chunks(")
    text = text.replace("self.create_abort_task(", "self.response_emitter.create_abort_task(")
    tm.write_text(text)

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
