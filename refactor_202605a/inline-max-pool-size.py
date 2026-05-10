#!/usr/bin/env python3
"""Inline `ModelRunner.max_token_pool_size` property at its sole consumer in
`tp_worker.py`. Cut the @property from ModelRunner via `cut_lines` (decorators
included), then expand the if/else body inline at the consumer with `self.X`
rewritten to `self.model_runner.X` (cross-class self replacement allowed for
inline per EXECUTION_GUIDE).

Usage:
    uv run --python 3.12 inline-max-pool-size.py run
    uv run --python 3.12 inline-max-pool-size.py verify
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

ID = "inline-max-pool-size"
SUBJECT = "Inline max_token_pool_size property at sole consumer"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/extract-init-threads-binding"
AREA_BRANCH = f"tom_refactor_202605a/raw/{AREA}"


def transform(wt: Path) -> None:
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
            "        pool_tokens = (\n"
            "            self.model_runner.full_max_total_num_tokens\n"
            "            if self.model_runner.is_hybrid_swa\n"
            "            else self.model_runner.max_total_num_tokens\n"
            "        )\n"
            "        self.max_req_len = min(\n"
            "            self.model_config.context_len - 1,\n"
            "            pool_tokens - 1,\n"
            "        )"
        ),
    )
    tp.write_text(text)

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
