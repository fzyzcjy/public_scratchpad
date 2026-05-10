#!/usr/bin/env python3
"""Migrate ``SchedulerProfilerMixin`` to ``SchedulerProfilerManager`` at
``scheduler_components/observability/profiler_manager.py`` (composition).

- Ctor takes narrow typed kwargs (``ps``, ``dp_tp_cpu_group``) and replicates
  ``init_profiler`` body inside ``__init__``. The original ``init_profiler``
  method is removed (Scheduler.__init__ no longer calls it).
- 4 methods receive a privacy flip (add ``_`` prefix only — no rename):
  ``init_profile`` → ``_init_profile`` / ``start_profile`` → ``_start_profile`` /
  ``stop_profile`` → ``_stop_profile`` / ``profile`` → ``_profile``.
- ``forward_ct`` becomes a per-call keyword on ``_init_profile``,
  ``_profile_batch_predicate``, and ``_profile`` (R4 kwarg add per
  EXECUTION_GUIDE item 2). The 4 ``self.forward_ct`` reads in those bodies
  become bare ``forward_ct``.
- 3 callsites updated: ``Scheduler.__init__`` (init_profiler call removed +
  ctor instantiation added), the ``_profile_batch_predicate`` hot-path call
  in ``run_batch``, and the RPC dispatch tuple ``(ProfileReq, self.profile)``
  in ``init_request_dispatcher``. The RPC dispatch becomes a lambda to
  forward ``forward_ct``.
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

ID = "migrate-profiler-mixin"
SUBJECT = "Migrate SchedulerProfilerMixin to SchedulerProfilerManager (composition)"
BODY = """\
Move ``SchedulerProfilerMixin`` (7 methods) to a new ``SchedulerProfilerManager``
class at ``scheduler_components/observability/profiler_manager.py``. Scheduler
holds it as ``self.profiler_manager``.

The ctor takes narrow typed kwargs and replicates the original
``init_profiler`` body inline (the ``init_profiler`` method itself is
removed). 4 methods get a privacy flip (add ``_`` prefix only — no rename):
``init_profile`` / ``start_profile`` / ``stop_profile`` / ``profile``.

``forward_ct`` is converted to a per-call keyword on ``_init_profile``,
``_profile_batch_predicate``, and ``_profile`` (R4 kwarg add).

Callers updated:
- ``Scheduler.__init__``: drop ``self.init_profiler()`` call; instantiate
  ``self.profiler_manager = SchedulerProfilerManager(...)`` instead.
- ``Scheduler.run_batch`` hot path: pass ``forward_ct=self.forward_ct`` to
  ``_profile_batch_predicate``.
- ``Scheduler.init_request_dispatcher`` RPC tuple: wrap
  ``self.profiler_manager._profile`` in a lambda to inject ``forward_ct``.

