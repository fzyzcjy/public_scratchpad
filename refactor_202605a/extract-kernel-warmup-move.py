#!/usr/bin/env python3
"""Move stage for extract-kernel-warmup (MECH_COMMIT_SPLIT §"二段式"):

Cut+paste two staticmethods to ``model_executor/model_runner_components/kernel_warmup.py``. Bodies
byte-equivalent. Call sites prefix-strip.
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

ID = "extract-kernel-warmup-move"
SUBJECT = "Move kernel_warmup + _run_flashinfer_autotune to kernel_warmup module (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-kernel-warmup-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _cut_and_dedent(mr: Path, method_name: str) -> str:
    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name=method_name)
    method_text = cut_lines(mr, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    return dedent_method_to_function("".join(lines[1:]))


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    kw = wt / "python/sglang/srt/model_executor/model_runner_components/kernel_warmup.py"

    # Add logger to target file if not present.
    kw_text = kw.read_text()
    if "logger = logging.getLogger(__name__)" not in kw_text:
        kw_text = insert_after(
            kw_text,
            anchor="from sglang.srt.environ import envs\n",
            addition="\nimport logging\n\nlogger = logging.getLogger(__name__)\n",
        )
        kw.write_text(kw_text)

    fn1 = _cut_and_dedent(mr, "kernel_warmup")
    # ``kernel_warmup`` body has a class-qualified call to
    # ``ModelRunner._run_flashinfer_autotune(...)`` (prep-stage scaffolding).
    # Strip the qualifier — both functions now live in this module.
    fn1 = fn1.replace("ModelRunner._run_flashinfer_autotune(", "_run_flashinfer_autotune(")
    append_to_file(kw, fn1)
    fn2 = _cut_and_dedent(mr, "_run_flashinfer_autotune")
    append_to_file(kw, fn2)

    # ModelRunner: caller prefix-strip + import.
    text = mr.read_text()
    text = replace_call_site(text, old="ModelRunner.kernel_warmup(", new="kernel_warmup(")
    text = replace_call_site(
        text,
        old=(
            "from sglang.srt.model_executor.model_runner_components.kernel_warmup import (\n"
            "    _flashinfer_autotune_cache_path,\n"
            "    _should_run_flashinfer_autotune,\n"
            ")\n"
        ),
        new=(
            "from sglang.srt.model_executor.model_runner_components.kernel_warmup import (\n"
            "    _flashinfer_autotune_cache_path,\n"
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
