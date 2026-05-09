#!/usr/bin/env python3
"""Reproducible transform: fix V2 trace filename collisions when DP/PP/EP
parallelism is enabled. Restores intent that was dropped to a copy-paste bug —
fields gating the original `getattr(self, "dp_size", 1) > 1` chain were never
forwarded into _ProfilerConcreteBase, so the suffixes were never appended.
With ps now injected (PR /15 + /16), convert each fragment to direct ps access.

Run from the repo root:
    python3 /tmp/transform_profiler_v2_fix_dp_pp_ep_suffixes.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/16"
TARGET_COMMIT = "tom_refactor/17"


def transform(dir_root: Path) -> None:
    pu = dir_root / "python/sglang/srt/utils/profile_utils.py"
    text = pu.read_text()

    fragment_replacements = [
        ('getattr(self, "dp_size", 1)', "self.ps.dp_size"),
        ('getattr(self, "pp_size", 1)', "self.ps.pp_size"),
        ('getattr(self, "moe_ep_size", 1)', "self.ps.moe_ep_size"),
        ("getattr(self, 'dp_rank', 0)", "self.ps.dp_rank"),
        ("getattr(self, 'pp_rank', 0)", "self.ps.pp_rank"),
        ("getattr(self, 'moe_ep_rank', 0)", "self.ps.moe_ep_rank"),
    ]
    for old, new in fragment_replacements:
        assert old in text, f"fragment not found: {old!r}"
        text = text.replace(old, new)

    pu.write_text(text)

    git_add_and_commit(
        "Fix V2 trace filename collisions when DP/PP/EP enabled",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
