#!/usr/bin/env python3
"""Inplace prep for ``migrate-update-weights-mixin``: create the
``SchedulerWeightUpdaterManager`` class skeleton at
``scheduler_components/weight_updater.py`` (ctor with 4 collaborator kwargs
+ 2 Callable kwargs + ``offload_tags``, no methods yet), instantiate in
``Scheduler.__init__`` BEFORE the existing ``dp_attn_adapter`` ctor and
BEFORE ``init_request_dispatcher``. Remove ``self.offload_tags = set()``
from Scheduler. Rewire ``dp_attn_adapter`` ctor's ``offload_tags`` kwarg to
``self.weight_updater.offload_tags``. Convert the 12 mixin methods to
``@staticmethod`` with ``self: "SchedulerWeightUpdaterManager"``. Wrap the
10 RPC dispatch tuple references in lambdas to inject
``self.weight_updater`` as the staticmethod ``self`` arg.

Method bodies byte-identical wrt the post-move state (modulo decorator +
the ``def foo(self: SchedulerWeightUpdaterManager, ...)`` →
``def foo(self, ...)`` signature simplification in the move commit).
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "migrate-update-weights-mixin-prep"
SUBJECT = "Build SchedulerWeightUpdaterManager skeleton + @staticmethod prep (prep for move)"
BODY = """\
Inplace prep for the ``migrate-update-weights-mixin`` mech move.

- Create ``scheduler_components/weight_updater.py`` with an empty
  ``SchedulerWeightUpdaterManager`` class. Ctor takes 4 collaborator kwargs
  (``tp_worker`` / ``draft_worker`` / ``tp_cpu_group`` /
  ``memory_saver_adapter``) + 2 ``Callable`` kwargs (``flush_cache`` /
  ``is_fully_idle``). Initializes ``self.offload_tags = set()`` (migrated
  from Scheduler).
- Instantiate ``self.weight_updater = SchedulerWeightUpdaterManager(...)``
  in ``Scheduler.__init__`` BEFORE the existing ``dp_attn_adapter`` ctor
  and BEFORE ``init_request_dispatcher``, so the field reference for the
  dp_attn_adapter ``offload_tags`` rewiring resolves.
- Remove the now-redundant ``self.offload_tags = set()`` from Scheduler.
- Rewire ``dp_attn_adapter`` ctor's ``offload_tags`` kwarg to
  ``self.weight_updater.offload_tags``.
- In the mixin file, convert all 12 methods to ``@staticmethod`` with
  ``self: "SchedulerWeightUpdaterManager"``. Body bytes unchanged.
- 10 RPC dispatch callsites in ``init_request_dispatcher`` wrapped in
  lambdas to inject ``self.weight_updater`` as the staticmethod ``self``
  arg.

The 12 methods stay inside ``SchedulerUpdateWeightsMixin`` in this commit;
physical cut + paste to ``SchedulerWeightUpdaterManager`` body happens in
``migrate-update-weights-mixin-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


WEIGHT_UPDATER_HEADER = '''from __future__ import annotations  # noqa: F401

from typing import Callable  # noqa: F401


class SchedulerWeightUpdaterManager:
    """Hot weight-update / memory-occupation / model-save / weight-inspection
    control surface. Composition target on Scheduler
    (``self.weight_updater``)."""

    def __init__(
        self,
        *,
        tp_worker,
        draft_worker,
        tp_cpu_group,
        memory_saver_adapter,
        flush_cache: Callable[..., bool],
        is_fully_idle: Callable[..., bool],
    ) -> None:
        self.tp_worker = tp_worker
        self.draft_worker = draft_worker
        self.tp_cpu_group = tp_cpu_group
        self.memory_saver_adapter = memory_saver_adapter
        self.flush_cache = flush_cache
        self.is_fully_idle = is_fully_idle
        self.offload_tags: set = set()
'''


