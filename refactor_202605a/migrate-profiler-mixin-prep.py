#!/usr/bin/env python3
"""Inplace prep for ``migrate-profiler-mixin``: create the
``SchedulerProfilerManager`` class skeleton at
``scheduler_components/profiler_manager.py`` (ctor with all 19 mutable
runtime fields inlined from ``init_profiler``, no methods yet), instantiate
in ``Scheduler.__init__`` in place of the ``self.init_profiler()`` call,
remove the original ``init_profiler`` method from the mixin, apply privacy
flips (``init_profile`` / ``start_profile`` / ``stop_profile`` / ``profile``
→ ``_init_profile`` / ``_start_profile`` / ``_stop_profile`` / ``_profile``),
convert the 6 remaining methods to ``@staticmethod`` with
``self: "SchedulerProfilerManager"``, add ``forward_ct`` as a keyword on
``_init_profile`` / ``_profile_batch_predicate`` / ``_profile`` (R4 kwarg
add), and rewrite the 2 hot-path callers in ``scheduler.py``.

Method bodies byte-identical wrt the post-move state (modulo decorator +
the ``def foo(self: SchedulerProfilerManager, ...)`` → ``def foo(self, ...)``
signature simplification in the move commit).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import insert_after, replace_call_site
from _runner import run_pr

ID = "migrate-profiler-mixin-prep"
SUBJECT = "Build SchedulerProfilerManager skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``migrate-profiler-mixin`` mech move.

- Create ``scheduler_components/profiler_manager.py`` with an empty
  ``SchedulerProfilerManager`` class. Ctor takes 2 narrow typed kwargs
  (``ps`` / ``dp_tp_cpu_group``) and replicates the original
  ``init_profiler`` body inline (the ``init_profiler`` method itself is
  removed from the mixin).
- Instantiate ``self.profiler_manager = SchedulerProfilerManager(...)`` in
  ``Scheduler.__init__`` in place of the ``self.init_profiler()`` call.
- Privacy flip 4 methods (rename only, no body change): ``init_profile``
  → ``_init_profile`` etc.
- In the mixin file, convert 6 remaining methods (after init_profiler is
  removed) to ``@staticmethod`` with ``self: "SchedulerProfilerManager"``.
- ``forward_ct`` becomes a keyword-only parameter on ``_init_profile``,
  ``_profile_batch_predicate``, and ``_profile`` (R4 kwarg add). The
  ``self.forward_ct`` reads in those bodies become bare ``forward_ct``.
- The ``_profile`` body's two ``self._init_profile(...)`` invocations switch
  to keyword form and forward ``forward_ct``.
- Callers updated:
  - ``Scheduler.run_batch`` hot path: pass ``forward_ct=self.forward_ct`` to
    ``_profile_batch_predicate``.
  - ``Scheduler.init_request_dispatcher`` RPC tuple: wrap ``_profile`` in a
    lambda to inject ``forward_ct``.

The 6 methods stay inside ``SchedulerProfilerMixin`` in this commit;
physical cut + paste to ``SchedulerProfilerManager`` body happens in
``migrate-profiler-mixin-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


PROFILER_MANAGER_HEADER = '''from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from sglang.srt.environ import envs
from sglang.srt.utils.profile_utils import ProfileManager


class SchedulerProfilerManager:
    """torch profiler / RPD / cuda profiler lifecycle. Composition target on
    Scheduler (``self.profiler_manager``). Owns 19 mutable runtime fields."""

    def __init__(
        self,
        *,
        ps,
        dp_tp_cpu_group,
    ) -> None:
        self.ps = ps
        self.dp_tp_cpu_group = dp_tp_cpu_group

        if envs.SGLANG_PROFILE_V2.get():
            self._profile_manager = ProfileManager(
                ps=self.ps,
                cpu_group=self.dp_tp_cpu_group,
            )
            return

        self.torch_profiler = None
        self.torch_profiler_output_dir: Optional[Path] = None
        self.profiler_activities: Optional[List[str]] = None
        self.profile_id: Optional[str] = None

        self.profiler_start_forward_ct: Optional[int] = None
        self.profiler_target_forward_ct: Optional[int] = None

        self.profiler_prefill_ct: Optional[int] = None
        self.profiler_decode_ct: Optional[int] = None
        self.profiler_target_prefill_ct: Optional[int] = None
        self.profiler_target_decode_ct: Optional[int] = None

        self.profile_by_stage: bool = False
        self.profile_in_progress: bool = False
        self.merge_profiles = False

        # For ROCM
        self.rpd_profiler = None
'''


SCHEDULER_INIT_INSERT = """\
        self.profiler_manager = SchedulerProfilerManager(
            ps=self.ps,
            dp_tp_cpu_group=self.dp_tp_cpu_group,
        )
