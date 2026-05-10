#!/usr/bin/env python3
"""Reproducible transform: bundle Scheduler rank/size fields into a frozen
ParallelState dataclass, computed inside Scheduler.__init__ (signature
unchanged). Adds attn_dp_size as a real field by extending
compute_dp_attention_world_info to return a 4-tuple.

Run from the repo root:
    python3 /tmp/transform_scheduler_ps_refactor.py
"""

import re
import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/14"
TARGET_COMMIT = "tom_refactor/15"

PARALLEL_STATE_WRAPPER = '''from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True, kw_only=True)
class ParallelState:
    tp_rank: int
    tp_size: int
    pp_rank: int
    pp_size: int
    dp_rank: Optional[int]
    dp_size: int
    attn_tp_rank: int
    attn_tp_size: int
    attn_cp_rank: int
    attn_cp_size: int
    attn_dp_rank: int
    attn_dp_size: int
    moe_ep_rank: int
    moe_ep_size: int
    moe_dp_rank: Optional[int]
    moe_dp_size: int
    gpu_id: int
'''

PARALLEL_STATE_TEST = '''import dataclasses
import unittest

from sglang.srt.distributed.parallel_state_wrapper import ParallelState
from sglang.test.ci.ci_register import register_cpu_ci
from sglang.test.test_utils import CustomTestCase

register_cpu_ci(est_time=5, suite="stage-a-test-cpu")


def _make_default(**overrides):
    base = dict(
        tp_rank=0,
        tp_size=1,
        pp_rank=0,
        pp_size=1,
        dp_rank=None,
        dp_size=1,
        attn_tp_rank=0,
        attn_tp_size=1,
        attn_cp_rank=0,
        attn_cp_size=1,
        attn_dp_rank=0,
        attn_dp_size=1,
        moe_ep_rank=0,
        moe_ep_size=1,
        moe_dp_rank=None,
        moe_dp_size=1,
        gpu_id=0,
    )
    base.update(overrides)
    return ParallelState(**base)


class TestParallelStateConstruction(CustomTestCase):
    def test_minimal_single_rank(self):
        state = _make_default()
        self.assertEqual(state.tp_rank, 0)
        self.assertEqual(state.tp_size, 1)
        self.assertEqual(state.gpu_id, 0)
        self.assertIsNone(state.dp_rank)
        self.assertIsNone(state.moe_dp_rank)

    def test_multi_rank_full(self):
        state = _make_default(
            tp_rank=3,
            tp_size=8,
            pp_rank=1,
            pp_size=2,
            dp_rank=2,
            dp_size=4,
            attn_tp_rank=3,
            attn_tp_size=4,
            attn_cp_rank=0,
            attn_cp_size=1,
            attn_dp_rank=2,
            attn_dp_size=2,
            moe_ep_rank=1,
            moe_ep_size=2,
            moe_dp_rank=2,
            moe_dp_size=4,
            gpu_id=3,
        )
        self.assertEqual(state.tp_rank, 3)
        self.assertEqual(state.dp_rank, 2)
        self.assertEqual(state.moe_dp_rank, 2)
        self.assertEqual(state.attn_dp_size, 2)


class TestParallelStateImmutability(CustomTestCase):
    def test_frozen_rejects_mutation(self):
        state = _make_default()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            state.tp_rank = 9  # type: ignore[misc]

    def test_slots_rejects_new_attribute(self):
        state = _make_default()
        with self.assertRaises((AttributeError, dataclasses.FrozenInstanceError)):
            state.extra_field = 1  # type: ignore[attr-defined]


class TestParallelStateKeywordOnly(CustomTestCase):
    def test_positional_args_rejected(self):
        with self.assertRaises(TypeError):
            ParallelState(0, 1)  # type: ignore[call-arg]


if __name__ == "__main__":
    unittest.main()
'''

BUNDLED_FIELDS = [
    "tp_rank", "tp_size",
    "pp_rank", "pp_size",
    "dp_rank", "dp_size",
    "attn_tp_rank", "attn_tp_size",
    "attn_cp_rank", "attn_cp_size",
    "attn_dp_rank", "attn_dp_size",
    "moe_ep_rank", "moe_ep_size",
    "moe_dp_rank", "moe_dp_size",
    "gpu_id",
]