SCHEDULER_INIT_INSERT_WEIGHT_UPDATER = """\
        self.weight_updater = SchedulerWeightUpdaterManager(
            tp_worker=self.tp_worker,
            draft_worker=self.draft_worker,
            tp_cpu_group=self.tp_cpu_group,
            memory_saver_adapter=self.memory_saver_adapter,
            flush_cache=self.flush_cache,
            is_fully_idle=self.is_fully_idle,
        )

"""


# RPC dispatch callsites — 10 (note: ``update_weights_from_distributed`` is the
# only one with a 2-line tuple form). Each becomes a lambda forwarding
# ``self.weight_updater`` as the staticmethod ``self`` arg.
RPC_LAMBDA_PAIRS = [
    (
        "                (UpdateWeightFromDiskReqInput, self.update_weights_from_disk),\n",
        "                (\n"
        "                    UpdateWeightFromDiskReqInput,\n"
        "                    lambda req: self.update_weights_from_disk(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n"
        "                ),\n",
    ),
    (
        "                (InitWeightsUpdateGroupReqInput, self.init_weights_update_group),\n",
        "                (\n"
        "                    InitWeightsUpdateGroupReqInput,\n"
        "                    lambda req: self.init_weights_update_group(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n"
        "                ),\n",
    ),
    (
        "                (DestroyWeightsUpdateGroupReqInput, self.destroy_weights_update_group),\n",
        "                (\n"
        "                    DestroyWeightsUpdateGroupReqInput,\n"
        "                    lambda req: self.destroy_weights_update_group(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n"
        "                ),\n",
    ),
    (
        "                    self.update_weights_from_distributed,\n",
        "                    lambda req: self.update_weights_from_distributed(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n",
    ),
    (
        "                (UpdateWeightsFromTensorReqInput, self.update_weights_from_tensor),\n",
        "                (\n"
        "                    UpdateWeightsFromTensorReqInput,\n"
        "                    lambda req: self.update_weights_from_tensor(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n"
        "                ),\n",
    ),
    (
        "                (UpdateWeightsFromIPCReqInput, self.update_weights_from_ipc),\n",
        "                (\n"
        "                    UpdateWeightsFromIPCReqInput,\n"
        "                    lambda req: self.update_weights_from_ipc(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n"
        "                ),\n",
    ),
    (
        "                (GetWeightsByNameReqInput, self.get_weights_by_name),\n",
        "                (\n"
        "                    GetWeightsByNameReqInput,\n"
        "                    lambda req: self.get_weights_by_name(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n"
        "                ),\n",
    ),
    (
        "                (ReleaseMemoryOccupationReqInput, self.release_memory_occupation),\n",
        "                (\n"
        "                    ReleaseMemoryOccupationReqInput,\n"
        "                    lambda req: self.release_memory_occupation(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n"
        "                ),\n",
    ),
    (
        "                (ResumeMemoryOccupationReqInput, self.resume_memory_occupation),\n",
        "                (\n"
        "                    ResumeMemoryOccupationReqInput,\n"
        "                    lambda req: self.resume_memory_occupation(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n"
        "                ),\n",
    ),
    (
        "                (CheckWeightsReqInput, self.check_weights),\n",
        "                (\n"
        "                    CheckWeightsReqInput,\n"
        "                    lambda req: self.check_weights(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n"
        "                ),\n",
    ),
]


