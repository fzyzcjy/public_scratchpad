#!/usr/bin/env python3
"""Inline `ModelRunner.max_token_pool_size` property at its sole consumer in
`tp_worker.py`. Cut the @property from ModelRunner via `cut_lines` (decorators
included), then expand the if/else body inline at the consumer with `self.X`
rewritten to `self.model_runner.X` (cross-class self replacement allowed for
inline per EXECUTION_GUIDE).

Usage:
    uv run --python 3.12 tom_refactor_21.py run
    uv run --python 3.12 tom_refactor_21.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import cut_lines, find_method_lines, replace_call_site
from _runner import run_pr

BASE = "tom_refactor/20"
TARGET = "tom_refactor/21"


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    tp = wt / "python/sglang/srt/managers/tp_worker.py"

    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="max_token_pool_size"
    )
    cut_lines(mr, s, e)

    text = tp.read_text()
    text = replace_call_site(
        text,
        old=(
            "        self.max_req_len = min(\n"
            "            self.model_config.context_len - 1,\n"
            "            self.model_runner.max_token_pool_size - 1,\n"
            "        )"
        ),
        new=(
            "        if self.model_runner.is_hybrid_swa:\n"
            "            pool_tokens = self.model_runner.full_max_total_num_tokens\n"
            "        else:\n"
            "            pool_tokens = self.model_runner.max_total_num_tokens\n"
            "        self.max_req_len = min(\n"
            "            self.model_config.context_len - 1,\n"
            "            pool_tokens - 1,\n"
            "        )"
        ),
    )
    tp.write_text(text)

    git_add_and_commit(
        "Inline max_token_pool_size property at sole consumer",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
