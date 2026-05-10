#!/usr/bin/env python3
"""Remove unused ``RankZeroFilter`` class from ``model_runner.py``.

`grep -rn RankZeroFilter` across the repo finds zero call sites — the class
is dead code (defined but never instantiated). Ch1 normally bans dead-code
deletion, but the user explicitly authorized dropping this one rather than
relocating it elsewhere — so this commit removes the class definition
outright instead of moving it to ``utils/log_utils.py``.

If a future feature needs a rank-zero log filter, recreate at the right
home (utils/log_utils.py) when the consumer lands; until then the class
adds noise to model_runner.py without value.

Usage:
    uv run --python 3.12 drop-rank-zero-filter.py run
    uv run --python 3.12 drop-rank-zero-filter.py verify
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
    cut_lines,
    find_class_lines,
)
from _runner import run_pr

ID = "drop-rank-zero-filter"
SUBJECT = "Remove unused RankZeroFilter class from model_runner.py"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/nem-drop-legacy-fields"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    s, e = find_class_lines(mr.read_text(), class_name="RankZeroFilter")
    cut_lines(mr, s, e)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
