#!/usr/bin/env python3
"""Inplace prep for ``migrate-update-weights-mixin``: build the
``SchedulerWeightUpdaterManager`` (@dataclass) skeleton at
``scheduler_components/weight_updater.py`` (ctor with 4 collaborator kwargs
+ 2 Callable kwargs; ``self.offload_tags`` field migrated in), instantiate
in ``Scheduler.__init__`` BEFORE ``self.init_request_dispatcher()`` (so
``self.weight_updater`` exists by the time dispatch lambdas resolve it).
Delete the original ``self.offload_tags = set()`` from
``Scheduler.init_watch_dog_memory_saver_input_blocker`` (ownership now
lives on the manager). Rewire the ``dp_attn_adapter`` ctor's
``offload_tags`` kwarg to ``self.weight_updater.offload_tags``. Convert
13 mixin methods to ``@staticmethod`` with
``self: "SchedulerWeightUpdaterManager"``. Rewrap the 10 RPC dispatch
tuples in ``init_request_dispatcher`` directly into the lambda form that
invokes the staticmethod (``lambda req: self.method(self.weight_updater,
req)``).

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
SUBJECT = "Carve out SchedulerWeightUpdaterManager for weight-update state"
BODY = """\
Inplace prep for the ``migrate-update-weights-mixin`` mech move.

- Create ``scheduler_components/weight_updater.py`` with a
  ``SchedulerWeightUpdaterManager`` class (skeleton: ctor only, no
  methods yet). Ctor takes the collaborator kwargs ``tp_worker`` /
  ``draft_worker`` / ``tp_cpu_group`` / ``memory_saver_adapter`` plus
  the ``Callable`` kwargs ``flush_cache`` / ``is_fully_idle``.
  Initializes ``self.offload_tags = set()`` (ownership migrated from
  Scheduler).
- Instantiate ``self.weight_updater = SchedulerWeightUpdaterManager(...)``
  in ``Scheduler.__init__`` BEFORE ``self.init_request_dispatcher()``
  (so the dispatch lambdas can resolve ``self.weight_updater`` lazily).
- Delete the original ``self.offload_tags = set()`` from
  ``Scheduler.init_watch_dog_memory_saver_input_blocker`` (ownership
  now lives on the manager).
- Rewire ``dp_attn_adapter`` ctor's ``offload_tags`` kwarg from
  ``self.offload_tags`` to ``self.weight_updater.offload_tags``.
