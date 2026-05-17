#!/usr/bin/env python3
"""Inplace prep for ``migrate-profiler-mixin``: build the
``SchedulerProfilerManager`` (@dataclass) skeleton at
``scheduler_components/profiler_manager.py``, lift the ``init_profiler``
method body out of ``SchedulerProfilerMixin`` into the manager
``__post_init__`` (byte-identical block move; return-short-circuit
semantics preserved because ``__post_init__`` is itself a method),
replace the ``self.init_profiler()`` call in ``Scheduler.__init__`` with
the manager ctor, inject the ``forward_ct`` Callable getter, and
type-flip the 6 mixin methods to ``@staticmethod`` with
``self: "SchedulerProfilerManager"``. Body refs to ``self.forward_ct``
(runtime-mutable Scheduler state) rewrite to ``self.get_forward_ct()``
(Callable getter form).

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
SUBJECT = "Stand up SchedulerProfilerManager; migrate profiler state to it"
BODY = """\
Inplace prep for the ``migrate-profiler-mixin`` mech move.

- Privacy flip (absorbed from the former ``-pre-rename`` straggler): 4
  ``SchedulerProfilerMixin`` methods are made private because their
  post-move home (``SchedulerProfilerManager``) treats them as ``_*``
  helpers; lifecycle is driven by the manager's owner via composition.
    * ``init_profile``  → ``_init_profile``
    * ``start_profile`` → ``_start_profile``
    * ``stop_profile``  → ``_stop_profile``
    * ``profile``       → ``_profile``
  Bodies byte-identical; cross-method callsites updated to the renamed
  forms; one ``test_profile_merger.py`` reference updated.
