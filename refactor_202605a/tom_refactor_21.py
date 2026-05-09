#!/usr/bin/env python3
"""Reproducible transform: inline `ModelRunner.max_token_pool_size` property at
its sole consumer in `tp_worker.py`. Strict-minimal mechanical move:
- Delete the @property.
- Inline the body at the single call site (tp_worker.py).

Run from the repo root:
    python3 /tmp/transform_inline_max_token_pool_size.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/20"
TARGET_COMMIT = "tom_refactor/21"


def transform(dir_root: Path) -> None:
    # --- Step 1: Delete the property in model_runner.py ---
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()
    old = (
        "    @property\n"
        "    def max_token_pool_size(self):\n"
        '        """Return the max token pool size considering hybrid swa settings."""\n'
        "        if self.is_hybrid_swa:\n"
        "            return self.full_max_total_num_tokens\n"
        "        else:\n"
        "            return self.max_total_num_tokens\n\n"
    )
    assert old in text, "max_token_pool_size property not found"
    text = text.replace(old, "")
    mr.write_text(text)

    # --- Step 2: Inline at the sole consumer in tp_worker.py ---
    tp = dir_root / "python/sglang/srt/managers/tp_worker.py"
    text = tp.read_text()
    old = (
        "        self.max_req_len = min(\n"
        "            self.model_config.context_len - 1,\n"
        "            self.model_runner.max_token_pool_size - 1,\n"
        "        )"
    )
    new = (
        "        mr = self.model_runner\n"
        "        pool_tokens = (\n"
        "            mr.full_max_total_num_tokens if mr.is_hybrid_swa else mr.max_total_num_tokens\n"
        "        )\n"
        "        self.max_req_len = min(\n"
        "            self.model_config.context_len - 1,\n"
        "            pool_tokens - 1,\n"
        "        )"
    )
    assert old in text, "tp_worker max_token_pool_size callsite not found"
    text = text.replace(old, new)
    tp.write_text(text)

    git_add_and_commit(
        "Inline max_token_pool_size property at sole consumer",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
