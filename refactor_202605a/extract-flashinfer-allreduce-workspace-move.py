#!/usr/bin/env python3
"""Move stage for extract-flashinfer-allreduce-workspace (MECH_COMMIT_SPLIT §"二段式"):

Pure cut+paste of the prep'd staticmethod into ``model_executor/kernel_warmup.py``
(co-located with the other ``kernel_warmup`` family functions). Body byte-equivalent.
Call site prefix-strip + import.
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
    replace_call_site,
)
from _runner import run_pr

ID = "extract-flashinfer-allreduce-workspace-move"
SUBJECT = "Move _pre_initialize_flashinfer_allreduce_workspace to kernel_warmup (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-flashinfer-allreduce-workspace-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    kw = wt / "python/sglang/srt/model_executor/kernel_warmup.py"

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="_pre_initialize_flashinfer_allreduce_workspace",
    )
    method_text = cut_lines(mr, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    function_text = dedent_method_to_function("".join(lines[1:]))
    append_to_file(kw, function_text)

    text = mr.read_text()
    text = replace_call_site(
        text,
        old="ModelRunner._pre_initialize_flashinfer_allreduce_workspace(",
        new="_pre_initialize_flashinfer_allreduce_workspace(",
    )
    text = replace_call_site(
        text,
        old=(
            "from sglang.srt.model_executor.kernel_warmup import (\n"
            "    _flashinfer_autotune_cache_path,\n"
            "    _should_run_flashinfer_autotune,\n"
            "    kernel_warmup,\n"
            ")\n"
        ),
        new=(
            "from sglang.srt.model_executor.kernel_warmup import (\n"
            "    _flashinfer_autotune_cache_path,\n"
            "    _pre_initialize_flashinfer_allreduce_workspace,\n"
            "    _should_run_flashinfer_autotune,\n"
            "    kernel_warmup,\n"
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