def transform(wt: Path) -> None:
    mixin = wt / "python/sglang/srt/managers/scheduler_update_weights_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/weight_updater.py"

    # 1. Create new target file with empty class skeleton (ctor + fields only).
    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    if not pkg_init.exists():
        pkg_init.write_text("")
    target.write_text(WEIGHT_UPDATER_HEADER)

    # 2. In mixin file, convert all 12 methods to @staticmethod inplace.
    text = mixin.read_text()
    method_names = [
        "flush_cache_after_weight_update",
        "update_weights_from_disk",
        "init_weights_update_group",
        "destroy_weights_update_group",
        "update_weights_from_distributed",
        "update_weights_from_tensor",
        "update_weights_from_ipc",
        "get_weights_by_name",
        "release_memory_occupation",
        "resume_memory_occupation",
        "check_weights",
        "save_remote_model",
        "save_sharded_model",
    ]
    for name in method_names:
        s, e = find_method_lines(
            text, class_name="SchedulerUpdateWeightsMixin", method_name=name
        )
        lines = text.splitlines(keepends=True)
        method_text = "".join(lines[s:e])
        # Add @staticmethod + type-flip self. Original sigs are mixed:
        #   - ``def foo(self: Scheduler, recv_req: T):`` (single-line)
        #   - ``def foo(\n        self: Scheduler, recv_req: T\n    ):`` (multi-line)
        #   - ``def update_weights_from_distributed(\n        self,\n ...`` (no type)
        #
        # We handle each case with a generic replacement: prepend @staticmethod
        # and switch ``self: Scheduler`` → ``self: "SchedulerWeightUpdaterManager"``.
        # The ``update_weights_from_distributed`` method has bare ``self``; flip
        # it via its multi-line signature.
        new_method = method_text.replace(
            "self: Scheduler",
            'self: "SchedulerWeightUpdaterManager"',
        )
        # Insert @staticmethod before ``    def <name>``.
        new_method = new_method.replace(
            f"    def {name}(",
            f"    @staticmethod\n    def {name}(",
            1,
        )
        # For ``update_weights_from_distributed`` only, the original signature
        # was ``def update_weights_from_distributed(\n        self,\n``. After
        # adding @staticmethod, we also need to type-flip the bare ``self``.
        if name == "update_weights_from_distributed":
            new_method = new_method.replace(
                "    @staticmethod\n    def update_weights_from_distributed(\n        self,\n",
                '    @staticmethod\n    def update_weights_from_distributed(\n        self: "SchedulerWeightUpdaterManager",\n',
            )
        text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # Swap the TYPE_CHECKING Scheduler import for the new TargetClass so the
    # ``self: "SchedulerWeightUpdaterManager"`` annotation resolves under
    # pyflakes (otherwise F821).
    text = text.replace(
        "if TYPE_CHECKING:\n    from sglang.srt.managers.scheduler import Scheduler\n",
        "if TYPE_CHECKING:\n"
        "    from sglang.srt.managers.scheduler_components.weight_updater import SchedulerWeightUpdaterManager\n",
    )

    mixin.write_text(text)

    # 3. In scheduler.py, add import + ctor instantiation + remove offload_tags.
    text = sched.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.profiler_manager import (\n    SchedulerProfilerManager,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.weight_updater import (\n"
            "    SchedulerWeightUpdaterManager,\n"
            ")\n"
        ),
    )

    # Remove ``self.offload_tags = set()`` from Scheduler (was inside
    # ``init_watch_dog_memory_saver_input_blocker``).
    text = replace_call_site(
        text,
        old="        self.offload_tags = set()\n",
        new="",
    )

    # Insert weight_updater ctor BEFORE the dp_attn_adapter ctor (which was
    # inserted in C5 prep just before ``self.is_initializing = False``). The
    # weight_updater ctor must come earlier so that
    # ``self.weight_updater.offload_tags`` resolves when dp_attn_adapter is
    # constructed.
    text = replace_call_site(
        text,
        old="        self.dp_attn_adapter = SchedulerDPAttnAdapter(\n",
        new=SCHEDULER_INIT_INSERT_WEIGHT_UPDATER
        + "        self.dp_attn_adapter = SchedulerDPAttnAdapter(\n",
    )

    # Rewire dp_attn_adapter's offload_tags arg from self.offload_tags to
    # self.weight_updater.offload_tags.
    text = replace_call_site(
        text,
        old="            offload_tags=self.offload_tags,\n",
        new="            offload_tags=self.weight_updater.offload_tags,\n",
    )

    # 10 RPC dispatch callsites — wrap in lambdas.
    for old, new in RPC_LAMBDA_PAIRS:
        text = replace_call_site(text, old=old, new=new)

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
