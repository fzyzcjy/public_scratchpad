#!/usr/bin/env python3
"""Prep: ResponseEmitter skeleton + composition wiring + in-place staticmethod conversion + caller rewrites."""

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

ID = "introduce-response-emitter-prep"
SUBJECT = "Stage client-side wait/abort for handoff to ResponseEmitter"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds ResponseEmitter skeleton; wires composition in TM.__init__;
converts _wait_one_response, create_abort_task, _handle_abort_finish_reason,
_coalesce_streaming_chunks to @staticmethod with
self: "ResponseEmitter" annotation; applies body rewrites
(self.server_args.incremental_streaming_output -> self.config.incremental_streaming_output,
self.server_args.enable_lora -> self.config.enable_lora, sibling
self._coalesce_streaming_chunks / self._handle_abort_finish_reason calls
through TokenizerManager._X(self, ...) form); rewrites TM-facade callers
of _wait_one_response (5 sites) to
TokenizerManager._wait_one_response(self.response_emitter, ...)
form; rewrites entrypoint create_abort_task callers similarly. Methods
stay on TM in this commit; the next commit's pure cut/paste + caller
prefix replacement completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict

from sglang.srt.managers.tokenizer_manager_components.lora_controller import LoraController
from sglang.srt.managers.tokenizer_manager_components.request_log_manager import RequestLogManager
from sglang.srt.managers.tokenizer_manager_components.request_state import ReqState


@dataclass(slots=True, kw_only=True)
class ResponseEmitterConfig:
    incremental_streaming_output: bool
    enable_lora: bool


@dataclass(slots=True, kw_only=True)
class ResponseEmitter:
    """Drains rid_to_state[rid].out_list and yields per-request dicts to HTTP clients."""

    rid_to_state: Dict[str, ReqState]
    lora_controller: LoraController
    request_log_manager: RequestLogManager
    abort_request: Callable[..., None]
    config: ResponseEmitterConfig
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


# Replacement headers: @staticmethod + self: "ResponseEmitter" typing.
NEW_COALESCE_HEADER = '''    @staticmethod
    def _coalesce_streaming_chunks(
        self: "ResponseEmitter",
        out_list: list,
        rid: str,
    ) -> dict:
'''

NEW_HANDLE_ABORT_HEADER = '''    @staticmethod
    async def _handle_abort_finish_reason(
        self: "ResponseEmitter",
        out: dict,
        state: ReqState,
        is_stream: bool,
    ) -> Optional[dict]:
'''

NEW_WAIT_HEADER = '''    @staticmethod
    async def _wait_one_response(
        self: "ResponseEmitter",
        obj: Union[GenerateReqInput, EmbeddingReqInput],
        request: Optional[fastapi.Request] = None,
    ):
'''

NEW_CREATE_ABORT_HEADER = '''    @staticmethod
    def create_abort_task(self: "ResponseEmitter", obj: GenerateReqInput):
'''


def _retype_method(text: str, method_name: str, new_header: str) -> str:
    s, body_s, e = _method_ranges(text, "TokenizerManager", method_name)
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])
    new_method = new_header + body_text
    return "".join(lines[:s]) + new_method + "".join(lines[e:])


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/response_emitter.py"
    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_components.response_emitter import (\n"
            "    ResponseEmitter,\n"
            "    ResponseEmitterConfig,\n"
            ")\n"
        ),
    )

    # Composition wiring.
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
            "            lora_controller=self.lora_controller,\n"
            "            request_log_manager=self.request_log_manager,\n"
            "            abort_request=self.abort_request,\n"
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

    # Convert the 4 methods to @staticmethod with self: "ResponseEmitter" typing.
    # Body stays in TM class; rewrites are applied below.
    text = _retype_method(text, "_coalesce_streaming_chunks", NEW_COALESCE_HEADER)
    text = _retype_method(text, "_handle_abort_finish_reason", NEW_HANDLE_ABORT_HEADER)
    text = _retype_method(text, "_wait_one_response", NEW_WAIT_HEADER)
    text = _retype_method(text, "create_abort_task", NEW_CREATE_ABORT_HEADER)

    # Body rewrites: server_args.X → config.X. Inside the now-staticmethod
    # bodies, `self` is a ResponseEmitter, so these references must hit the
    # config dataclass field.
    text = text.replace(
        "                is_stream and self.server_args.incremental_streaming_output\n",
        "                is_stream and self.config.incremental_streaming_output\n",
    )
    text = text.replace(
        "            if self.server_args.enable_lora and state.obj.lora_path:\n",
        "            if self.config.enable_lora and state.obj.lora_path:\n",
    )

    # Sibling-method self-calls (still on TokenizerManager class as
    # @staticmethod): explicit TokenizerManager.<method>(self, ...) form.
    text = replace_call_site(
        text,
        old="                out = self._coalesce_streaming_chunks(out_list, obj.rid)\n",
        new="                out = TokenizerManager._coalesce_streaming_chunks(\n"
            "                    self, out_list, obj.rid\n"
            "                )\n",
    )
    text = replace_call_site(
        text,
        old=(
            "                    abort_out = await self._handle_abort_finish_reason(\n"
            "                        out, state, is_stream\n"
            "                    )\n"
        ),
        new=(
            "                    abort_out = await TokenizerManager._handle_abort_finish_reason(\n"
            "                        self, out, state, is_stream\n"
            "                    )\n"
        ),
    )

    # TM-facade callers of _wait_one_response (5 sites: 1 in _handle_one_request,
    # 4 in _handle_batch_request). Rewrite to
    # TokenizerManager._wait_one_response(self.response_emitter, ...).
    text = text.replace(
        "self._wait_one_response(",
        "TokenizerManager._wait_one_response(self.response_emitter, ",
    )

    tm.write_text(text)

    # Entrypoint callers of create_abort_task: rewrite to pass response_emitter
    # as the explicit first arg of the now-staticmethod. We deliberately keep
    # the receiver-instance form (``tm.create_abort_task(tm.response_emitter, obj)``)
    # rather than ``TokenizerManager.create_abort_task(...)`` so we don't have
    # to add a TokenizerManager import to anthropic/serving.py (and avoid
    # accidental import cycles in TYPE_CHECKING-only entrypoints).
    import glob
    import re as _re
    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        t = f.read_text()
        new_t = _re.sub(
            r"(?<![\w.])([\w][\w.]*)\.create_abort_task\(",
            lambda m: f"{m.group(1)}.create_abort_task({m.group(1)}.response_emitter, ",
            t,
        )
        if new_t != t:
            f.write_text(new_t)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
