#!/usr/bin/env python3
"""Prep stage for extract-prealloc-symm-pool (MECH_COMMIT_SPLIT §"二段式"):

In-place reshape: @staticmethod, parametrize four self.X reads, restore the
in-body local import (preserved from the original to avoid the
``sglang.srt.distributed`` import cycle). Call site becomes class-qualified.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, replace_call_site
from _runner import run_pr

ID = "extract-prealloc-symm-pool-prep"
SUBJECT = "Prep prealloc_symmetric_memory_pool for extraction: @staticmethod + kwargs"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/inline-max-pool-size"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    start, end = find_method_lines(
        text, class_name="ModelRunner", method_name="prealloc_symmetric_memory_pool"
    )
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    new_method = (
        method
        .replace(
            "    def prealloc_symmetric_memory_pool(self):\n",
            "    @staticmethod\n"
            "    def prealloc_symmetric_memory_pool(\n"
            "        *,\n"
            "        is_draft_worker: bool,\n"
            "        enable_symm_mem: bool,\n"
            "        device: str,\n"
            "        forward_stream: torch.cuda.Stream,\n"
            "    ):\n",
        )
        .replace("self.is_draft_worker", "is_draft_worker")
        .replace("self.server_args.enable_symm_mem", "enable_symm_mem")
        .replace("self.forward_stream", "forward_stream")
        .replace("self.device", "device")
        .replace(
            "            return\n\n        # Memory allocation",
            "            return\n\n        from sglang.srt.distributed import get_tp_group\n\n        # Memory allocation",
        )
    )
    text = "".join(lines[:start]) + new_method + "".join(lines[end:])

    text = replace_call_site(
        text,
        old="        self.prealloc_symmetric_memory_pool()\n",
        new=(
            "        ModelRunner.prealloc_symmetric_memory_pool(\n"
            "            is_draft_worker=self.is_draft_worker,\n"
            "            enable_symm_mem=self.server_args.enable_symm_mem,\n"
            "            device=self.device,\n"
            "            forward_stream=self.forward_stream,\n"
            "        )\n"
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
