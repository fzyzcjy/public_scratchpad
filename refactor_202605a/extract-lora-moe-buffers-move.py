#!/usr/bin/env python3
"""Move stage for extract-lora-moe-buffers (MECH_COMMIT_SPLIT §"二段式"):

Pure cut+paste of the staticmethod prep'd in -prep into
``lora/lora_manager.py``. Body byte-equivalent. Call-site rewrite is a
prefix strip.
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

ID = "extract-lora-moe-buffers-move"
SUBJECT = "Move _init_lora_cuda_graph_moe_buffers to lora.lora_manager (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-lora-moe-buffers-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    lm = wt / "python/sglang/srt/lora/lora_manager.py"

    start, end = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="_init_lora_cuda_graph_moe_buffers",
    )
    method_text = cut_lines(mr, start, end)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    function_text = dedent_method_to_function("".join(lines[1:]))
    append_to_file(lm, function_text)

    text = mr.read_text()
    text = replace_call_site(
        text,
        old="ModelRunner._init_lora_cuda_graph_moe_buffers(",
        new="_init_lora_cuda_graph_moe_buffers(",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.lora.lora_manager import LoRAManager\n",
        addition=(
            "from sglang.srt.lora.lora_manager import (\n"
            "    _init_lora_cuda_graph_moe_buffers,\n"
            ")\n"
        ),
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
