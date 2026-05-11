#!/usr/bin/env python3
"""Prep stage for extract-lora-moe-buffers (MECH_COMMIT_SPLIT §"二段式"):

In-place reshape of ``ModelRunner._init_lora_cuda_graph_moe_buffers`` toward
free-function form. Adds ``@staticmethod`` + kwarg-only signature; replaces
``self.X`` reads with kwargs. Call site rewritten to class-qualified form.
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

ID = "extract-lora-moe-buffers-prep"
SUBJECT = "Prep _init_lora_cuda_graph_moe_buffers for extraction"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-kernel-warmup-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    start, end = find_method_lines(
        text, class_name="ModelRunner", method_name="_init_lora_cuda_graph_moe_buffers"
    )
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    new_method = (
        method
        .replace(
            "    def _init_lora_cuda_graph_moe_buffers(self):\n",
            "    @staticmethod\n"
            "    def _init_lora_cuda_graph_moe_buffers(\n"
            "        *,\n"
            "        server_args: ServerArgs,\n"
            "        model: torch.nn.Module,\n"
            "        lora_manager: LoRAManager,\n"
            "        dtype: torch.dtype,\n"
            "    ):\n",
        )
        .replace("self.server_args", "server_args")
        .replace("self.model.modules()", "model.modules()")
        .replace("self.lora_manager", "lora_manager")
        .replace("self.dtype", "dtype")
    )
    text = "".join(lines[:start]) + new_method + "".join(lines[end:])

    text = replace_call_site(
        text,
        old="                self._init_lora_cuda_graph_moe_buffers()\n",
        new=(
            "                ModelRunner._init_lora_cuda_graph_moe_buffers(\n"
            "                    server_args=self.server_args,\n"
            "                    model=self.model,\n"
            "                    lora_manager=self.lora_manager,\n"
            "                    dtype=self.dtype,\n"
            "                )\n"
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
