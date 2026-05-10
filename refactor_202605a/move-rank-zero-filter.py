#!/usr/bin/env python3
"""Move ``RankZeroFilter`` class from ``model_runner.py`` to ``utils/log_utils.py``.

Per `module_level.md`, ``RankZeroFilter`` is a generic logging-filter class
that has no business living in ``model_runner.py``; the natural home is
``utils/log_utils.py`` (already the bucket for logging helpers). The class
has zero callers in the repo right now (so the move requires no consumer
rewires), but Ch1 forbids dead-code deletion -- we move it instead.

- Cut the class via ``find_class_lines`` + ``cut_lines`` (preserves byte
  layout including the trailing blank line into the next class).
- Append to ``utils/log_utils.py`` as-is. The class only uses ``logging``,
  which is already imported at the top of that file.
- No caller updates needed (zero existing imports of ``RankZeroFilter``).

Usage:
    uv run --python 3.12 move-rank-zero-filter.py run
    uv run --python 3.12 move-rank-zero-filter.py verify
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
    find_class_lines,
)
from _runner import run_pr

ID = "move-rank-zero-filter"
SUBJECT = "Move RankZeroFilter from model_runner.py to utils/log_utils.py"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/nem-migrate-cuda-graph"
AREA_BRANCH = f"tom_refactor_202605a/raw/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    log_utils = wt / "python/sglang/srt/utils/log_utils.py"

    s, e = find_class_lines(mr.read_text(), class_name="RankZeroFilter")
    class_text = cut_lines(mr, s, e)

    # ``cut_lines`` includes the trailing blank line(s); strip and re-attach
    # via the standard ``append_to_file`` separator so log_utils.py keeps a
    # clean single-blank-line gap before the moved class.
    append_to_file(log_utils, class_text.rstrip() + "\n")

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
