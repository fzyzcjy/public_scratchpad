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
from typing import Iterable, Optional, Union

import fastapi
from fastapi import BackgroundTasks

from sglang.srt.environ import envs
from sglang.srt.managers.io_struct import EmbeddingReqInput, GenerateReqInput
from sglang.srt.managers.tokenizer_manager_components import logprob_ops

logger = logging.getLogger(__name__)

_REQUEST_STATE_WAIT_TIMEOUT = envs.SGLANG_REQUEST_STATE_WAIT_TIMEOUT.get()
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    re_ = wt / "python/sglang/srt/managers/tokenizer_manager_components/response_emitter.py"

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
            "                    self,\n"
            "                    out_list,\n"
            "                    obj.rid,\n"
            "                    state.customized_info_accumulated.keys(),\n"
            "                )",
            "self._coalesce_streaming_chunks(\n"
            "                    out_list,\n"
            "                    obj.rid,\n"
            "                    state.customized_info_accumulated.keys(),\n"
            "                )",
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
        # ``\s*`` after ``\(`` + ``re.DOTALL`` together absorb the black-wrapped
        # multi-line form where ``(`` ends one line and the receiver is on the
        # next line.
        t_new = _re.sub(
            r"(?<![\w.])([\w][\w.]*)\.create_abort_task\(\s*\1\.response_emitter,\s*",
            r"\1.response_emitter.create_abort_task(",
            t,
            flags=_re.DOTALL,
        )
        if t_new != t:
            f.write_text(t_new)


    # The OpenAI serving unit tests stub create_abort_task on their fake TMs;
    # the serving code now reaches it via tokenizer_manager.response_emitter, so
    # route each fake through itself (the rerank-stub pattern).
    completions_test = wt / "test/registered/unit/entrypoints/openai/test_serving_completions.py"
    if completions_test.exists():
        ct = completions_test.read_text()
        ct = ct.replace(
            "        tm.create_abort_task = Mock()\n",
            "        tm.response_emitter = tm\n        tm.create_abort_task = Mock()\n",
        )
        completions_test.write_text(ct)

    chat_test = wt / "test/registered/unit/entrypoints/openai/test_serving_chat.py"
    if chat_test.exists():
        ct = chat_test.read_text()
        ct = ct.replace(
            "        self.create_abort_task = Mock()\n",
            "        self.response_emitter = self\n        self.create_abort_task = Mock()\n",
        )
        chat_test.write_text(ct)

    transcription_test = wt / "test/registered/unit/entrypoints/openai/test_serving_transcription.py"
    if transcription_test.exists():
        ct = transcription_test.read_text()
        ct = ct.replace(
            "        self.tokenizer = Mock()\n        self._stream_chunks = stream_chunks\n",
            "        self.tokenizer = Mock()\n        self.response_emitter = self\n        self._stream_chunks = stream_chunks\n",
        )
        transcription_test.write_text(ct)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