No behavior change.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# Replacement for ``class SchedulerProfilerMixin:`` line. The original
# ``init_profiler`` method body becomes ``__init__`` body.
NEW_CLASS_AND_INIT = '''\
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


# Original ``init_profiler`` method block (full, 4-space indent) — remove from file.
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


SCHEDULER_INIT_INSERT = """\
        self.profiler_manager = SchedulerProfilerManager(
            ps=self.ps,
            dp_tp_cpu_group=self.dp_tp_cpu_group,
        )

"""


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_profiler_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/observability/__init__.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/observability/profiler_manager.py"

    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    pkg_init.write_text("")

    text = src.read_text()

    # Replace class header and inline ``init_profiler`` as ctor body.
    if "class SchedulerProfilerMixin:\n" not in text:
        raise RuntimeError("Profiler class header anchor mismatch")
    text = text.replace("class SchedulerProfilerMixin:\n", NEW_CLASS_AND_INIT)

    # Remove the original init_profiler method body (now redundant).
    if INIT_PROFILER_METHOD_BLOCK not in text:
        raise RuntimeError("init_profiler method block anchor mismatch")
    text = text.replace(INIT_PROFILER_METHOD_BLOCK, "")

    # Drop ``: Scheduler`` annotations on remaining methods.
    text = text.replace("self: Scheduler", "self")

    # Drop the TYPE_CHECKING Scheduler import.
    text = text.replace(
        "    from sglang.srt.managers.scheduler import Scheduler\n",
        "",
    )

    # Privacy flips (add ``_`` prefix). Touch both definitions and internal
    # cross-method calls.
    privacy_pairs = [
        ("init_profile", "_init_profile"),
        ("start_profile", "_start_profile"),
        ("stop_profile", "_stop_profile"),
        ("profile", "_profile"),  # last so it doesn't double-prefix above 3
    ]
    # Definitions:
    text = text.replace("def init_profile(\n", "def _init_profile(\n")
    text = text.replace("def start_profile(\n", "def _start_profile(\n")
    text = text.replace("def stop_profile(\n", "def _stop_profile(\n")
    text = text.replace(
        "def profile(self, recv_req: ProfileReq):",
        "def _profile(self, *, recv_req: ProfileReq, forward_ct: int):",
    )
    # Internal cross-method calls:
    text = text.replace("self.init_profile(", "self._init_profile(")
    text = text.replace("self.start_profile(", "self._start_profile(")
    text = text.replace("self.stop_profile(", "self._stop_profile(")

    # Per-call ``forward_ct`` for ``_init_profile`` and ``_profile_batch_predicate``.
    # Add kwarg to signatures.
    text = text.replace(
        "    def _init_profile(\n        self,\n        output_dir: Optional[str],",
        "    def _init_profile(\n"
        "        self,\n"
        "        *,\n"
        "        forward_ct: int,\n"
        "        output_dir: Optional[str],",
    )
    text = text.replace(
        "    def _profile_batch_predicate(self, batch: ScheduleBatch):",
        "    def _profile_batch_predicate(self, *, batch: ScheduleBatch, forward_ct: int):",
    )
    # Body: ``self.forward_ct`` reads → bare ``forward_ct``.
    text = text.replace("self.forward_ct", "forward_ct")

    # ``_profile``'s body calls ``self._init_profile(...)`` 2x — those calls
    # need to forward ``forward_ct`` and switch to keyword form. Rewrite the
    # 2 invocations.
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

    # ``_profile_batch_predicate`` body has internal calls to ``self.start_profile``
    # / ``self.stop_profile`` (already privacy-flipped above).

    target.write_text(text)
    src.unlink()

    # Update Scheduler: import + remove from inheritance + ctor + 2 callsite rewrites.
    text = sched.read_text()
    text = text.replace(
        "from sglang.srt.managers.scheduler_profiler_mixin import SchedulerProfilerMixin\n",
        "",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.scheduling.dp_attn_adapter import (\n    SchedulerDPAttnAdapter,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.observability.profiler_manager import (\n"
            "    SchedulerProfilerManager,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old="    SchedulerProfilerMixin,\n",
        new="",
    )
    # Replace ``self.init_profiler()`` with ctor instantiation (line 472).
    text = replace_call_site(
        text,
        old="        self.init_profiler()\n",
        new=SCHEDULER_INIT_INSERT,
    )
    # _profile_batch_predicate hot-path callsite (line 2968 area).
    text = replace_call_site(
        text,
        old="        self._profile_batch_predicate(batch)\n",
        new="        self.profiler_manager._profile_batch_predicate(\n"
        "            batch=batch, forward_ct=self.forward_ct\n"
        "        )\n",
    )
    # RPC dispatch tuple — replace ``self.profile`` with a lambda forwarding forward_ct.
    text = replace_call_site(
        text,
        old="                (ProfileReq, self.profile),\n",
        new="                (\n"
        "                    ProfileReq,\n"
        "                    lambda req: self.profiler_manager._profile(\n"
        "                        recv_req=req, forward_ct=self.forward_ct\n"
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
