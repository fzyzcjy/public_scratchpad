#!/usr/bin/env python3
"""Mechanical move for ``migrate-dp-attn-mixin``: true cut + paste from
``scheduler_dp_attn_mixin.py`` into
``scheduler_components/dp_attn_adapter.py``.

Cuts (in source order, top-down):
  - module-level ``MLPSyncBatchInfo`` ``@dataclass`` (verbatim)
  - module-level ``_update_gather_batch`` free function (verbatim)
  - module-level ``prepare_mlp_sync_batch_raw`` free function (verbatim)
  - 3 ``@staticmethod`` methods (``prepare_mlp_sync_batch`` /
    ``maybe_prepare_mlp_sync_batch`` / ``get_idle_batch``) — drop decorator
    + simplify ``self: "SchedulerDPAttnAdapter"`` → bare ``self``; body bytes
    unchanged.

Builds the target file:
  HEADER imports (final form) + MLPSyncBatchInfo + _update_gather_batch +
  prepare_mlp_sync_batch_raw + (existing) SchedulerDPAttnAdapter skeleton
  with the 3 methods appended to its body.

Then unlinks the source mixin, drops SchedulerDPAttnMixin from the
Scheduler inheritance + import, and updates callers
``self.<method>(self.dp_attn_adapter, ...)`` →
``self.dp_attn_adapter.<method>(...)`` (pure prefix transformation).
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
    cut_lines,
    find_class_lines,
    find_function_lines,
    find_method_lines,
    replace_call_site,
    rewrite_method_call_site,
)
from _runner import run_pr

ID = "migrate-dp-attn-mixin-move"
SUBJECT = "Move DP-attention adapter methods to SchedulerDPAttnAdapter"
BODY = """\
Mechanical cut + paste for the ``migrate-dp-attn-mixin`` mech move.

Cut ``prepare_mlp_sync_batch`` / ``maybe_prepare_mlp_sync_batch`` /
``get_idle_batch`` (@staticmethods after prep) from
``scheduler_dp_attn_mixin.py`` and paste them into ``SchedulerDPAttnAdapter``
class body in ``scheduler_components/dp_attn_adapter.py``.

Module-level ``MLPSyncBatchInfo`` dataclass + ``_update_gather_batch`` +
``prepare_mlp_sync_batch_raw`` are cut verbatim from the old mixin and
prepended into the new target module above the adapter class. The source
file is deleted, the ``SchedulerDPAttnMixin`` entry is dropped from the
Scheduler inheritance list, and its ``from`` import is dropped from
``scheduler.py``.

Method bodies otherwise byte-identical. ``@staticmethod`` decorators
dropped; ``self: "SchedulerDPAttnAdapter"`` annotation simplified to bare
``self``.

All callers updated:
  ``self.maybe_prepare_mlp_sync_batch(self.dp_attn_adapter, batch, ...)`` →
  ``self.dp_attn_adapter.maybe_prepare_mlp_sync_batch(batch, ...)``
(pure prefix transformation).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Final imports for the target module. These match the post-move state and
# replace the minimal skeleton header the prep commit wrote.
TARGET_FILE_HEADER = '''\
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Optional

import torch

from sglang.srt.batch_overlap.two_batch_overlap import TboDPAttentionPreparer
from sglang.srt.distributed.parallel_state import get_tp_group
from sglang.srt.environ import envs
from sglang.srt.managers.schedule_batch import ScheduleBatch
from sglang.srt.model_executor.forward_batch_info import ForwardMode
from sglang.srt.observability.metrics_collector import DPCooperationInfo
from sglang.srt.utils.common import require_mlp_tp_gather

if TYPE_CHECKING:
    from sglang.srt.distributed.parallel_state import GroupCoordinator


_ENABLE_METRICS_DP_ATTENTION = envs.SGLANG_ENABLE_METRICS_DP_ATTENTION.get()
'''


