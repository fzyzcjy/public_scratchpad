#!/usr/bin/env python3
"""Prep stage for extract-init-cublas (MECH_COMMIT_SPLIT §"二段式"):

In-place reshape of ``ModelRunner.init_cublas`` to a free-function-ready
form. Body reads no ``self.X``; we just add ``@staticmethod`` and drop the
``self`` parameter, then rewrite the sole call site to class-qualified form
``ModelRunner.init_cublas()``. The follow-up ``-move`` commit cuts the
staticmethod out byte-equivalently into ``utils/common.py``.

Usage:
    uv run --python 3.12 extract-init-cublas-prep.py run
    uv run --python 3.12 extract-init-cublas-prep.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "extract-init-cublas-prep"
SUBJECT = "Prep init_cublas for extraction: @staticmethod + class-qualified call site"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Add @staticmethod + drop ``self`` parameter; body is already self-free.
    text = replace_call_site(
        text,
        old="    def init_cublas(self):\n",
        new="    @staticmethod\n    def init_cublas():\n",
    )
    # Class-qualified call site so the next commit is a pure prefix strip.
    text = replace_call_site(
        text,
        old="self.init_cublas()",
        new="ModelRunner.init_cublas()",
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