"""


# Original ``init_profiler`` method block (4-space indent, with trailing
# blank line) — remove from the mixin in prep so the body lives only in the
# new ctor.
INIT_PROFILER_METHOD_BLOCK = """\
    def init_profiler(self: Scheduler):
        if envs.SGLANG_PROFILE_V2.get():
            self._profile_manager = ProfileManager(
                ps=self.ps,
                cpu_group=self.dp_tp_cpu_group,
            )
            return

        self.torch_profiler = None
        self.torch_profiler_output_dir: Optional[Path] = None
        self.profiler_activities: Optional[List[str]] = None
        self.profile_id: Optional[str] = None

        self.profiler_start_forward_ct: Optional[int] = None
        self.profiler_target_forward_ct: Optional[int] = None

        self.profiler_prefill_ct: Optional[int] = None
        self.profiler_decode_ct: Optional[int] = None
        self.profiler_target_prefill_ct: Optional[int] = None
        self.profiler_target_decode_ct: Optional[int] = None

        self.profile_by_stage: bool = False
        self.profile_in_progress: bool = False
        self.merge_profiles = False

        # For ROCM
        self.rpd_profiler = None

"""


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_profiler_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/profiler_manager.py"
    test_profile = wt / "test/registered/unit/utils/test_profile_merger.py"

    # 1. Create new target file with empty class skeleton (ctor + fields only).
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    if not pkg_init.exists():
        pkg_init.write_text("")
    target.write_text(PROFILER_MANAGER_HEADER)

    # 2. In mixin file, drop the original init_profiler method (body now lives
    #    in the new ctor).
    text = mixin.read_text()
    if INIT_PROFILER_METHOD_BLOCK not in text:
        raise RuntimeError("init_profiler method block anchor mismatch")
    text = text.replace(INIT_PROFILER_METHOD_BLOCK, "")

    # 3. Privacy flips on the 4 method definitions (rename only).
    text = text.replace("def init_profile(\n", "def _init_profile(\n")
    text = text.replace("def start_profile(\n", "def _start_profile(\n")
    text = text.replace("def stop_profile(\n", "def _stop_profile(\n")
    text = text.replace(
        "def profile(self: Scheduler, recv_req: ProfileReq):",
        "def _profile(self: Scheduler, recv_req: ProfileReq):",
    )

    # 4. Internal cross-method calls — rewrite to the renamed forms.
    text = text.replace("self.init_profile(", "self._init_profile(")
    text = text.replace("self.start_profile(", "self._start_profile(")
    text = text.replace("self.stop_profile(", "self._stop_profile(")

    # 5. Convert 6 remaining methods to @staticmethod with type-flip self.
    #    Replace ``self: Scheduler`` → ``self: "SchedulerProfilerManager"`` and add
    #    @staticmethod decorator.
    text = text.replace(
        "    def _init_profile(\n        self: Scheduler,\n",
        '    @staticmethod\n    def _init_profile(\n        self: "SchedulerProfilerManager",\n',
    )
    text = text.replace(
        "    def _start_profile(\n        self: Scheduler, ",
        '    @staticmethod\n    def _start_profile(\n        self: "SchedulerProfilerManager", ',
    )
    text = text.replace(
        "    def _merge_profile_traces(self: Scheduler)",
        '    @staticmethod\n    def _merge_profile_traces(self: "SchedulerProfilerManager")',
    )
    text = text.replace(
        "    def _stop_profile(\n        self: Scheduler, ",
        '    @staticmethod\n    def _stop_profile(\n        self: "SchedulerProfilerManager", ',
    )
    text = text.replace(
        "    def _profile_batch_predicate(self: Scheduler, batch: ScheduleBatch):",
        '    @staticmethod\n    def _profile_batch_predicate(self: "SchedulerProfilerManager", batch: ScheduleBatch):',
    )
    text = text.replace(
        "    def _profile(self: Scheduler, recv_req: ProfileReq):",
        '    @staticmethod\n    def _profile(self: "SchedulerProfilerManager", recv_req: ProfileReq):',
    )

    # 6. Drop TYPE_CHECKING Scheduler import (no longer used).
    text = text.replace(
        "    from sglang.srt.managers.scheduler import Scheduler\n",
        "",
    )

    # 7. forward_ct kwarg add on _init_profile / _profile_batch_predicate / _profile.
    text = text.replace(
        '    @staticmethod\n    def _init_profile(\n        self: "SchedulerProfilerManager",\n        output_dir: Optional[str],',
        '    @staticmethod\n    def _init_profile(\n'
        '        self: "SchedulerProfilerManager",\n'
        "        *,\n"
        "        forward_ct: int,\n"
        "        output_dir: Optional[str],",
    )
    text = text.replace(
        '    @staticmethod\n    def _profile_batch_predicate(self: "SchedulerProfilerManager", batch: ScheduleBatch):',
        '    @staticmethod\n    def _profile_batch_predicate(self: "SchedulerProfilerManager", *, batch: ScheduleBatch, forward_ct: int):',
    )
    text = text.replace(
        '    @staticmethod\n    def _profile(self: "SchedulerProfilerManager", recv_req: ProfileReq):',
        '    @staticmethod\n    def _profile(self: "SchedulerProfilerManager", *, recv_req: ProfileReq, forward_ct: int):',
    )

    # 8. Body: ``self.forward_ct`` reads → bare ``forward_ct``.
    text = text.replace("self.forward_ct", "forward_ct")

    # 9. ``_profile`` body's two ``self._init_profile(...)`` invocations switch
    #    to keyword form forwarding forward_ct.
    text = text.replace(
        "                return self._init_profile(\n"
        "                    recv_req.output_dir,\n",
        "                return self._init_profile(\n"
        "                    forward_ct=forward_ct,\n"
        "                    output_dir=recv_req.output_dir,\n"
        "                    start_step=recv_req.start_step,\n"
        "                    num_steps=recv_req.num_steps,\n"
        "                    activities=recv_req.activities,\n"
        "                    with_stack=recv_req.with_stack,\n"
        "                    record_shapes=recv_req.record_shapes,\n"
        "                    profile_by_stage=recv_req.profile_by_stage,\n"
        "                    profile_id=recv_req.profile_id,\n"
        "                    merge_profiles=recv_req.merge_profiles,\n"
        "                    profile_prefix=recv_req.profile_prefix,\n"
        "                    profile_stages=recv_req.profile_stages,\n"
        "                )\n",
    )
    # Drop the now-redundant positional args of the first invocation.
    text = text.replace(
        "                    recv_req.start_step,\n"
        "                    recv_req.num_steps,\n"
        "                    recv_req.activities,\n"
        "                    recv_req.with_stack,\n"
        "                    recv_req.record_shapes,\n"
        "                    recv_req.profile_by_stage,\n"
        "                    recv_req.profile_id,\n"
        "                    recv_req.merge_profiles,\n"
        "                    recv_req.profile_prefix,\n"
        "                    recv_req.profile_stages,\n"
        "                )\n",
        "",
    )
    # Same for the second invocation.
    text = text.replace(
        "                self._init_profile(\n"
        "                    recv_req.output_dir,\n",
        "                self._init_profile(\n"
        "                    forward_ct=forward_ct,\n"
        "                    output_dir=recv_req.output_dir,\n"
        "                    start_step=recv_req.start_step,\n"
        "                    num_steps=recv_req.num_steps,\n"
        "                    activities=recv_req.activities,\n"
        "                    with_stack=recv_req.with_stack,\n"
        "                    record_shapes=recv_req.record_shapes,\n"
        "                    profile_by_stage=recv_req.profile_by_stage,\n"
        "                    profile_id=recv_req.profile_id,\n"
        "                    merge_profiles=recv_req.merge_profiles,\n"
        "                    profile_prefix=recv_req.profile_prefix,\n"
        "                )\n",
    )
    text = text.replace(
        "                    recv_req.start_step,\n"
        "                    recv_req.num_steps,\n"
        "                    recv_req.activities,\n"
        "                    recv_req.with_stack,\n"
        "                    recv_req.record_shapes,\n"
        "                    recv_req.profile_by_stage,\n"
        "                    recv_req.profile_id,\n"
        "                    recv_req.merge_profiles,\n"
        "                    recv_req.profile_prefix,\n"
        "                )\n",
        "",
    )

    # Add TYPE_CHECKING import for the new TargetClass so the
    # ``self: "SchedulerProfilerManager"`` annotation resolves under pyflakes.
    if "from sglang.srt.managers.scheduler_components.profiler_manager import SchedulerProfilerManager" not in text:
        text = text.replace(
            "if TYPE_CHECKING:\n",
            "if TYPE_CHECKING:\n"
            "    from sglang.srt.managers.scheduler_components.profiler_manager import SchedulerProfilerManager\n",
            1,
        )

    mixin.write_text(text)

    # 10. In scheduler.py, add import + replace init_profiler call with ctor.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.dp_attn_adapter import (\n    SchedulerDPAttnAdapter,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.profiler_manager import (\n"
            "    SchedulerProfilerManager,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        self.init_profiler()\n",
        new=SCHEDULER_INIT_INSERT,
    )

    # 11. _profile_batch_predicate hot-path callsite: forward forward_ct kwarg.
    text = replace_call_site(
        text,
        old="        self._profile_batch_predicate(batch)\n",
        new="        self._profile_batch_predicate(\n"
        "            self.profiler_manager, batch=batch, forward_ct=self.forward_ct\n"
        "        )\n",
    )

    # 12. RPC dispatch tuple: replace ``self.profile`` with a lambda that
    #     forwards forward_ct (via ``self._profile`` staticmethod, post privacy
    #     flip).
    text = replace_call_site(
        text,
        old="                (ProfileReq, self.profile),\n",
        new="                (\n"
        "                    ProfileReq,\n"
        "                    lambda req: self._profile(\n"
        "                        self.profiler_manager,\n"
        "                        recv_req=req,\n"
        "                        forward_ct=self.forward_ct,\n"
        "                    ),\n"
        "                ),\n",
    )

    sched.write_text(text)

    # 13. Test fixture: privacy-flip the ``init_profile`` reference (still on
    #     SchedulerProfilerMixin in this commit).
    test_text = test_profile.read_text()
    test_text = replace_call_site(
        test_text,
        old="        sig = inspect.signature(SchedulerProfilerMixin.init_profile)\n",
        new="        sig = inspect.signature(SchedulerProfilerMixin._init_profile)\n",
    )
    test_profile.write_text(test_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
