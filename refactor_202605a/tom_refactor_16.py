#!/usr/bin/env python3
"""Reproducible transform: inject ParallelState into ProfilerV2 (ProfileManager
+ _ProfilerConcreteBase). Renames self.tp_rank → self.ps.tp_rank only. The
dead `getattr(self, "dp_size", 1)` block in stop() is preserved verbatim
(separate PR fixes the underlying copy-paste bug).

Run from the repo root:
    python3 /tmp/transform_profiler_v2_inject_ps.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/15"
TARGET_COMMIT = "tom_refactor/16"


def transform(dir_root: Path) -> None:
    pu = dir_root / "python/sglang/srt/utils/profile_utils.py"
    text = pu.read_text()

    OLD_IMPORT = "from sglang.srt.managers.io_struct import ProfileReqOutput\n"
    NEW_IMPORT = (
        "from sglang.srt.distributed.parallel_state_wrapper import ParallelState\n"
        "from sglang.srt.managers.io_struct import ProfileReqOutput\n"
    )
    assert OLD_IMPORT in text, "io_struct anchor import not found"
    text = text.replace(OLD_IMPORT, NEW_IMPORT)

    # ProfileManager.__init__: drop tp_rank/gpu_id params, gain ps.
    text = text.replace(
        "def __init__(self, tp_rank: int, cpu_group, gpu_id: int):",
        "def __init__(self, ps: ParallelState, cpu_group):",
    )
    # gpu_id read in ProfileManager.__init__ body (unique to that line).
    text = text.replace(
        "self.first_rank_in_node = gpu_id == get_global_server_args().base_gpu_id",
        "self.first_rank_in_node = ps.gpu_id == get_global_server_args().base_gpu_id",
    )

    # _ProfilerBase.create() kwarg in ProfileManager._do_start.
    text = text.replace(
        "tp_rank=self.tp_rank,",
        "ps=self.ps,",
    )

    # _ProfilerConcreteBase.__init__: tp_rank: int param → ps: ParallelState.
    # The 8-space indent + trailing comma make this fragment unique.
    text = text.replace(
        "        tp_rank: int,\n",
        "        ps: ParallelState,\n",
    )

    # Field-store assignment present in BOTH ProfileManager and
    # _ProfilerConcreteBase bodies — both rename to self.ps = ps.
    text = text.replace(
        "        self.tp_rank = tp_rank\n",
        "        self.ps = ps\n",
    )

    # Remaining live self.tp_rank reads (filename construction + barrier guards).
    # Each fragment is unique within the file.
    fragment_replacements = [
        ('f"TP-{self.tp_rank}"', 'f"TP-{self.ps.tp_rank}"'),
        ('f"-TP-{self.tp_rank}-memory"', 'f"-TP-{self.ps.tp_rank}-memory"'),
        ('"rpd-" + str(time.time()) + f"-TP-{self.tp_rank}"', '"rpd-" + str(time.time()) + f"-TP-{self.ps.tp_rank}"'),
        ("if self.tp_rank == 0:", "if self.ps.tp_rank == 0:"),
    ]
    for old, new in fragment_replacements:
        assert old in text, f"fragment not found: {old!r}"
        text = text.replace(old, new)

    pu.write_text(text)

    # Caller in scheduler_profiler_mixin.init_profiler: rename one kwarg, drop another.
    spm = dir_root / "python/sglang/srt/managers/scheduler_profiler_mixin.py"
    text = spm.read_text()
    text = text.replace(
        "                tp_rank=self.ps.tp_rank,\n",
        "                ps=self.ps,\n",
    )
    text = text.replace(
        "                gpu_id=self.ps.gpu_id,\n",
        "",
    )
    spm.write_text(text)

    git_add_and_commit(
        "Inject ParallelState into ProfilerV2",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
