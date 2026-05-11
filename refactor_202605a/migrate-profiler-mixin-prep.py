#!/usr/bin/env python3
"""Inplace prep for ``migrate-profiler-mixin``: build the
``SchedulerProfilerManager`` (@dataclass) skeleton at
``scheduler_components/profiler_manager.py``, lift the inlined
``init_profiler`` body out of ``Scheduler.__init__`` into the manager ctor
(byte-identical block move), wire composition on Scheduler, inject the
``forward_ct`` Callable getter, and type-flip the 6 mixin methods to
``@staticmethod`` with ``self: "SchedulerProfilerManager"``. Body refs to
``self.forward_ct`` (runtime-mutable Scheduler state) rewrite to
``self.get_forward_ct()`` (Callable getter form).

Method bodies byte-identical wrt the post-move state (modulo
``@staticmethod`` + ``self: "SchedulerProfilerManager"`` annotation
simplification handled by ``migrate-profiler-mixin-move``).
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
SUBJECT = "Stage profiler controls for handoff to SchedulerProfilerManager"
BODY = """\
Inplace prep for the ``migrate-profiler-mixin`` mech move.

- Create ``scheduler_components/profiler_manager.py`` with a
  ``SchedulerProfilerManager`` class (skeleton: ctor only, no methods
  yet). Ctor takes ``ps`` + ``dp_tp_cpu_group`` static kwargs plus a
  ``get_forward_ct: Callable[[], int]`` Callable getter (runtime-mutable
  Scheduler state per ``MECH_COMMIT_SPLIT.md`` §"Runtime-mutable scheduler
  state Callable injection").
- Lift the inlined ``init_profiler`` body out of ``Scheduler.__init__``
  into ``SchedulerProfilerManager.__init__`` (byte-identical block
  move). Instantiate
  ``self.profiler_manager = SchedulerProfilerManager(...)`` in place.
- In ``SchedulerProfilerMixin``, type-flip the 6 remaining methods to
  ``@staticmethod`` with ``self: "SchedulerProfilerManager"``. Body
  ``self.forward_ct`` reads rewrite to ``self.get_forward_ct()``.
- Update the 2 hot-path callers in ``scheduler.py`` to the
  class-qualified ``self._profile_batch_predicate(self.profiler_manager,
  ...)`` / ``self._profile(self.profiler_manager, ...)`` form (prep
  cadence; move step collapses to ``self.profiler_manager.<method>``).

The 6 methods stay inside ``SchedulerProfilerMixin`` in this commit;
physical cut + paste to ``SchedulerProfilerManager`` body happens in
``migrate-profiler-mixin-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


PROFILER_MANAGER_HEADER = '''from __future__ import annotations  # noqa: F401

from pathlib import Path  # noqa: F401
from typing import Callable, List, Optional  # noqa: F401

from sglang.srt.environ import envs  # noqa: F401
from sglang.srt.utils.profile_utils import ProfileManager  # noqa: F401


class SchedulerProfilerManager:
    """torch profiler / RPD / cuda profiler lifecycle. Composition target on
    Scheduler (``self.profiler_manager``). Owns 19 mutable runtime fields."""

    def __init__(
        self,
        *,
        ps,
        dp_tp_cpu_group,
        get_forward_ct: Callable[[], int],
    ) -> None:
        self.ps = ps
        self.dp_tp_cpu_group = dp_tp_cpu_group
        self.get_forward_ct = get_forward_ct

'''


# The inlined block currently in Scheduler.__init__ (from pre-prep). After
# this commit it lives byte-identical inside SchedulerProfilerManager.__init__,
# replaced in Scheduler.__init__ by the ctor instantiation.
INIT_PROFILER_BODY_INLINED = """\
        if envs.SGLANG_PROFILE_V2.get():
            self._profile_manager = ProfileManager(
                ps=self.ps,
                cpu_group=self.dp_tp_cpu_group,
            )
        else:
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


SCHEDULER_INIT_INSERT = """\
        self.profiler_manager = SchedulerProfilerManager(
            ps=self.ps,
            dp_tp_cpu_group=self.dp_tp_cpu_group,
            get_forward_ct=lambda: self.forward_ct,
        )
"""


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_profiler_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/profiler_manager.py"

    # 1. Create new target file with class skeleton (ctor only).
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    if not pkg_init.exists():
        pkg_init.write_text("")
    target.write_text(PROFILER_MANAGER_HEADER + INIT_PROFILER_BODY_INLINED)

    # 2. In mixin: type-flip the 6 methods to @staticmethod with
    #    self: "SchedulerProfilerManager".
    text = mixin.read_text()
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

    # 3. Body: ``self.forward_ct`` reads → ``self.get_forward_ct()``
    #    (Callable getter form for runtime-mutable Scheduler state).
    text = text.replace("self.forward_ct", "self.get_forward_ct()")

    # 4. Swap the TYPE_CHECKING Scheduler import for SchedulerProfilerManager
    #    so the ``self: "SchedulerProfilerManager"`` annotation resolves under
    #    pyflakes.
    text = text.replace(
        "    from sglang.srt.managers.scheduler import Scheduler\n",
        "    from sglang.srt.managers.scheduler_components.profiler_manager import SchedulerProfilerManager\n",
    )

    mixin.write_text(text)

    # 5. Scheduler.__init__: replace the inlined body with the ctor call.
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
        old="        # Init profiler\n" + INIT_PROFILER_BODY_INLINED,
        new="        # Init profiler\n" + SCHEDULER_INIT_INSERT,
    )

    # 6. Caller rewrites — prep cadence (class-qualified form). ``move`` will
    #    collapse to ``self.profiler_manager.<method>``.
    text = replace_call_site(
        text,
        old="        self._profile_batch_predicate(batch)\n",
        new="        self._profile_batch_predicate(self.profiler_manager, batch)\n",
    )
    text = replace_call_site(
        text,
        old="                (ProfileReq, self.profile),\n",
        new="                (\n"
        "                    ProfileReq,\n"
        "                    lambda req: self._profile(\n"
        "                        self.profiler_manager, req\n"
        "                    ),\n"
        "                ),\n",
    )
    sched.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
