#!/usr/bin/env python3
"""Move stage for extract-autotune-helpers (MECH_COMMIT_SPLIT §"二段式"):

Cut+paste both staticmethods to the new file ``model_executor/model_runner_components/kernel_warmup.py``.
Bodies byte-equivalent. Call sites prefix-strip.
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

ID = "extract-autotune-helpers-move"
SUBJECT = "Move _should_run_flashinfer_autotune and _flashinfer_autotune_cache_path to kernel_warmup (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-autotune-helpers-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_HEADER = (
    "from __future__ import annotations\n"
    "\n"
    "import hashlib\n"
    "from pathlib import Path\n"
    "\n"
    "import torch\n"
    "\n"
    "from sglang.srt.configs.model_config import ModelConfig\n"
    "from sglang.srt.environ import envs\n"
    "from sglang.srt.server_args import ServerArgs\n"
    "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n"
)


def _cut_and_dedent(mr: Path, method_name: str) -> str:
    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name=method_name)
    method_text = cut_lines(mr, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    return dedent_method_to_function("".join(lines[1:]))


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    kw = wt / "python/sglang/srt/model_executor/model_runner_components/kernel_warmup.py"

    kw.write_text(_HEADER)

    fn1 = _cut_and_dedent(mr, "_should_run_flashinfer_autotune")
    append_to_file(kw, fn1)
    fn2 = _cut_and_dedent(mr, "_flashinfer_autotune_cache_path")
    append_to_file(kw, fn2)

    text = mr.read_text()
    text = replace_call_site(text, old="ModelRunner._should_run_flashinfer_autotune(", new="_should_run_flashinfer_autotune(")
    text = replace_call_site(text, old="ModelRunner._flashinfer_autotune_cache_path(", new="_flashinfer_autotune_cache_path(")
    text = insert_after(
        text,
        anchor=(
            "from sglang.srt.model_executor.cuda_graph_runner import (\n"
            "    DecodeInputBuffers,\n"
            "    set_torch_compile_config,\n"
            ")\n"
        ),
        addition=(
            "from sglang.srt.model_executor.model_runner_components.kernel_warmup import (\n"
            "    _flashinfer_autotune_cache_path,\n"
            "    _should_run_flashinfer_autotune,\n"
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