SELF_PATTERN = re.compile(r"\bself\.(" + "|".join(BUNDLED_FIELDS) + r")\b")
SCHEDULER_PATTERN = re.compile(
    r"\bself\.scheduler\.(" + "|".join(BUNDLED_FIELDS) + r")\b"
)


def transform(dir_root: Path) -> None:
    (dir_root / "python/sglang/srt/distributed/parallel_state_wrapper.py").write_text(
        PARALLEL_STATE_WRAPPER
    )
    (dir_root / "test/registered/unit/test_parallel_state_wrapper.py").write_text(
        PARALLEL_STATE_TEST
    )

    dp_attention = dir_root / "python/sglang/srt/layers/dp_attention.py"
    text = dp_attention.read_text()
    text = text.replace(
        "    return attn_tp_rank, attn_tp_size, attn_dp_rank\n",
        "    return attn_tp_rank, attn_tp_size, attn_dp_rank, attn_dp_size\n",
    )
    text = text.replace(
        "_, _, _ATTN_DP_RANK = compute_dp_attention_world_info(",
        "_, _, _ATTN_DP_RANK, _ = compute_dp_attention_world_info(",
    )
    dp_attention.write_text(text)

    dpc = dir_root / "python/sglang/srt/managers/data_parallel_controller.py"
    text = dpc.read_text()
    text = text.replace(
        "_, _, dp_rank = compute_dp_attention_world_info(",
        "_, _, dp_rank, _ = compute_dp_attention_world_info(",
    )
    dpc.write_text(text)

    ray_dpc = dir_root / "python/sglang/srt/ray/data_parallel_controller.py"
    text = ray_dpc.read_text()
    text = text.replace(
        "_, _, actual_dp_rank = compute_dp_attention_world_info(",
        "_, _, actual_dp_rank, _ = compute_dp_attention_world_info(",
    )
    ray_dpc.write_text(text)

    sched = dir_root / "python/sglang/srt/managers/scheduler.py"
    text = sched.read_text()

    text = text.replace(
        "from sglang.srt.distributed.parallel_state import get_tp_group\n",
        "from sglang.srt.distributed.parallel_state import get_tp_group\n"
        "from sglang.srt.distributed.parallel_state_wrapper import ParallelState\n",
    )

    for line in (
        '        self.tp_rank = tp_rank\n',
        '        self.moe_ep_rank = moe_ep_rank\n',
        '        self.pp_rank = pp_rank\n',
        '        self.attn_cp_rank = attn_cp_rank\n',
        '        self.attn_cp_size = server_args.attn_cp_size\n',
        '        self.moe_dp_rank = moe_dp_rank\n',
        '        self.moe_dp_size = server_args.moe_dp_size\n',
        '        self.dp_rank = dp_rank\n',
        '        self.tp_size = server_args.tp_size\n',
        '        self.moe_ep_size = server_args.ep_size\n',
        '        self.pp_size = server_args.pp_size\n',
        '        self.dp_size = server_args.dp_size\n',
        '        self.gpu_id = gpu_id\n',
    ):
        assert text.count(line) == 1, f"line not unique: {line!r}"
        text = text.replace(line, "")

    # Promote LHS from `self.attn_tp_*` 3-tuple to local 4-tuple (extra attn_dp_size).
    text = text.replace(
        "self.attn_tp_rank, self.attn_tp_size, self.attn_dp_rank = (",
        "attn_tp_rank, attn_tp_size, attn_dp_rank, attn_dp_size = (",
    )

    # Switch the call's args from `self.X` (about to be removed) to constructor
    # locals / `server_args.X`. The 4-line clump is unique to this call site.
    text = text.replace(
        "                self.tp_rank,\n"
        "                self.tp_size,\n"
        "                self.dp_size,\n"
        "                self.attn_cp_size,\n",
        "                tp_rank,\n"
        "                server_args.tp_size,\n"
        "                server_args.dp_size,\n"
        "                server_args.attn_cp_size,\n",
    )

    # Insert the ParallelState construction directly after the call's closing
    # ``)``. Anchor on `# Init model configs` (uniquely 2 lines below the
    # insertion point) so we don't depend on the long preceding context.
    PARALLEL_STATE_CONSTRUCTION = (
        "        self.ps = ParallelState(\n"
        "            tp_rank=tp_rank,\n"
        "            tp_size=server_args.tp_size,\n"
        "            pp_rank=pp_rank,\n"
        "            pp_size=server_args.pp_size,\n"
        "            dp_rank=dp_rank,\n"
        "            dp_size=server_args.dp_size,\n"
        "            attn_tp_rank=attn_tp_rank,\n"
        "            attn_tp_size=attn_tp_size,\n"
        "            attn_cp_rank=attn_cp_rank,\n"
        "            attn_cp_size=server_args.attn_cp_size,\n"
        "            attn_dp_rank=attn_dp_rank,\n"
        "            attn_dp_size=attn_dp_size,\n"
        "            moe_ep_rank=moe_ep_rank,\n"
        "            moe_ep_size=server_args.ep_size,\n"
        "            moe_dp_rank=moe_dp_rank,\n"
        "            moe_dp_size=server_args.moe_dp_size,\n"
        "            gpu_id=gpu_id,\n"
        "        )\n"
    )
    ANCHOR = "        )\n\n        # Init model configs\n"
    assert ANCHOR in text, "anchor before `# Init model configs` not found"
    text = text.replace(ANCHOR, "        )\n" + PARALLEL_STATE_CONSTRUCTION + "\n        # Init model configs\n")

    text = SELF_PATTERN.sub(r"self.ps.\1", text)
    sched.write_text(text)

    mixin_files = [
        "python/sglang/srt/managers/scheduler_dp_attn_mixin.py",
        "python/sglang/srt/managers/scheduler_output_processor_mixin.py",
        "python/sglang/srt/managers/scheduler_pp_mixin.py",
        "python/sglang/srt/managers/scheduler_profiler_mixin.py",
        "python/sglang/srt/observability/scheduler_metrics_mixin.py",
    ]
    for rel in mixin_files:
        path = dir_root / rel
        text = path.read_text()
        text = SELF_PATTERN.sub(r"self.ps.\1", text)
        path.write_text(text)

    # Restore MLPSyncBatchInfo (a standalone @dataclass at scheduler_dp_attn_mixin.py:24)
    # whose own fields `dp_size` / `tp_size` were over-rewritten by SELF_PATTERN. The
    # class has no `ps` attribute — the rewrite would AttributeError at runtime.
    dp_attn = dir_root / "python/sglang/srt/managers/scheduler_dp_attn_mixin.py"
    text = dp_attn.read_text()
    for old, new in [
        (
            "(self.ps.dp_size, self.ps.tp_size * self.cp_size, 6),",
            "(self.dp_size, self.tp_size * self.cp_size, 6),",
        ),
        (
            "self.ps.dp_size * self.ps.tp_size * self.cp_size, 6",
            "self.dp_size * self.tp_size * self.cp_size, 6",
        ),
    ]:
        assert old in text, f"MLPSyncBatchInfo restore: {old!r} not found"
        text = text.replace(old, new)
    dp_attn.write_text(text)

    prof = dir_root / "python/sglang/srt/managers/scheduler_profiler_mixin.py"
    text = prof.read_text()
    fragment_replacements = [
        ('getattr(self, "dp_size", 1)', "self.ps.dp_size"),
        ('getattr(self, "dp_rank", 0)', "self.ps.dp_rank"),
        ('getattr(self, "pp_size", 1)', "self.ps.pp_size"),
        ('getattr(self, "pp_rank", 0)', "self.ps.pp_rank"),
        ('getattr(self, "moe_ep_size", 1)', "self.ps.moe_ep_size"),
        ('getattr(self, "moe_ep_rank", 0)', "self.ps.moe_ep_rank"),
        ("getattr(self, 'dp_rank', 0)", "self.ps.dp_rank"),
        ("getattr(self, 'pp_rank', 0)", "self.ps.pp_rank"),
        ("getattr(self, 'moe_ep_rank', 0)", "self.ps.moe_ep_rank"),
    ]
    for old, new in fragment_replacements:
        text = text.replace(old, new)
    prof.write_text(text)

    external_files = [
        "python/sglang/srt/disaggregation/prefill.py",
        "python/sglang/srt/disaggregation/decode.py",
        "python/sglang/srt/ray/scheduler_actor.py",
    ]
    for rel in external_files:
        path = dir_root / rel
        text = path.read_text()
        text = SCHEDULER_PATTERN.sub(r"self.scheduler.ps.\1", text)
        path.write_text(text)

    git_add_and_commit(
        "Bundle Scheduler rank/size fields into a frozen ParallelState",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