def _strip_staticmethod_typeflip(method_text: str) -> str:
    """Drop ``@staticmethod`` decorator and simplify the
    ``self: "SchedulerDPAttnAdapter"`` annotation back to bare ``self``.
    Body bytes otherwise unchanged.
    """
    text = method_text.replace("    @staticmethod\n", "", 1)
    text = text.replace('self: "SchedulerDPAttnAdapter"', "self")
    return text


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_dp_attn_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pp = wt / "python/sglang/srt/managers/scheduler_pp_mixin.py"
    prefill = wt / "python/sglang/srt/disaggregation/prefill.py"
    decode = wt / "python/sglang/srt/disaggregation/decode.py"
    test_chunked = wt / "test/registered/unit/managers/test_scheduler_chunked_req_gate.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/dp_attn_adapter.py"

    # 1. Cut module-level items (bottom-up so earlier line offsets stay valid).
    mtext = mixin.read_text()
    fn_s, fn_e = find_function_lines(mtext, function_name="prepare_mlp_sync_batch_raw")
    prepare_raw_block = cut_lines(mixin, fn_s, fn_e)

    mtext = mixin.read_text()
    fn_s, fn_e = find_function_lines(mtext, function_name="_update_gather_batch")
    update_gather_block = cut_lines(mixin, fn_s, fn_e)

    mtext = mixin.read_text()
    cls_s, cls_e = find_class_lines(mtext, class_name="MLPSyncBatchInfo")
    mlp_info_block = cut_lines(mixin, cls_s, cls_e)

    # 2. Cut the 3 @staticmethods (bottom-up).
    method_blocks = []
    for name in ("get_idle_batch", "maybe_prepare_mlp_sync_batch", "prepare_mlp_sync_batch"):
        mtext = mixin.read_text()
        m_s, m_e = find_method_lines(
            mtext, class_name="SchedulerDPAttnMixin", method_name=name
        )
        block = cut_lines(mixin, m_s, m_e)
        method_blocks.append(_strip_staticmethod_typeflip(block))
    method_blocks.reverse()  # restore source order

    # 3. Build the final target file: HEADER + MLPSyncBatchInfo + 2 free fns
    #    + (existing skeleton class body, methods appended).
    existing = target.read_text()
    # The prep wrote: "from __future__ import annotations\n\n@dataclass(...)\nclass SchedulerDPAttnAdapter:..."
    # Find where the dataclass decorator + class begins so we keep the
    # skeleton body verbatim (incl. the decorator) while replacing the header.
    cls_marker = "@dataclass(kw_only=True, slots=True, frozen=True)\nclass SchedulerDPAttnAdapter:"
    if cls_marker not in existing:
        raise RuntimeError("SchedulerDPAttnAdapter skeleton not found in target")
    skeleton_class_body = existing[existing.index(cls_marker):].rstrip() + "\n"

    new_target = (
        TARGET_FILE_HEADER
        + "\n\n"
        + mlp_info_block.rstrip()
        + "\n\n\n"
        + update_gather_block.rstrip()
        + "\n\n\n"
        + prepare_raw_block.rstrip()
        + "\n\n\n"
        + skeleton_class_body.rstrip()
        + "\n\n"
        + "".join(method_blocks).rstrip()
        + "\n"
    )
    target.write_text(new_target)

    # 4. Delete the old mixin file.
    mixin.unlink()

    # 5. Update Scheduler: drop mixin import + remove from inheritance list.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="from sglang.srt.managers.scheduler_dp_attn_mixin import SchedulerDPAttnMixin\n",
        new="",
    )
    text = replace_call_site(
        text,
        old="    SchedulerDPAttnMixin,\n",
        new="",
    )
    sched.write_text(text)  # persist import + inheritance drop before regex pass

    # 6. Caller rewrites in scheduler.py / pp_mixin / prefill / decode: pure
    #    ``self.<method>(self.dp_attn_adapter, ...)`` →
    #    ``self.dp_attn_adapter.<method>(...)`` (regex handles single-line +
    #    multi-line black-formatted forms).
    for f in (sched, pp, prefill, decode):
        ftext = f.read_text()
        for method in (
            "maybe_prepare_mlp_sync_batch",
            "prepare_mlp_sync_batch",
            "get_idle_batch",
        ):
            try:
                ftext = rewrite_method_call_site(
                    ftext, method_name=method, target_attr="dp_attn_adapter"
                )
            except ValueError:
                pass  # not all methods called in every file
        f.write_text(ftext)

    # 7. Test fixture: previously mocked ``s.maybe_prepare_mlp_sync_batch``
    #    directly; now the callsite is
    #    ``s.dp_attn_adapter.maybe_prepare_mlp_sync_batch``.
    test_text = test_chunked.read_text()
    test_text = replace_call_site(
        test_text,
        old="    s.maybe_prepare_mlp_sync_batch = MagicMock(side_effect=lambda batch, **_: batch)\n",
        new="    s.dp_attn_adapter = MagicMock()\n"
        "    s.dp_attn_adapter.maybe_prepare_mlp_sync_batch = MagicMock(side_effect=lambda batch, **_: batch)\n",
    )
    test_chunked.write_text(test_text)

    # 8. External free-function import: bench_one_batch imports
    #    ``prepare_mlp_sync_batch_raw`` from the now-retired mixin path.
    bench = wt / "python/sglang/bench_one_batch.py"
    btext = bench.read_text()
    btext = replace_call_site(
        btext,
        old="from sglang.srt.managers.scheduler_dp_attn_mixin import prepare_mlp_sync_batch_raw\n",
        new="from sglang.srt.managers.scheduler_components.dp_attn_adapter import prepare_mlp_sync_batch_raw\n",
    )
    bench.write_text(btext)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
