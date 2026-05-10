#!/usr/bin/env python3
"""Fix ``pr-test-sgl-kernel.yml``'s ``sgl-kernel-mla-test`` step.

Upstream commit ``5fbec0e445`` moved ``test_mla_deepseek_v3.py`` from
``test/registered/mla/`` to ``test/manual/mla/`` ("prune per-commit CUDA
tests"), but the kernel CI workflow still hardcoded the old path —
``cd test/registered/mla && python3 test_mla_deepseek_v3.py``. The
result: every PR's ``call-sgl-kernel-tests / sgl-kernel-mla-test`` job
fast-fails, and downstream stages cascade-fail through
``check-stage-health``.

This commit retargets the path to ``test/manual/mla`` so the same test
runs from its new home. Strictly a CI infra fix — outside the refactor
scope, but required for our sandbox PR's CI to actually exercise the
chain.

Usage:
    uv run --python 3.12 fix-mla-ci-workflow.py run
    uv run --python 3.12 fix-mla-ci-workflow.py verify
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

ID = "fix-mla-ci-workflow"
SUBJECT = "Fix sgl-kernel CI: retarget mla test to test/manual after main file move"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/rwt-mech-slots"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    path = wt / ".github/workflows/pr-test-sgl-kernel.yml"
    text = path.read_text()
    text = replace_call_site(
        text,
        old="          cd test/registered/mla\n",
        new="          cd test/manual/mla\n",
    )
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
