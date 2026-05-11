#!/usr/bin/env python3
"""Move stage for extract-prealloc-symm-pool (MECH_COMMIT_SPLIT §"二段式"):

Pure cut+paste into ``distributed/device_communicators/pynccl_allocator.py``.
Body byte-equivalent.
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
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-prealloc-symm-pool-move"
SUBJECT = "Move prealloc_symmetric_memory_pool to pynccl_allocator (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-prealloc-symm-pool-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    allocator = wt / "python/sglang/srt/distributed/device_communicators/pynccl_allocator.py"

    start, end = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="prealloc_symmetric_memory_pool",
    )
    method_text = cut_lines(mr, start, end)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    function_text = dedent_method_to_function("".join(lines[1:]))

    a_text = allocator.read_text()
    if "\nlogger = logging.getLogger(__name__)\n" not in a_text:
        a_text = insert_after(
            a_text,
            anchor="_symm_mem_logger = logging.getLogger(__name__)\n",
            addition="logger = logging.getLogger(__name__)\n",
        )
        allocator.write_text(a_text)
    append_to_file(allocator, function_text)

    text = mr.read_text()
    text = replace_call_site(
        text,
        old="ModelRunner.prealloc_symmetric_memory_pool(",
        new="prealloc_symmetric_memory_pool(",
    )
    text = replace_call_site(
        text,
        old="    use_symmetric_memory,\n)\n",
        new="    prealloc_symmetric_memory_pool,\n    use_symmetric_memory,\n)\n",
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
