#!/usr/bin/env python3
"""Prep: CorpusController skeleton + composition wiring + in-place staticmethod conversion + caller rewrites."""

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

ID = "introduce-corpus-controller-prep"
SUBJECT = "Stage external-corpus operations for handoff to CorpusController"
BODY = """\
Per MECH_COMMIT_SPLIT §"拆 class 场景": prep does ALL semantic work.

Builds CorpusController skeleton; wires composition in TM.__init__;
converts add_external_corpus / remove_external_corpus / list_external_corpora
on TokenizerControlMixin to @staticmethod with self: "CorpusController"
annotation; applies body rewrites in-place (self.server_args.X ->
self.config.X). Methods stay on TokenizerControlMixin in this commit.
Entrypoint callers (http_server.py) rewritten to
``TokenizerManager.<method>(tokenizer_manager.corpus_controller, ...)``
form. The next commit's pure cut/paste + caller prefix replacement
completes the move.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


SKELETON = '''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True, slots=True, kw_only=True)
class CorpusControllerConfig:
    speculative_algorithm: str
    max_external_corpus_tokens: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CorpusController:
    """add / remove / list external corpus endpoints (n-gram speculative decoding)."""

    add_external_corpus_communicator: Any
    remove_external_corpus_communicator: Any
    list_external_corpora_communicator: Any
    tokenizer: Optional[Any]
    config: CorpusControllerConfig
    auto_create_handle_loop: Callable[[], None]
'''


def _method_ranges(text: str, class_name: str, method_name: str):
    """Return (start, body_start, end) line indices for a method (including decorators)."""
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


# New headers: @staticmethod + self: "CorpusController" typing. Bodies stay byte-identical
# except for the targeted self.server_args.X -> self.config.X rewrites.
NEW_ADD_HEADER = '''    @staticmethod
    async def add_external_corpus(
        self: "CorpusController", obj: AddExternalCorpusReqInput
    ) -> AddExternalCorpusReqOutput:
'''

NEW_REMOVE_HEADER = '''    @staticmethod
    async def remove_external_corpus(
        self: "CorpusController", corpus_id: str
    ) -> RemoveExternalCorpusReqOutput:
'''

NEW_LIST_HEADER = '''    @staticmethod
    async def list_external_corpora(
        self: "CorpusController",
    ) -> ListExternalCorporaReqOutput:
'''


def _rewrite_body(body_text: str) -> str:
    body_text = body_text.replace(
        "self.server_args.speculative_algorithm",
        "self.config.speculative_algorithm",
    )
    body_text = body_text.replace(
        "self.server_args.speculative_ngram_external_corpus_max_tokens",
        "self.config.max_external_corpus_tokens",
    )
    return body_text


def _convert_to_staticmethod(text: str, method_name: str, new_header: str) -> str:
    s, body_s, e = _method_ranges(text, "TokenizerControlMixin", method_name)
    lines = text.splitlines(keepends=True)
    body_text = "".join(lines[body_s:e])
    body_text = _rewrite_body(body_text)
    new_method = new_header + body_text
    return "".join(lines[:s]) + new_method + "".join(lines[e:])


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"
    new = wt / "python/sglang/srt/managers/tokenizer_manager_components/corpus_controller.py"

    new.write_text(SKELETON)

    # Composition wiring in TokenizerManager.__init__ + import.
    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.tokenizer_manager_components.corpus_controller import (\n"
            "    CorpusController,\n"
            "    CorpusControllerConfig,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
        new=(
            "        # Corpus controller\n"
            "        self.corpus_controller = CorpusController(\n"
            "            add_external_corpus_communicator=self.add_external_corpus_communicator,\n"
            "            remove_external_corpus_communicator=self.remove_external_corpus_communicator,\n"
            "            list_external_corpora_communicator=self.list_external_corpora_communicator,\n"
            "            tokenizer=self.tokenizer,\n"
            "            config=CorpusControllerConfig(\n"
            "                speculative_algorithm=self.server_args.speculative_algorithm or '',\n"
            "                max_external_corpus_tokens=self.server_args.speculative_ngram_external_corpus_max_tokens,\n"
            "            ),\n"
            "            auto_create_handle_loop=self.auto_create_handle_loop,\n"
            "        )\n"
            "\n"
            "        # Session controller\n"
            "        self.session_controller = SessionController(\n"
        ),
    )
    tm.write_text(text)

    # Convert 3 methods on TokenizerControlMixin to @staticmethod with self: "CorpusController"
    # typing. Apply body rewrites in-place. Bodies stay on TokenizerControlMixin in this commit.
    mixin_text = control_mixin.read_text()
    mixin_text = _convert_to_staticmethod(mixin_text, "add_external_corpus", NEW_ADD_HEADER)
    mixin_text = _convert_to_staticmethod(mixin_text, "remove_external_corpus", NEW_REMOVE_HEADER)
    mixin_text = _convert_to_staticmethod(mixin_text, "list_external_corpora", NEW_LIST_HEADER)
    control_mixin.write_text(mixin_text)

    # Caller rewrites: entrypoints (http_server.py). Methods live on TokenizerControlMixin
    # but TokenizerManager inherits, so TokenizerManager.<method>(...) resolves correctly.
    http_text = http_server.read_text()
    http_text = replace_call_site(
        http_text,
        old="    result = await _global_state.tokenizer_manager.add_external_corpus(obj)\n",
        new=(
            "    result = await TokenizerManager.add_external_corpus(\n"
            "        _global_state.tokenizer_manager.corpus_controller, obj\n"
            "    )\n"
        ),
    )
    http_text = replace_call_site(
        http_text,
        old="    result = await _global_state.tokenizer_manager.remove_external_corpus(corpus_id)\n",
        new=(
            "    result = await TokenizerManager.remove_external_corpus(\n"
            "        _global_state.tokenizer_manager.corpus_controller, corpus_id\n"
            "    )\n"
        ),
    )
    http_text = replace_call_site(
        http_text,
        old="    result = await _global_state.tokenizer_manager.list_external_corpora()\n",
        new=(
            "    result = await TokenizerManager.list_external_corpora(\n"
            "        _global_state.tokenizer_manager.corpus_controller,\n"
            "    )\n"
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
