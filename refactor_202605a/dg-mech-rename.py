#!/usr/bin/env python3
"""Rename device_graphs free functions:

- ``init_device_graphs`` → ``create_device_graphs``
- ``init_piecewise_cuda_graphs`` → ``create_piecewise_cuda_graphs``

Per CLAUDE.md 3a — these are factory functions that return a constructed
runner; ``create_*`` reads truer than ``init_*`` (which suggests
in-place initialization on a passed-in object).

Caller sites: 4 in ``model_runner.py`` (3 in the ``initialize`` if/elif
chain calling ``init_device_graphs``, 1 calling ``init_piecewise_cuda_graphs``)
and 1 in ``weight_updater.py`` (recapture path).

Usage:
    uv run --python 3.12 dg-mech-rename.py run
    uv run --python 3.12 dg-mech-rename.py verify
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

ID = "dg-mech-rename"
SUBJECT = "Rename device_graphs init_* to create_*"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/kvc-mech-extract-mla-dim"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    files = [
        wt / "python/sglang/srt/model_executor/device_graphs.py",
        wt / "python/sglang/srt/model_executor/model_runner.py",
        wt / "python/sglang/srt/model_executor/weight_updater.py",
    ]
    for path in files:
        text = path.read_text()
        text = text.replace("init_piecewise_cuda_graphs", "create_piecewise_cuda_graphs")
        text = text.replace("init_device_graphs", "create_device_graphs")
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
