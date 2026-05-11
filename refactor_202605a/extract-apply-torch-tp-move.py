#!/usr/bin/env python3
"""Move stage for extract-apply-torch-tp (MECH_COMMIT_SPLIT §"二段式"):

Pure cut+paste of the staticmethod prep'd in ``extract-apply-torch-tp-prep``
into ``layers/model_parallel.py``. Body byte-equivalent. Call-site rewrite is
a prefix strip.
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
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-apply-torch-tp-move"
SUBJECT = "Move apply_torch_tp to layers.model_parallel (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-apply-torch-tp-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    mp = wt / "python/sglang/srt/layers/model_parallel.py"

    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="apply_torch_tp"
    )
    method_text = cut_lines(mr, start, end)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod", f"first line not @staticmethod: {lines[0]!r}"
    function_text = dedent_method_to_function("".join(lines[1:]))

    mp_text = mp.read_text()
    if "logger = logging.getLogger(__name__)" not in mp_text:
        mp_text = insert_after(
            mp_text,
            anchor="from typing import Optional, Sequence\n",
            addition="import logging\n",
        )
        mp_text = insert_after(
            mp_text,
            anchor="from torch.distributed.device_mesh import DeviceMesh\n",
            addition="\nlogger = logging.getLogger(__name__)\n",
        )
        mp.write_text(mp_text)
    append_to_file(mp, function_text)

    text = mr.read_text()
    # Pre-commit may line-wrap the long call; strip the class qualifier
    # uniformly regardless of formatting.
    text = replace_call_site(
        text,
        old="ModelRunner.apply_torch_tp(",
        new="apply_torch_tp(",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.layers.logits_processor import LogitsProcessorOutput\n",
        addition="from sglang.srt.layers.model_parallel import apply_torch_tp\n",
    )
    mr.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
