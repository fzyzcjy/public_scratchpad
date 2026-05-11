#!/usr/bin/env python3
"""Move (pure cut/paste): CorpusController methods relocate from TokenizerControlMixin to target class."""

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
SUBJECT = "Hand external-corpus operations over to CorpusController"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut @staticmethod
add_external_corpus / remove_external_corpus / list_external_corpora
from TokenizerControlMixin; paste into CorpusController (drop
@staticmethod, replace ``self: "CorpusController"`` -> plain ``self``).
Caller prefix replacement in http_server.py:
``TokenizerManager.<method>(_global_state.tokenizer_manager.corpus_controller, ...)``
-> ``_global_state.tokenizer_manager.corpus_controller.<method>(...)``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''from sglang.srt.managers.communicator import FanOutCommunicator
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
    http_server = wt / "python/sglang/srt/entrypoints/http_server.py"
    cc = wt / "python/sglang/srt/managers/corpus_controller.py"

    method_names = ("add_external_corpus", "remove_external_corpus", "list_external_corpora")

    # Cut bottom-up so earlier ranges stay valid.
    name_to_range = {}
    for n in method_names:
        name_to_range[n] = find_method_lines(
            control_mixin.read_text(), class_name="TokenizerControlMixin", method_name=n
        )
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(
            control_mixin.read_text(),
            class_name="TokenizerControlMixin",
            method_name=n,
        )
        cut_blocks[n] = cut_lines(control_mixin, s, e)

    # Strip @staticmethod + restore plain self. Bodies are byte-identical to post-prep.
    def finalize(body: str) -> str:
        body = body.replace("    @staticmethod\n", "", 1)
        body = body.replace('self: "CorpusController", ', "self, ")
        body = body.replace('self: "CorpusController",\n', "self,\n")
        return body

    bodies = [finalize(cut_blocks[n]) for n in method_names]
    methods_text = "\n".join(b.rstrip() for b in bodies) + "\n"

    cc_text = cc.read_text()
    cc_text = cc_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    cc.write_text(cc_text.rstrip() + "\n\n" + methods_text)

    # Caller prefix replacement: TokenizerManager.<method>(<tm_expr>.corpus_controller, ...)
    # -> <tm_expr>.corpus_controller.<method>(...)
    text = http_server.read_text()
    text = text.replace(
        "    result = await TokenizerManager.add_external_corpus(\n"
        "        _global_state.tokenizer_manager.corpus_controller, obj\n"
        "    )\n",
        "    result = await _global_state.tokenizer_manager.corpus_controller.add_external_corpus(\n"
        "        obj\n"
        "    )\n",
    )
    text = text.replace(
        "    result = await TokenizerManager.remove_external_corpus(\n"
        "        _global_state.tokenizer_manager.corpus_controller, corpus_id\n"
        "    )\n",
        "    result = await _global_state.tokenizer_manager.corpus_controller.remove_external_corpus(\n"
        "        corpus_id\n"
        "    )\n",
    )
    text = text.replace(
        "    result = await TokenizerManager.list_external_corpora(\n"
        "        _global_state.tokenizer_manager.corpus_controller,\n"
        "    )\n",
        "    result = await _global_state.tokenizer_manager.corpus_controller.list_external_corpora()\n",
    )
    http_server.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
