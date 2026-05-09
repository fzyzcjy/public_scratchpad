#!/usr/bin/env python3
"""Reproducible transform: extract `ModelRunner.init_cublas` to a free function
in `sglang.srt.utils.common`. The original method already had a docstring; the
new free function carries the same docstring.

Run from the repo root:
    python3 /tmp/transform_init_cublas.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/17"
TARGET_COMMIT = "tom_refactor/18"


def transform(dir_root: Path) -> None:
    common = dir_root / "python/sglang/srt/utils/common.py"
    text = common.read_text()
    text = text.rstrip() + '\n\n\ndef init_cublas() -> None:\n    """We need to run a small matmul to init cublas. Otherwise, it will raise some errors later."""\n    dtype = torch.float16\n    device = "cuda"\n    a = torch.ones((16, 16), dtype=dtype, device=device)\n    b = torch.ones((16, 16), dtype=dtype, device=device)\n    a @ b\n'
    common.write_text(text)

    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    old_method = (
        '    def init_cublas(self):\n'
        '        """We need to run a small matmul to init cublas. Otherwise, it will raise some errors later."""\n'
        '        dtype = torch.float16\n'
        '        device = "cuda"\n'
        '        a = torch.ones((16, 16), dtype=dtype, device=device)\n'
        '        b = torch.ones((16, 16), dtype=dtype, device=device)\n'
        '        c = a @ b\n'
        '        return c\n\n'
    )
    assert old_method in text, "init_cublas method not found"
    text = text.replace(old_method, "")

    text = text.replace("self.init_cublas()", "init_cublas()")

    text = text.replace(
        "    get_cpu_ids_by_node,\n    init_custom_process_group,",
        "    get_cpu_ids_by_node,\n    init_cublas,\n    init_custom_process_group,",
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
