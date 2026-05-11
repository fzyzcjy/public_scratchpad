#!/usr/bin/env python3
"""Move (pure cut/paste): ResponseEmitter methods relocate from TM to target class."""

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
SUBJECT = "Hand client-side wait/abort over to ResponseEmitter"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut @staticmethod
_wait_one_response, create_abort_task, _handle_abort_finish_reason,
_coalesce_streaming_chunks from TokenizerManager; paste into
ResponseEmitter (drop @staticmethod, replace
``self: "ResponseEmitter"`` → plain ``self``, strip ``TokenizerManager.``
prefix from sibling-method calls inside moved bodies). Caller prefix
replacement: ``TokenizerManager._wait_one_response(self.response_emitter, ...)``
→ ``self.response_emitter._wait_one_response(...)`` in TM facade;
``tm.create_abort_task(tm.response_emitter, obj)`` →
``tm.response_emitter.create_abort_task(obj)`` in entrypoints.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import asyncio
import logging
from http import HTTPStatus
from typing import Optional, Union

import fastapi
from fastapi import BackgroundTasks

from sglang.srt.environ import envs
from sglang.srt.managers import logprob_ops
from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput

logger = logging.getLogger(__name__)

_REQUEST_STATE_WAIT_TIMEOUT = envs.SGLANG_REQUEST_STATE_WAIT_TIMEOUT.get()

_INCREMENTAL_STREAMING_META_INFO_KEYS = (
    "output_token_logprobs",
    "output_top_logprobs",
    "output_token_ids_logprobs",
)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    re_ = wt / "python/sglang/srt/managers/response_emitter.py"

    # Cut bottom-up to keep line numbers stable.
    method_names = (
        "_coalesce_streaming_chunks",
        "_handle_abort_finish_reason",
        "_wait_one_response",
        "create_abort_task",
    )
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    def strip(body: str) -> str:
        # Drop @staticmethod decorator and restore plain self.
        body = body.replace("    @staticmethod\n", "", 1)
        body = body.replace('self: "ResponseEmitter",', "self,")
        body = body.replace('self: "ResponseEmitter"', "self")
        # Strip TokenizerManager.<sibling>(self, ...) form back to self.<sibling>(...).
        body = body.replace(
            "TokenizerManager._coalesce_streaming_chunks(\n"
            "                    self, out_list, obj.rid\n"
            "                )",
            "self._coalesce_streaming_chunks(out_list, obj.rid)",
        )
        body = body.replace(
            "TokenizerManager._handle_abort_finish_reason(\n"
            "                        self, out, state, is_stream\n"
            "                    )",
            "self._handle_abort_finish_reason(\n"
            "                        out, state, is_stream\n"
            "                    )",
        )
        return body

    # Preserve source-file definition order in the destination.
    bodies = [
        strip(cut_blocks["_coalesce_streaming_chunks"]),
        strip(cut_blocks["_handle_abort_finish_reason"]),
        strip(cut_blocks["_wait_one_response"]),
        strip(cut_blocks["create_abort_task"]),
    ]

    re_text = re_.read_text()
    re_text = re_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    re_.write_text(re_text.rstrip() + "\n\n" + "\n\n".join(b.rstrip() for b in bodies) + "\n")

    # TM-facade caller prefix replacement. Use regex to absorb both single-line
    # and black-wrapped multi-line forms.
    import re as _re

    text = tm.read_text()
    text = _re.sub(
        r"TokenizerManager\._wait_one_response\(\s*self\.response_emitter,\s*",
        "self.response_emitter._wait_one_response(",
        text,
    )
    tm.write_text(text)

    # Entrypoint caller prefix replacement: tm.create_abort_task(tm.response_emitter, X)
    # → tm.response_emitter.create_abort_task(X).
    import glob
    import re as _re
    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        t = f.read_text()
        t_new = _re.sub(
            r"(?<![\w.])([\w][\w.]*)\.create_abort_task\(\1\.response_emitter,\s*",
            r"\1.response_emitter.create_abort_task(",
            t,
        )
        if t_new != t:
            f.write_text(t_new)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
