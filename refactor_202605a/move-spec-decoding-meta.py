#!/usr/bin/env python3
"""Move _calculate_spec_decoding_metrics out of tokenizer_manager.py to a new
``managers/spec_decoding_meta.py`` module as free function
``fill_spec_decoding_meta``. The single ``self.X`` read
(server_args.speculative_num_draft_tokens) becomes an explicit kwarg.
"""

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
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "move-spec-decoding-meta"
SUBJECT = "Move _calculate_spec_decoding_metrics to managers/spec_decoding_meta.py"
BODY = """\
_calculate_spec_decoding_metrics becomes free function fill_spec_decoding_meta
in a new managers/spec_decoding_meta.py module. The single self.X read
(server_args.speculative_num_draft_tokens) becomes a
speculative_num_draft_tokens kwarg. Single caller in _handle_batch_output
updates accordingly. No behavior change.
"""
AREA = "mech_tokenizer_manager"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


HEADER = '''from __future__ import annotations

from typing import Any, Dict, Union

from sglang.srt.managers.io_struct import (
    BatchEmbeddingOutput,
    BatchStrOutput,
    BatchTokenIDOutput,
)


'''


def transform(wt: Path) -> None:
    tm = wt / "python/sglang/srt/managers/tokenizer_manager.py"
    new = wt / "python/sglang/srt/managers/spec_decoding_meta.py"

    s, e = find_method_lines(
        tm.read_text(), class_name="TokenizerManager", method_name="_calculate_spec_decoding_metrics"
    )
    method_text = cut_lines(tm, s, e)

    fn_text = dedent_method_to_function(method_text)
    fn_text = fn_text.replace(
        "def _calculate_spec_decoding_metrics(\n    self,\n    meta_info: Dict[str, Any],\n    recv_obj: Union[\n        BatchStrOutput,\n        BatchEmbeddingOutput,\n        BatchTokenIDOutput,\n    ],\n    i: int,\n) -> None:",
        "def fill_spec_decoding_meta(\n    meta_info: Dict[str, Any],\n    *,\n    recv_obj: Union[\n        BatchStrOutput,\n        BatchEmbeddingOutput,\n        BatchTokenIDOutput,\n    ],\n    i: int,\n    speculative_num_draft_tokens: int,\n) -> None:",
    )
    fn_text = fn_text.replace(
        "self.server_args.speculative_num_draft_tokens",
        "speculative_num_draft_tokens",
    )

    new.write_text(HEADER + fn_text.rstrip() + "\n")

    # ===== Update tokenizer_manager.py caller =====
    text = tm.read_text()

    text = insert_after(
        text,
        anchor="from sglang.srt.managers.async_dynamic_batch_tokenizer import AsyncDynamicbatchTokenizer\n",
        addition="from sglang.srt.managers import spec_decoding_meta\n",
    )

    text = replace_call_site(
        text,
        old="self._calculate_spec_decoding_metrics(meta_info, recv_obj, i)",
        new=(
            "spec_decoding_meta.fill_spec_decoding_meta(\n"
            "                        meta_info,\n"
            "                        recv_obj=recv_obj,\n"
            "                        i=i,\n"
            "                        speculative_num_draft_tokens=self.server_args.speculative_num_draft_tokens,\n"
            "                    )"
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
