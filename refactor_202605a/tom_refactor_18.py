#!/usr/bin/env python3
"""Cut `init_cublas` method from ModelRunner; paste as a free function in
`utils/common.py`. Update the sole caller and add an import.

Run from the repo root:
    python3 tom_refactor_18.py
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import (
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/17"
TARGET_COMMIT = "tom_refactor/18"


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    common = dir_root / "python/sglang/srt/utils/common.py"

    start, end = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="init_cublas")
    method_text = cut_lines(mr, start, end)
    function_text = dedent_method_to_function(method_text).replace(
        "def init_cublas(self):", "def init_cublas():"
    )
    append_to_file(common, function_text)

    text = mr.read_text()
    text = text.replace("self.init_cublas()", "init_cublas()")
    text = text.replace(
        "    init_custom_process_group,\n",
        "    init_cublas,\n    init_custom_process_group,\n",
    )
    mr.write_text(text)

    git_add_and_commit(
        "Extract init_cublas to free function in utils.common",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
