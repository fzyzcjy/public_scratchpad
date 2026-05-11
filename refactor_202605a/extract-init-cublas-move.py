#!/usr/bin/env python3
"""Move stage for extract-init-cublas (MECH_COMMIT_SPLIT §"二段式"):

Pure cut+paste of the staticmethod prep'd in ``extract-init-cublas-prep``
into ``utils/common.py``. Body byte-equivalent. Call-site rewrite is a
prefix strip (``ModelRunner.init_cublas()`` → ``init_cublas()``).

Usage:
    uv run --python 3.12 extract-init-cublas-move.py run
    uv run --python 3.12 extract-init-cublas-move.py verify
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

ID = "extract-init-cublas-move"
SUBJECT = "Move init_cublas to utils.common (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-init-cublas-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    common = wt / "python/sglang/srt/utils/common.py"

    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="init_cublas"
    )
    method_text = cut_lines(mr, start, end)
    # Strip the ``    @staticmethod\n`` decorator line; the rest is the
    # function body at 4-space indent — dedent to module level.
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod", f"first line not @staticmethod: {lines[0]!r}"
    function_text = dedent_method_to_function("".join(lines[1:]))
    append_to_file(common, function_text)

    text = mr.read_text()
    text = replace_call_site(text, old="ModelRunner.init_cublas()", new="init_cublas()")
    text = add_to_grouped_import(
        text, anchor_name="init_custom_process_group", new_line="    init_cublas,"
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
