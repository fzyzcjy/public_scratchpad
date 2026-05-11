#!/usr/bin/env python3
"""Prep: RawTokenizerWrapper skeleton (fields only) + @property facade on TM +
retype TokenizerManager.init_tokenizer_and_processor as @staticmethod with
``self: "RawTokenizerWrapper"`` typing. Body of init_tokenizer_and_processor
STAYS on TM (and stays byte-equivalent to upstream modulo server_args /
model_config arg injection); move commit cuts and pastes.

Per MECH_COMMIT_SPLIT §"反模式：prep 大段加代码 + move 大段删代码"——this is the
canonical reshape that earlier "factory variant" iteration violated.
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

ID = "introduce-raw-tokenizer-wrapper-prep"
SUBJECT = "Stage tokenizer/processor ownership for handoff to RawTokenizerWrapper"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds RawTokenizerWrapper skeleton (fields only — no body), wires
composition in TokenizerManager.__init__, retypes
``init_tokenizer_and_processor`` as ``@staticmethod`` with
``self: "RawTokenizerWrapper"`` + injected ``server_args``/``model_config``
params (body left on TM, byte-equivalent modulo facade-attribute
re-routing onto the new params). Adds permanent
``@property tokenizer/processor/mm_processor`` (+ setters) on
TokenizerManager so external callers keep using ``tm.tokenizer`` —
``raw_tokenizer_wrapper`` stays as an internal-detail attribute.

The follow-up -move commit is pure cut/paste: relocate
``init_tokenizer_and_processor`` + ``InputFormat`` + module helpers
(``_get_processor_wrapper`` / ``_determine_tensor_transport_mode``) into
``raw_tokenizer_wrapper.py``; no body changes, no external caller
rewrites (the @property facade absorbs all of them).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer


@dataclass(slots=True, kw_only=True)
class RawTokenizerWrapper:
    """Owns tokenizer / processor / mm_processor / async_dynamic_batch_tokenizer."""

    tokenizer: Optional[Any] = None
    processor: Optional[Any] = None
    mm_processor: Optional[Any] = None
    async_dynamic_batch_tokenizer: Optional[AsyncDynamicbatchTokenizer] = None
'''


NEW_INIT_TOKENIZER_HEADER = '''    @staticmethod
    def init_tokenizer_and_processor(
        self: "RawTokenizerWrapper",
        server_args: ServerArgs,
        model_config: ModelConfig,
    ) -> None:
'''


PROPERTY_FACADE = '''
    # ---- raw_tokenizer_wrapper facade -----------------------------------
    # ``tokenizer`` / ``processor`` / ``mm_processor`` are the TokenizerManager
    # public read-API; storage is delegated to ``self.raw_tokenizer_wrapper``.
    # Read-only by design — writes go through ``self.raw_tokenizer_wrapper``
    # directly (the only writes happen inside
    # ``RawTokenizerWrapper.init_tokenizer_and_processor``).
    # ``async_dynamic_batch_tokenizer`` stays internal — access via
    # ``self.raw_tokenizer_wrapper.async_dynamic_batch_tokenizer`` directly.

    @property
    def tokenizer(self):
        return self.raw_tokenizer_wrapper.tokenizer

    @property
    def processor(self):
        return self.raw_tokenizer_wrapper.processor

    @property
    def mm_processor(self):
        return self.raw_tokenizer_wrapper.mm_processor

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


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/raw_tokenizer_wrapper.py"
    new.write_text(HEADER)

    text = tm.read_text()

    # ---- 1. Composition wiring: replace init_tokenizer_and_processor() call
    # with RawTokenizerWrapper construction + class-qualified factory call.
    text = replace_call_site(
        text,
        old=(
            "        # Initialize tokenizer and multimodalprocessor\n"
            "        self.init_tokenizer_and_processor()"
        ),
        new=(
            "        # Initialize tokenizer and multimodal processor\n"
            "        self.raw_tokenizer_wrapper = RawTokenizerWrapper()\n"
            "        TokenizerManager.init_tokenizer_and_processor(\n"
            "            self.raw_tokenizer_wrapper,\n"
            "            server_args=self.server_args,\n"
            "            model_config=self.model_config,\n"
            "        )"
        ),
    )

    # ---- 2. Import RawTokenizerWrapper into TM.
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition="from sglang.srt.managers.raw_tokenizer_wrapper import RawTokenizerWrapper\n",
    )

    # ---- 3. Retype init_tokenizer_and_processor on TM. Body stays here;
    # only swap header + rewrite ``self.server_args`` → ``server_args``,
    # ``self.model_config`` → ``model_config``, and drop the local
    # ``server_args = self.server_args`` alias (now a real param).
    s, body_s, e = _method_ranges(text, "TokenizerManager", "init_tokenizer_and_processor")
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])
    body_text = body_text.replace(
        "        server_args = self.server_args\n\n", ""
    )
    body_text = body_text.replace("self.server_args", "server_args")
    body_text = body_text.replace("self.model_config", "model_config")
    text = "".join(lines[:s]) + NEW_INIT_TOKENIZER_HEADER + body_text + "".join(lines[e:])

    # ---- 4. Insert @property facade at the end of ``class TokenizerManager``
    # body. Anchor on the first module-level definition that follows the class
    # (``class ServerStatus(Enum):``) and insert BEFORE it — the indented
    # @property block stays inside TM's class body; the unindented anchor line
    # closes the class scope.
    text = replace_call_site(
        text,
        old="class ServerStatus(Enum):\n",
        new=PROPERTY_FACADE.lstrip("\n") + "\nclass ServerStatus(Enum):\n",
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