- In the mixin, type-flip every weight-update method to ``@staticmethod``
  with ``self: "SchedulerWeightUpdaterManager"``. Body bytes unchanged
  (no runtime-mutable Scheduler state is read; the mixin already
  collaborates only through ``self.tp_worker`` / ``self.draft_worker``
  / etc., which become the manager's own fields).
- Rewrap the 10 RPC dispatch tuples in ``init_request_dispatcher`` from
  the direct method-ref form ``(MessageClass, self.method)`` into the
  lambda form that invokes the staticmethod with the manager as first
  arg: ``(MessageClass, lambda req: self.method(self.weight_updater,
  req))``.

The weight-update methods stay inside ``SchedulerUpdateWeightsMixin`` in
this commit; physical cut + paste to ``SchedulerWeightUpdaterManager``
body happens in ``migrate-update-weights-mixin-move``.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


WEIGHT_UPDATER_HEADER = '''from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass(kw_only=True, slots=True)
class SchedulerWeightUpdaterManager:
    tp_worker: Any
    draft_worker: Any
    tp_cpu_group: Any
    memory_saver_adapter: Any
    flush_cache: Callable[..., bool]
    is_fully_idle: Callable[..., bool]
    offload_tags: set = field(default_factory=set)
    stashed_model_static_state: Any = None
'''


SCHEDULER_INIT_INSERT = """\
        self.weight_updater = SchedulerWeightUpdaterManager(
            tp_worker=self.tp_worker,
            draft_worker=self.draft_worker,
            tp_cpu_group=self.tp_cpu_group,
            memory_saver_adapter=self.memory_saver_adapter,
            flush_cache=self.flush_cache,
            is_fully_idle=self.is_fully_idle,
        )

"""


METHOD_NAMES = [
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


# 10 RPC dispatch tuples: rewrap each direct bound-method ref into the
# lambda form that invokes the post-typeflip staticmethod with
# ``self.weight_updater`` as the first arg. The
# ``UpdateWeightsFromDistributedReqInput`` site is already multi-line in
# the base (long message-class name); the rest are single-line.
RPC_LAMBDA_WRAPS = [
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
        "                (\n"
        "                    UpdateWeightsFromDistributedReqInput,\n"
        "                    self.update_weights_from_distributed,\n"
        "                ),\n",
        "                (\n"
        "                    UpdateWeightsFromDistributedReqInput,\n"
        "                    lambda req: self.update_weights_from_distributed(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n"
        "                ),\n",
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

    # 2. In mixin file, convert all 13 methods to @staticmethod inplace.
    text = mixin.read_text()
    for name in METHOD_NAMES:
        s, e = find_method_lines(
            text, class_name="SchedulerUpdateWeightsMixin", method_name=name
        )
        lines = text.splitlines(keepends=True)
        method_text = "".join(lines[s:e])
        new_method = method_text.replace(
            "self: Scheduler",
            'self: "SchedulerWeightUpdaterManager"',
        )
        # Prepend @staticmethod.
        new_method = new_method.replace(
            f"    def {name}(",
            f"    @staticmethod\n    def {name}(",
            1,
        )
        # ``update_weights_from_distributed`` uses bare ``self`` (multi-line
        # signature without type annotation); flip via its specific shape.
        if name == "update_weights_from_distributed":
            new_method = new_method.replace(
                "    @staticmethod\n    def update_weights_from_distributed(\n        self,\n",
                '    @staticmethod\n    def update_weights_from_distributed(\n        self: "SchedulerWeightUpdaterManager",\n',
            )
        text = "".join(lines[:s]) + new_method + "".join(lines[e:])

    # 3. Swap the TYPE_CHECKING Scheduler import for the new target class
    #    so the ``self: "SchedulerWeightUpdaterManager"`` annotation resolves
    #    under pyflakes.
    text = text.replace(
        "if TYPE_CHECKING:\n    from sglang.srt.managers.scheduler import Scheduler\n",
        "if TYPE_CHECKING:\n"
        "    from sglang.srt.managers.scheduler_components.weight_updater import SchedulerWeightUpdaterManager\n",
    )
    # Rewrite the 4 intra-mixin ``self.flush_cache_after_weight_update(recv_req)``
    # call sites to the explicit class-qualified form so the staticmethod
    # dispatches receive the manager as first arg.
    text = text.replace(
        "self.flush_cache_after_weight_update(recv_req)",
        "SchedulerUpdateWeightsMixin.flush_cache_after_weight_update(self, recv_req)",
    )
    mixin.write_text(text)

    # 4. In scheduler.py: add import, delete the original
    #    ``self.offload_tags = set()`` from
    #    ``init_watch_dog_memory_saver_input_blocker``, instantiate
    #    weight_updater before ``self.init_request_dispatcher()``, and rewire
    #    dp_attn_adapter's ``offload_tags`` kwarg.
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

    # Delete the original ``self.offload_tags = set()`` line (ownership migrates
    # to the manager).
    text = replace_call_site(
        text,
        old="        self.memory_saver_adapter = TorchMemorySaverAdapter.create(\n"
        "            enable=self.server_args.enable_memory_saver\n"
        "        )\n"
        "        self.offload_tags = set()\n",
        new="        self.memory_saver_adapter = TorchMemorySaverAdapter.create(\n"
        "            enable=self.server_args.enable_memory_saver\n"
        "        )\n",
    )

    # Instantiate weight_updater immediately before
    # ``self.init_request_dispatcher()``.
    text = replace_call_site(
        text,
        old="        # Init request dispatcher\n"
        "        self.init_request_dispatcher()\n",
        new=SCHEDULER_INIT_INSERT
        + "        # Init request dispatcher\n"
        "        self.init_request_dispatcher()\n",
    )

    # Rewire dp_attn_adapter's offload_tags arg.
    text = replace_call_site(
        text,
        old="            offload_tags=self.offload_tags,\n",
        new="            offload_tags=self.weight_updater.offload_tags,\n",
    )

    # 5. Rewrap the 10 RPC dispatch tuples directly into the staticmethod-form
    #    lambdas (no intermediate ``lambda req: self.method(req)`` step).
    for old, new in RPC_LAMBDA_WRAPS:
        text = replace_call_site(text, old=old, new=new)

    # 6. ``save_remote_model`` / ``save_sharded_model`` are invoked directly on
    #    ``Scheduler`` (not through the RPC dispatcher), so the staticmethod
    #    type-flip breaks their call sites. Add thin wrapper methods on
    #    ``Scheduler`` that forward to the staticmethod with the manager.
    text = replace_call_site(
        text,
        old="    def handle_rpc_request(self, recv_req: RpcReqInput):\n",
        new="    def save_remote_model(self, **kwargs):\n"
        "        SchedulerUpdateWeightsMixin.save_remote_model(self.weight_updater, kwargs)\n"
        "\n"
        "    def save_sharded_model(self, **kwargs):\n"
        "        SchedulerUpdateWeightsMixin.save_sharded_model(self.weight_updater, kwargs)\n"
        "\n"
        "    def handle_rpc_request(self, recv_req: RpcReqInput):\n",
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
