#!/usr/bin/env python3
"""Cut `_init_lora_cuda_graph_moe_buffers` from ModelRunner; paste as a free
function in `lora/lora_manager.py`. Body byte-identical modulo `self.X` ->
explicit kwargs (`server_args`, `model`, `lora_manager`, `dtype`). The sole
caller in `ModelRunner.initialize()` is updated to call the free function.
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

ID = "extract-lora-moe-buffers"
SUBJECT = "Extract _init_lora_cuda_graph_moe_buffers to free function in lora_manager"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/extract-kernel-warmup"
AREA_BRANCH = f"tom_refactor_202605a/raw/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    lm = wt / "python/sglang/srt/lora/lora_manager.py"

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="_init_lora_cuda_graph_moe_buffers",
    )
    fn = dedent_method_to_function(cut_lines(mr, s, e))
    fn = fn.replace(
        "def _init_lora_cuda_graph_moe_buffers(self):\n",
        "def _init_lora_cuda_graph_moe_buffers(\n"
        "    *,\n"
        "    server_args: ServerArgs,\n"
        "    model: torch.nn.Module,\n"
        "    lora_manager: LoRAManager,\n"
        "    dtype: torch.dtype,\n"
        "):\n",
    )
    fn = fn.replace("self.server_args", "server_args")
    fn = fn.replace("self.model.modules()", "model.modules()")
    fn = fn.replace("self.lora_manager", "lora_manager")
    fn = fn.replace("self.dtype", "dtype")
    append_to_file(lm, fn)

    # ---- Update ModelRunner: caller + import ----
    text = mr.read_text()

    text = replace_call_site(
        text,
        old="                self._init_lora_cuda_graph_moe_buffers()\n",
        new=(
            "                _init_lora_cuda_graph_moe_buffers(\n"
            "                    server_args=self.server_args,\n"
            "                    model=self.model,\n"
            "                    lora_manager=self.lora_manager,\n"
            "                    dtype=self.dtype,\n"
            "                )\n"
        ),
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
