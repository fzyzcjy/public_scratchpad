#!/usr/bin/env python3
"""Move 3 external-corpus methods from TokenizerControlMixin to CorpusController.

Per MECH_COMMIT_SPLIT, this is the physical-move step. The class skeleton +
composition wiring already landed in ``introduce-corpus-controller-prep``.
"""

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

ID = "introduce-corpus-controller-move"
SUBJECT = "Move external-corpus methods to CorpusController"
BODY = """\
Cut 3 methods (add_external_corpus / remove_external_corpus /
list_external_corpora) from TokenizerControlMixin and paste into
CorpusController. Bodies rewritten to address the new owner-class fields
(self.server_args.X -> self.config.X; self.raw_tokenizer_wrapper.tokenizer
-> self.tokenizer).

External entrypoint callers (http_server.py) updated to go through
``tokenizer_manager.corpus_controller``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import logging
import uuid
from typing import List

from sglang.srt.managers.communicator import FanOutCommunicator
from sglang.srt.managers.io_struct import (
    AddExternalCorpusReqInput,
    AddExternalCorpusReqOutput,
    ListExternalCorporaReqInput,
    ListExternalCorporaReqOutput,
    RemoveExternalCorpusReqInput,
    RemoveExternalCorpusReqOutput,
)
'''


def transform(wt: Path) -> None:
    control_mixin = wt / "python/sglang/srt/managers/tokenizer_control_mixin.py"
    cc = wt / "python/sglang/srt/managers/corpus_controller.py"

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
    methods_text = "\n\n".join(b.rstrip() for b in bodies) + "\n"

    # Append methods to CorpusController class + add the needed imports.
    cc_text = cc.read_text()
    cc_text = cc_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    cc.write_text(cc_text.rstrip() + "\n" + methods_text)

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
