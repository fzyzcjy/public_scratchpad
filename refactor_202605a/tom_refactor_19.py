#!/usr/bin/env python3
"""Cut `apply_torch_tp` from ModelRunner; paste as a free function in
`layers/model_parallel.py`. Update sole caller and add an import.

Usage:
    uv run --python 3.12 tom_refactor_19.py run
    uv run --python 3.12 tom_refactor_19.py verify
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

BASE = "tom_refactor/18"
TARGET = "tom_refactor/19"


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    mp = wt / "python/sglang/srt/layers/model_parallel.py"

    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="apply_torch_tp"
    )
    method_text = cut_lines(mr, start, end)
    function_text = (
        dedent_method_to_function(method_text)
        .replace(
            "def apply_torch_tp(self):\n",
            "def apply_torch_tp(\n    *,\n    model,\n    device,\n    tp_size,\n):\n",
        )
        .replace("self.tp_size", "tp_size")
        .replace("self.device", "device")
        .replace("self.model", "model")
    )

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
    text = replace_call_site(
        text,
        old="self.apply_torch_tp()",
        new="apply_torch_tp(model=self.model, device=self.device, tp_size=self.tp_size)",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.layers.logits_processor import LogitsProcessorOutput\n",
        addition="from sglang.srt.layers.model_parallel import apply_torch_tp\n",
    )
    mr.write_text(text)

    git_add_and_commit(
        "Extract apply_torch_tp to free function in layers.model_parallel",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
