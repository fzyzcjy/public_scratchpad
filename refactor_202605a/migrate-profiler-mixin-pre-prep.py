#!/usr/bin/env python3
"""Pure block-move pre-prep for ``migrate-profiler-mixin``: inline the
``init_profiler`` method body into ``Scheduler.__init__`` in place of the
``self.init_profiler()`` call, and delete the now-dead ``init_profiler``
method from ``SchedulerProfilerMixin``.

This is a standalone block-relocation commit per
``MECH_COMMIT_SPLIT.md`` §"例外" (move a hunk between functions, body
byte-identical). The follow-up ``migrate-profiler-mixin-prep`` will lift
this inlined block into the ``SchedulerProfilerManager`` ctor body.

After this commit:
- ``Scheduler.__init__`` carries the 19-field ``init_profiler`` body
  inline, right at the original ``self.init_profiler()`` callsite.
- ``SchedulerProfilerMixin`` no longer defines ``init_profiler``.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import replace_call_site
from _runner import run_pr

ID = "migrate-profiler-mixin-pre-prep"
SUBJECT = "Inline init_profiler body into Scheduler.__init__ (block move)"
BODY = """\
Pure block-move pre-prep for ``migrate-profiler-mixin``.

Move the entire ``init_profiler`` body from ``SchedulerProfilerMixin`` into
``Scheduler.__init__``, replacing the ``self.init_profiler()`` call. The
method itself is then deleted from the mixin.

Diff is 2 hunks: one delete from the mixin (the full ``init_profiler``
method), one insert into ``Scheduler.__init__`` at the original call
site. ``git --color-moved`` should mark the relocated body as moved
(``self.X`` refs unchanged: the 19 profiler fields live on the same
Scheduler instance pre- and post-move).
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Original ``init_profiler`` method block in the mixin (4-space indent;
# includes the trailing blank line).
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


# Same body, indented for ``Scheduler.__init__`` context (still 8 spaces
# because Scheduler.__init__ is also a class method).
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


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_profiler_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"

    # 1. Cut the init_profiler method from the mixin.
    text = mixin.read_text()
    if INIT_PROFILER_METHOD_BLOCK not in text:
        raise RuntimeError("init_profiler method block anchor mismatch")
    text = text.replace(INIT_PROFILER_METHOD_BLOCK, "")
    mixin.write_text(text)

    # 2. Inline the body in Scheduler.__init__ in place of the call.
    text = sched.read_text()
    text = replace_call_site(
        text,
        old="        # Init profiler\n        self.init_profiler()\n",
        new="        # Init profiler\n" + INIT_PROFILER_BODY_INLINED,
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
