#!/usr/bin/env python3
"""Prep stage for extract-init-threads-binding (MECH_COMMIT_SPLIT §"二段式"):

In-place reshape: @staticmethod, parametrize ``self.tp_rank`` / ``self.tp_size``,
turn the single ``self.local_omp_cpuid = ...`` write into a return. Call site
gains the writeback ``self.local_omp_cpuid = ModelRunner.init_threads_binding(...)``.
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

ID = "extract-init-threads-binding-prep"
SUBJECT = "Prep init_threads_binding for extraction: @staticmethod + kwargs + return-value"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-apply-torch-tp-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    start, end = find_method_lines(text, class_name="ModelRunner", method_name="init_threads_binding")
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    new_method = (
        method
        .replace(
            "    def init_threads_binding(self):\n",
            "    @staticmethod\n"
            "    def init_threads_binding(\n"
            "        *,\n"
            "        tp_rank: int,\n"
            "        tp_size: int,\n"
            "    ):\n",
        )
        .replace("self.tp_size", "tp_size")
        .replace("self.tp_rank", "tp_rank")
        .replace("self.local_omp_cpuid = ", "local_omp_cpuid = ")
    )
    new_method = new_method.rstrip() + "\n        return local_omp_cpuid\n\n"
    text = "".join(lines[:start]) + new_method + "".join(lines[end:])

    text = replace_call_site(
        text,
        old='        if self.device == "cpu":\n            self.init_threads_binding()',
        new=(
            '        if self.device == "cpu":\n'
            "            self.local_omp_cpuid = ModelRunner.init_threads_binding(\n"
            "                tp_rank=self.tp_rank, tp_size=self.tp_size\n"
            "            )"
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
