#!/usr/bin/env python3
"""Cut `init_cublas` method from ModelRunner; paste as a free function in
`utils/common.py`. Update the sole caller and add an import.

Usage:
    uv run --python 3.12 tom_refactor_18.py run     # build + push to upstream
    uv run --python 3.12 tom_refactor_18.py verify  # diff against upstream
    uv run --python 3.12 tom_refactor_18.py apply <wt>  # apply on existing worktree
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
    add_to_grouped_import,
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    replace_call_site,
)
from _runner import run_pr

BASE = "tom_refactor/17"
TARGET = "tom_refactor/18"


def transform(wt: Path) -> None:
    sys.path.insert(0, "/Users/tom/main/workspaces/ws-main/worktrees/sglang-dev-a/.claude/skills/mechanical-refactor-verify")
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    common = wt / "python/sglang/srt/utils/common.py"

    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="init_cublas"
    )
    method_text = cut_lines(mr, start, end)
    function_text = dedent_method_to_function(method_text).replace(
        "def init_cublas(self):", "def init_cublas():"
    )
    append_to_file(common, function_text)

    text = mr.read_text()
    text = replace_call_site(text, old="self.init_cublas()", new="init_cublas()")
    text = add_to_grouped_import(
        text, anchor_name="init_custom_process_group", new_line="    init_cublas,"
    )
    mr.write_text(text)

    git_add_and_commit("Extract init_cublas to free function in utils.common", cwd=str(wt))


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
