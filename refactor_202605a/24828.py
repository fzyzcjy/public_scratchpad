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

    OLD_PM_INIT = (
        "    def __init__(self, tp_rank: int, cpu_group, gpu_id: int):\n"
        "        self.stage_based_trigger = _StageBasedTrigger(\n"
        "            on_start=self._do_start,\n"
        "            on_stop=self._do_stop,\n"
        "        )\n"
        "        self.tp_rank = tp_rank\n"
        "        self.cpu_group = cpu_group\n"
        "        self.first_rank_in_node = gpu_id == get_global_server_args().base_gpu_id\n"
    )
    NEW_PM_INIT = (
        "    def __init__(self, ps: ParallelState, cpu_group):\n"
        "        self.stage_based_trigger = _StageBasedTrigger(\n"
        "            on_start=self._do_start,\n"
        "            on_stop=self._do_stop,\n"
        "        )\n"
        "        self.ps = ps\n"
        "        self.cpu_group = cpu_group\n"
        "        self.first_rank_in_node = ps.gpu_id == get_global_server_args().base_gpu_id\n"
    )
    assert OLD_PM_INIT in text, "ProfileManager.__init__ not found verbatim"
    text = text.replace(OLD_PM_INIT, NEW_PM_INIT)

    OLD_DO_START_KW = (
        "        self.profiler = _ProfilerBase.create(\n"
        "            **self.profiler_kwargs,\n"
        "            tp_rank=self.tp_rank,\n"
        "            cpu_group=self.cpu_group,\n"
        "            first_rank_in_node=self.first_rank_in_node,\n"
        "            output_suffix=f\"-{stage}\" if stage else \"\",\n"
        "        )\n"
    )
    NEW_DO_START_KW = (
        "        self.profiler = _ProfilerBase.create(\n"
        "            **self.profiler_kwargs,\n"
        "            ps=self.ps,\n"
        "            cpu_group=self.cpu_group,\n"
        "            first_rank_in_node=self.first_rank_in_node,\n"
        "            output_suffix=f\"-{stage}\" if stage else \"\",\n"
        "        )\n"
    )
    assert OLD_DO_START_KW in text, "_do_start kwargs not found verbatim"
    text = text.replace(OLD_DO_START_KW, NEW_DO_START_KW)

    # Replace tp_rank parameter with ps in _ProfilerConcreteBase.__init__.
    text = text.replace(
        "        profile_id: str,\n        tp_rank: int,\n",
        "        profile_id: str,\n        ps: ParallelState,\n",
    )
    text = text.replace(
        "        self.profile_id = profile_id\n        self.tp_rank = tp_rank\n",
        "        self.profile_id = profile_id\n        self.ps = ps\n",
    )

    # Rename the live self.tp_rank usages. Each fragment is unique.
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

    spm = dir_root / "python/sglang/srt/managers/scheduler_profiler_mixin.py"
    text = spm.read_text()
    OLD_CALLER = (
        "            self._profile_manager = ProfileManager(\n"
        "                tp_rank=self.ps.tp_rank,\n"
        "                cpu_group=self.dp_tp_cpu_group,\n"
        "                gpu_id=self.ps.gpu_id,\n"
        "            )\n"
    )
    NEW_CALLER = (
        "            self._profile_manager = ProfileManager(\n"
        "                ps=self.ps,\n"
        "                cpu_group=self.dp_tp_cpu_group,\n"
        "            )\n"
    )
    assert OLD_CALLER in text, "ProfileManager caller not found verbatim"
    text = text.replace(OLD_CALLER, NEW_CALLER)
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