- Create ``scheduler_components/profiler_manager.py`` with a
  ``SchedulerProfilerManager`` class (skeleton: ctor only, no methods
  yet). Ctor takes ``ps`` + ``dp_tp_cpu_group`` static kwargs plus a
  ``get_forward_ct: Callable[[], int]`` Callable getter (runtime-mutable
  Scheduler state per ``MECH_COMMIT_SPLIT.md`` §"Runtime-mutable scheduler
  state Callable injection").
- Cut the ``init_profiler`` body from ``SchedulerProfilerMixin`` and
  paste it byte-identical (including the ``return`` short-circuit) into
  ``SchedulerProfilerManager.__post_init__``. Delete the now-empty
  ``init_profiler`` method from the mixin. Replace the
  ``self.init_profiler()`` call in ``Scheduler.__init__`` with
  ``self.profiler_manager = SchedulerProfilerManager(...)``.
- In ``SchedulerProfilerMixin``, type-flip the remaining methods to
  ``@staticmethod`` with ``self: "SchedulerProfilerManager"``. Body
  ``self.forward_ct`` reads rewrite to ``self.get_forward_ct()``.
- Update the hot-path callers in ``scheduler.py`` to the
  class-qualified ``self._profile_batch_predicate(self.profiler_manager,
  ...)`` / ``self._profile(self.profiler_manager, ...)`` form (prep
  cadence; move step collapses to ``self.profiler_manager.<method>``).

The type-flipped methods stay inside ``SchedulerProfilerMixin`` in this
commit; physical cut + paste to ``SchedulerProfilerManager`` body
happens in ``migrate-profiler-mixin-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


PROFILER_MANAGER_HEADER = '''from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, List, Optional

from sglang.srt.environ import envs
from sglang.srt.utils.profile_utils import ProfileManager


@dataclass(kw_only=True)
class SchedulerProfilerManager:
    ps: Any
    dp_tp_cpu_group: Any
    get_forward_ct: Callable[[], int]

    def __post_init__(self) -> None:
'''


# The original ``init_profiler`` method block as it lives in the mixin
# right after pre-rename. Method-level indent (4 spaces); body lines at
# 8-space indent. We cut this verbatim from the mixin.
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


# Same body, re-indented for ``__post_init__`` context (still 8 spaces
# because ``__post_init__`` is itself a method). Byte-identical to the
# mixin body, including the ``return`` short-circuit.
INIT_PROFILER_BODY_FOR_POST_INIT = """\
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
    test_profile = wt / "test/registered/unit/utils/test_profile_merger.py"

    # 0. Privacy flip (absorbed from former ``migrate-profiler-mixin-pre-rename``
    #    straggler): mark 4 ``SchedulerProfilerMixin`` methods as private
    #    (``_*``) because their post-move home (``SchedulerProfilerManager``)
    #    treats them as ``_*`` helpers driven by the manager's owner via
    #    composition. Body byte-identical wrt main; cross-method callsites
    #    updated to the renamed forms.
    text = mixin.read_text()
    text = text.replace("    def init_profile(\n", "    def _init_profile(\n")
    text = text.replace("    def start_profile(\n", "    def _start_profile(\n")
    text = text.replace("    def stop_profile(\n", "    def _stop_profile(\n")
    text = text.replace(
        "    def profile(self: Scheduler, recv_req: ProfileReq):",
        "    def _profile(self: Scheduler, recv_req: ProfileReq):",
    )
    text = text.replace("self.init_profile(", "self._init_profile(")
    text = text.replace("self.start_profile(", "self._start_profile(")
    text = text.replace("self.stop_profile(", "self._stop_profile(")
    mixin.write_text(text)

    test_text = test_profile.read_text()
    test_text = test_text.replace(
        "sig = inspect.signature(SchedulerProfilerMixin.init_profile)",
        "sig = inspect.signature(SchedulerProfilerMixin._init_profile)",
    )
    test_profile.write_text(test_text)

    # 1. Cut the ``init_profiler`` method block from the mixin (byte-identical;
    #    return-short-circuit preserved).
    text = mixin.read_text()
    if INIT_PROFILER_METHOD_BLOCK not in text:
        raise RuntimeError("init_profiler method block anchor mismatch")
    text = text.replace(INIT_PROFILER_METHOD_BLOCK, "")
    mixin_text = text

    # 2. Create new target file with class skeleton (ctor body holds the
    #    relocated init_profiler body verbatim inside __post_init__).
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    if not pkg_init.exists():
        pkg_init.write_text("")
    target.write_text(PROFILER_MANAGER_HEADER + INIT_PROFILER_BODY_FOR_POST_INIT)

    # 3. In mixin: type-flip the 6 remaining methods to @staticmethod with
    #    self: "SchedulerProfilerManager".
    text = mixin_text
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

    # 3b. Inside the now-@staticmethod mixin methods, ``self`` is a
    #     ``SchedulerProfilerManager`` so ``self._foo(...)`` no longer
    #     resolves to the sibling mixin methods. Rewrite intra-mixin
    #     callsites to the class-qualified ``SchedulerProfilerMixin._foo(self, ...)``
    #     static-call form. ``move`` collapses these to
    #     ``self._foo(...)`` once the methods live on the manager.
    text = text.replace(
        "merge_message = self._merge_profile_traces()",
        "merge_message = SchedulerProfilerMixin._merge_profile_traces(self)",
    )
    text = text.replace(
        "self._start_profile(batch.forward_mode)",
        "SchedulerProfilerMixin._start_profile(self, batch.forward_mode)",
    )
    text = text.replace(
        "self._stop_profile(stage=ForwardMode.EXTEND)",
        "SchedulerProfilerMixin._stop_profile(self, stage=ForwardMode.EXTEND)",
    )
    text = text.replace(
        "self._stop_profile(stage=ForwardMode.DECODE)",
        "SchedulerProfilerMixin._stop_profile(self, stage=ForwardMode.DECODE)",
    )
    text = text.replace(
        "                self._stop_profile()\n",
        "                SchedulerProfilerMixin._stop_profile(self)\n",
    )
    text = text.replace(
        "                self._start_profile()\n",
        "                SchedulerProfilerMixin._start_profile(self)\n",
    )
    text = text.replace(
        "                return self._init_profile(\n",
        "                return SchedulerProfilerMixin._init_profile(\n                    self,\n",
    )
    text = text.replace(
        "                self._init_profile(\n",
        "                SchedulerProfilerMixin._init_profile(\n                    self,\n",
    )
    text = text.replace(
        "                return self._start_profile()\n",
        "                return SchedulerProfilerMixin._start_profile(self)\n",
    )
    text = text.replace(
        "            return self._stop_profile()\n",
        "            return SchedulerProfilerMixin._stop_profile(self)\n",
    )

    # 4. Body: ``self.forward_ct`` reads → ``self.get_forward_ct()``
    #    (Callable getter form for runtime-mutable Scheduler state).
    text = text.replace("self.forward_ct", "self.get_forward_ct()")

    # 5. Swap the TYPE_CHECKING Scheduler import for SchedulerProfilerManager
    #    so the ``self: "SchedulerProfilerManager"`` annotation resolves under
    #    pyflakes.
    text = text.replace(
        "    from sglang.srt.managers.scheduler import Scheduler\n",
        "    from sglang.srt.managers.scheduler_components.profiler_manager import SchedulerProfilerManager\n",
    )

    mixin.write_text(text)

    # 6. Scheduler.__init__: replace ``self.init_profiler()`` with the
    #    SchedulerProfilerManager ctor.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.dp_attn import (\n    SchedulerDPAttnAdapter,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.profiler_manager import (\n"
            "    SchedulerProfilerManager,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old="        # Init profiler\n        self.init_profiler()\n",
        new="        # Init profiler\n" + SCHEDULER_INIT_INSERT,
    )

    # 7. Caller rewrites — prep cadence (class-qualified form). ``move`` will
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
