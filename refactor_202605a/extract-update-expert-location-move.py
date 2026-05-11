#!/usr/bin/env python3
"""Move stage for extract-update-expert-location (MECH_COMMIT_SPLIT §"二段式"):

Pure cut+paste into ``eplb/expert_location_updater.py``. Body byte-equivalent.
The eplb_manager call-site is a prefix strip and the temporary ``ModelRunner``
import (introduced in the prep commit) is dropped in favour of a direct import
of the free function.
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

ID = "extract-update-expert-location-move"
SUBJECT = "Move update_expert_location_with_recovery to eplb.expert_location_updater (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-update-expert-location-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    elu = wt / "python/sglang/srt/eplb/expert_location_updater.py"
    eplb = wt / "python/sglang/srt/eplb/eplb_manager.py"

    # Ensure target module imports ``nn`` (referenced by the new signature).
    elu_text = elu.read_text()
    if "from torch import nn\n" not in elu_text:
        elu_text = insert_after(
            elu_text,
            anchor="import torch\n",
            addition="from torch import nn\n",
        )
        elu.write_text(elu_text)

    start, end = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="update_expert_location_with_recovery",
    )
    method_text = cut_lines(mr, start, end)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    function_text = dedent_method_to_function("".join(lines[1:]))
    append_to_file(elu, function_text)

    text = eplb.read_text()
    text = replace_call_site(
        text,
        old="ModelRunner.update_expert_location_with_recovery(",
        new="update_expert_location_with_recovery(",
    )
    # Drop the temporary ModelRunner import the prep commit introduced.
    text = replace_call_site(
        text,
        old="from sglang.srt.model_executor.model_runner import ModelRunner\n",
        new="",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.eplb.expert_location import ExpertLocationMetadata\n",
        addition="from sglang.srt.eplb.expert_location_updater import update_expert_location_with_recovery\n",
    )
    eplb.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
