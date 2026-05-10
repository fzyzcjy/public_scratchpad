#!/usr/bin/env python3
"""Rename ``_flashinfer_autotune`` → ``_run_flashinfer_autotune`` in
``model_executor/kernel_warmup.py``. Verb-leading reads truer than the
bare-noun original (the function executes the autotune; it is not the
autotune itself).

Caller is internal to ``kernel_warmup.py`` (1 site at line 141). The
substring check in ``pynccl_allocator.py`` still matches because the
new name contains the old name as a suffix.

Usage:
    uv run --python 3.12 kw-mech-rename.py run
    uv run --python 3.12 kw-mech-rename.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _runner import run_pr

ID = "kw-mech-rename"
SUBJECT = "Rename _flashinfer_autotune to _run_flashinfer_autotune in kernel_warmup"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/dg-mech-rename"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    path = wt / "python/sglang/srt/model_executor/kernel_warmup.py"
    text = path.read_text()
    # `_flashinfer_autotune(` matches both the def line and the call site.
    # The bare token also avoids touching ``_should_run_flashinfer_autotune``
    # / ``disable_flashinfer_autotune`` (different names).
    text = text.replace("_flashinfer_autotune(", "_run_flashinfer_autotune(")
    path.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
