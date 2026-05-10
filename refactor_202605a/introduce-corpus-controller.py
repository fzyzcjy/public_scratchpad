#!/usr/bin/env python3
"""Introduce CorpusController owner class."""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import (
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "introduce-corpus-controller"
SUBJECT = "Introduce CorpusController and move external corpus methods"
BODY = """\
Move 3 external-corpus methods (add_external_corpus / remove_external_corpus
/ list_external_corpora) from TokenizerControlMixin into a new
@dataclass(frozen=True, slots=True, kw_only=True) CorpusController in
managers/control/corpus_controller.py.

3 communicators are injected from facade post-init via attribute lookup
(facade fields are populated inside init_communicators).
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from sglang.srt.managers.communicator import FanOutCommunicator
from sglang.srt.managers.io_struct import (
    AddExternalCorpusReqInput,
    AddExternalCorpusReqOutput,
    ListExternalCorporaReqInput,
    ListExternalCorporaReqOutput,
    RemoveExternalCorpusReqInput,
    RemoveExternalCorpusReqOutput,
)

logger = logging.getLogger(__name__)


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
    # Facade callable injected so we can ensure the handle_loop is running
    # before sending RPCs (originally the moved methods called
    # self.auto_create_handle_loop() which only exists on TokenizerManager).
    auto_create_handle_loop: Callable[[], None]

'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    new = wt / "python/sglang/srt/managers/control/corpus_controller.py"

    method_names = (
        "add_external_corpus",
        "remove_external_corpus",
        "list_external_corpora",
    )
    name_to_range = {}
    for n in method_names:
        s, e = find_method_lines(
            control_mixin.read_text(),
            class_name="TokenizerControlMixin",
            method_name=n,
        )
        name_to_range[n] = (s, e)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(
            control_mixin.read_text(),
            class_name="TokenizerControlMixin",
            method_name=n,
        )
        cut_blocks[n] = cut_lines(control_mixin, s, e)

    def strip_typehint(body: str) -> str:
        return body.replace("self: TokenizerManager,", "self,").replace(
            "self: TokenizerManager\n", "self\n"
        )

    def rewrite_body(body: str) -> str:
        body = body.replace(
            "self.server_args.speculative_algorithm",
            "self.config.speculative_algorithm",
        )
        body = body.replace(
            "self.server_args.speculative_ngram_external_corpus_max_tokens",
            "self.config.max_external_corpus_tokens",
        )
        body = body.replace(
            "self.raw_tokenizer_wrapper.tokenizer", "self.tokenizer"
        )
        return body

    bodies = [rewrite_body(strip_typehint(cut_blocks[n])) for n in method_names]
    new.write_text(HEADER + "\n\n".join(b.rstrip() for b in bodies) + "\n")

    # ===== Update tokenizer_manager.py =====
    text = tm.read_text()

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.control.corpus_controller import (\n"
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
            "            add_external_corpus_communicator=getattr(self, '_add_external_corpus_communicator', None),\n"
            "            remove_external_corpus_communicator=getattr(self, '_remove_external_corpus_communicator', None),\n"
            "            list_external_corpora_communicator=getattr(self, '_list_external_corpora_communicator', None),\n"
            "            tokenizer=self.raw_tokenizer_wrapper.tokenizer,\n"
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

    # External entrypoint callers (http_server.py).
    import glob
    import re as _re
    for fpath in glob.glob(str(wt / "python/sglang/srt/entrypoints/**/*.py"), recursive=True):
        f = Path(fpath)
        t = f.read_text()
        t = _re.sub(
            r"\btokenizer_manager\.add_external_corpus\(",
            "tokenizer_manager.corpus_controller.add_external_corpus(",
            t,
        )
        t = _re.sub(
            r"\btokenizer_manager\.remove_external_corpus\(",
            "tokenizer_manager.corpus_controller.remove_external_corpus(",
            t,
        )
        t = _re.sub(
            r"\btokenizer_manager\.list_external_corpora\(",
            "tokenizer_manager.corpus_controller.list_external_corpora(",
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
