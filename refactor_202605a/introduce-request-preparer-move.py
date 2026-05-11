#!/usr/bin/env python3
"""Move (pure cut/paste): RequestPreparer methods relocate from TM to target class."""

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

ID = "introduce-request-preparer-move"
SUBJECT = "Move tokenize-orchestration methods to RequestPreparer: pure cut/paste + caller prefix replacement"
BODY = """\
Pure physical move per MECH_COMMIT_SPLIT. Cut the 4 @staticmethod
methods (_tokenize_one_request, _batch_tokenize_and_process,
_should_use_batch_tokenization, _batch_has_text) from TokenizerManager;
paste into RequestPreparer (drop @staticmethod, replace
``self: "RequestPreparer"`` -> plain ``self``). Cluster cross-calls
``TokenizerManager.<m>(self, ...)`` inside the moved bodies collapse
back to ``self.<m>(...)`` (now instance methods of the new class).
Caller prefix replacement at the 5 external sites:
``TokenizerManager.<m>(self.request_preparer, ...)`` ->
``self.request_preparer.<m>(...)``.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


EXTRA_IMPORTS = '''import logging
from typing import Any, Union

from sglang.srt.environ import envs
from sglang.srt.managers.embed_types import PositionalEmbeds  # noqa: F401
from sglang.srt.managers.io_struct import (
    EmbeddingReqInput,
    GenerateReqInput,
    TokenizedEmbeddingReqInput,
    TokenizedGenerateReqInput,
)
from sglang.srt.managers.schedule_batch import MultimodalDataItem

logger = logging.getLogger(__name__)
'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    rp = wt / "python/sglang/srt/managers/request_preparer.py"

    method_names = (
        "_tokenize_one_request",
        "_batch_tokenize_and_process",
        "_batch_has_text",
        "_should_use_batch_tokenization",
    )
    # Snapshot ranges to determine file order, then cut bottom-up so earlier
    # line numbers remain valid.
    name_to_range = {}
    for n in method_names:
        name_to_range[n] = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
    cut_blocks = {}
    for n in sorted(method_names, key=lambda nn: -name_to_range[nn][0]):
        s, e = find_method_lines(tm.read_text(), class_name="TokenizerManager", method_name=n)
        cut_blocks[n] = cut_lines(tm, s, e)

    # Strip @staticmethod + restore plain self for each method body. Collapse
    # cluster cross-calls back to instance form (they're now methods on the
    # same class).
    def strip_prep(body: str) -> str:
        body = body.replace("    @staticmethod\n", "", 1)
        body = body.replace('self: "RequestPreparer",', "self,")
        body = body.replace(
            "TokenizerManager._batch_has_text(self, ",
            "self._batch_has_text(",
        )
        body = body.replace(
            "TokenizerManager._tokenize_one_request(self, ",
            "self._tokenize_one_request(",
        )
        return body

    # Append in original (file) order: ascending start line.
    file_order = sorted(method_names, key=lambda nn: name_to_range[nn][0])
    rewritten = [strip_prep(cut_blocks[n]) for n in file_order]
    methods_text = "\n\n".join(b.rstrip() for b in rewritten) + "\n"

    rp_text = rp.read_text()
    rp_text = rp_text.replace(
        "from dataclasses import dataclass\n",
        "from dataclasses import dataclass\n\n" + EXTRA_IMPORTS,
    )
    rp.write_text(rp_text.rstrip() + "\n" + methods_text)

    # Caller prefix replacement: TokenizerManager.<m>(self.request_preparer, ... )
    #                           -> self.request_preparer.<m>(...)
    text = tm.read_text()
    text = text.replace(
        "await TokenizerManager._tokenize_one_request(self.request_preparer, ",
        "await self.request_preparer._tokenize_one_request(",
    )
    text = text.replace(
        "TokenizerManager._tokenize_one_request(self.request_preparer, ",
        "self.request_preparer._tokenize_one_request(",
    )
    text = text.replace(
        "await TokenizerManager._batch_tokenize_and_process(self.request_preparer, ",
        "await self.request_preparer._batch_tokenize_and_process(",
    )
    text = text.replace(
        "TokenizerManager._should_use_batch_tokenization(self.request_preparer, ",
        "self.request_preparer._should_use_batch_tokenization(",
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
