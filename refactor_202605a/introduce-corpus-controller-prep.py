#!/usr/bin/env python3
"""Prep step for introducing CorpusController.

Creates managers/corpus_controller.py with empty class skeleton (dataclasses
only, no methods) and adds composition wiring to TokenizerManager.__init__.
Methods stay on TokenizerControlMixin in this commit; subsequent commit
``introduce-corpus-controller-move`` cuts them over.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "introduce-corpus-controller-prep"
SUBJECT = "Prep CorpusController: empty skeleton + composition wiring"
BODY = """\
Per MECH_COMMIT_SPLIT: split the bundled introduce-corpus-controller into
prep + move. Prep creates the class skeleton + composition wiring only;
methods still live on TokenizerControlMixin in this commit. The next
commit cuts them over.
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


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/corpus_controller.py"

    new.write_text(SKELETON)

    text = tm.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.tokenizer_control_mixin import TokenizerControlMixin\n",
        addition=(
            "from sglang.srt.managers.corpus_controller import (\n"
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


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
