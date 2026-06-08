#!/usr/bin/env python3
"""Move (pure cut/paste): TokenizedRequestBuilder methods relocate from TM to target class."""

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

ID = "introduce-tokenized-request-builder-move"
SUBJECT = "Hand TokenizedRequest assembly over to TokenizedRequestBuilder"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut @staticmethod
_create_tokenized_object + _resolve_embed_overrides from TokenizerManager;
paste into TokenizedRequestBuilder (drop @staticmethod, replace
``self: "TokenizedRequestBuilder"`` → plain ``self``). Rename
_create_tokenized_object → build (scope-induced; method is now public API
of new class). Caller prefix replacement: ``TokenizerManager._create_tokenized_object(self.tokenized_request_builder, ...)``
→ ``self.tokenized_request_builder.build(...)``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''from array import array
from typing import List, Union

import torch

from sglang.srt.managers.embed_types import PositionalEmbeds
from sglang.srt.managers.io_struct import (
    EmbeddingReqInput,
    GenerateReqInput,
    SessionParams,
    TokenizedEmbeddingReqInput,
    TokenizedGenerateReqInput,
)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    trb = wt / "python/sglang/srt/managers/tokenizer_manager_components/tokenized_request_builder.py"

    # Cut bottom-up.
    s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name="_resolve_embed_overrides")
    resolve_text = cut_lines(tm, s, e)
    s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name="_create_tokenized_object")
    create_text = cut_lines(tm, s, e)

    # Strip @staticmethod + restore plain self. Rename _create_tokenized_object → build.
    create_text = create_text.replace("    @staticmethod\n", "", 1)
    create_text = create_text.replace('self: "TokenizedRequestBuilder",', "self,")
    create_text = create_text.replace("def _create_tokenized_object(", "def build(", 1)
    # _resolve_embed_overrides keeps @staticmethod; no `self: TargetClass` annotation since it has no self.
    create_text = create_text.replace(
        "TokenizerManager._resolve_embed_overrides(",
        "self._resolve_embed_overrides(",
    )

    trb_text = trb.read_text()
    trb_text = trb_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    trb.write_text(trb_text.rstrip() + "\n" + create_text.rstrip() + "\n\n" + resolve_text.rstrip() + "\n")

    # Caller prefix replacement: TokenizerManager._create_tokenized_object(self.tokenized_request_builder, ... )
    #                           → self.tokenized_request_builder.build(...)
    text = tm.read_text()
    text = text.replace(
        "TokenizerManager._create_tokenized_object(\n            self.tokenized_request_builder,\n            ",
        "self.tokenized_request_builder.build(\n            ",
    )
    text = text.replace(
        "TokenizerManager._create_tokenized_object(\n                self.tokenized_request_builder,\n                ",
        "self.tokenized_request_builder.build(\n                ",
    )
    tm.write_text(text)

    # Test-file rewrite: ``_resolve_embed_overrides`` is a staticmethod moved
    # to TokenizedRequestBuilder. Tests calling ``TokenizerManager._resolve_embed_overrides(...)``
    # must now call ``TokenizedRequestBuilder._resolve_embed_overrides(...)``.
    test_file = wt / "test/registered/prefill_only/test_embed_overrides.py"
    if test_file.exists():
        t = test_file.read_text()
        # Doc-comment reference at top of file. Fix the class+path together
        # BEFORE the generic class-token rewrite, else the path anchor no
        # longer matches and the source path is left stale.
        t = t.replace(
            "- TokenizerManager._resolve_embed_overrides (tokenizer_manager.py)",
            "- TokenizedRequestBuilder._resolve_embed_overrides (tokenized_request_builder.py)",
        )
        t = t.replace(
            "TokenizerManager._resolve_embed_overrides",
            "TokenizedRequestBuilder._resolve_embed_overrides",
        )
        t = t.replace(
            "# TokenizerManager._resolve_embed_overrides",
            "# TokenizedRequestBuilder._resolve_embed_overrides",
        )
        # Add the TokenizedRequestBuilder import alongside the existing
        # TokenizerManager import (which may stay if other code uses it).
        t = t.replace(
            "from sglang.srt.managers.tokenizer_manager import TokenizerManager\n",
            "from sglang.srt.managers.tokenizer_manager_components.tokenized_request_builder import (\n"
            "    TokenizedRequestBuilder,\n"
            ")\n"
            "from sglang.srt.managers.tokenizer_manager import TokenizerManager\n",
        )
        test_file.write_text(t)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
