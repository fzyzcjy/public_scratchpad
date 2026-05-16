#!/usr/bin/env python3
"""Inplace prep for ``migrate-update-weights-mixin``: build the
``SchedulerWeightUpdaterManager`` (@dataclass) skeleton at
``scheduler_components/weight_updater.py`` (ctor with 4 collaborator kwargs
+ 2 Callable kwargs; ``self.offload_tags`` field migrated in), instantiate
in ``Scheduler.__init__`` BEFORE ``self.init_request_dispatcher()`` (so
``self.weight_updater`` exists by the time dispatch lambdas resolve it).
Delete ``self.offload_tags = set()`` from Scheduler (pre-prep1 relocated it
near here; this commit migrates ownership to the manager). Rewire
``dp_attn_adapter`` ctor's ``offload_tags`` kwarg to
``self.weight_updater.offload_tags``. Convert 13 mixin methods to
``@staticmethod`` with ``self: "SchedulerWeightUpdaterManager"``. Grow the
10 pre-prep2 dispatch lambdas with the ``self.weight_updater`` first arg
so they invoke the staticmethod form.

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
  Scheduler per pre-prep1).
- Instantiate ``self.weight_updater = SchedulerWeightUpdaterManager(...)``
  in ``Scheduler.__init__`` BEFORE ``self.init_request_dispatcher()``
  (so the dispatch lambdas can resolve ``self.weight_updater`` lazily).
- Delete ``self.offload_tags = set()`` from Scheduler (pre-prep1
  relocated it next to the future ctor; this commit drops the line
  since ownership now lives on the manager).
- Rewire ``dp_attn_adapter`` ctor's ``offload_tags`` kwarg from
  ``self.offload_tags`` to ``self.weight_updater.offload_tags``.
- In the mixin, type-flip every weight-update method to ``@staticmethod``
  with ``self: "SchedulerWeightUpdaterManager"``. Body bytes unchanged
  (no runtime-mutable Scheduler state is read; the mixin already
  collaborates only through ``self.tp_worker`` / ``self.draft_worker``
  / etc., which become the manager's own fields).
- Grow the pre-prep2 dispatch lambdas: each lambda body gains the
  ``self.weight_updater`` first arg so it invokes the staticmethod-form
  mixin method, e.g. ``lambda req: self.update_weights_from_disk(req)``
  → ``lambda req: self.update_weights_from_disk(self.weight_updater,
  req)``.

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


# 10 pre-prep2 lambdas grow to include ``self.weight_updater`` as the
# staticmethod ``self`` arg. Each replacement targets the existing lambda
# body produced by pre-prep2.
RPC_LAMBDA_PAIRS = [
    (
        "                    lambda req: self.update_weights_from_disk(req),\n",
        "                    lambda req: self.update_weights_from_disk(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n",
    ),
    (
        "                    lambda req: self.init_weights_update_group(req),\n",
        "                    lambda req: self.init_weights_update_group(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n",
    ),
    (
        "                    lambda req: self.destroy_weights_update_group(req),\n",
        "                    lambda req: self.destroy_weights_update_group(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n",
    ),
    (
        "                    lambda req: self.update_weights_from_distributed(req),\n",
        "                    lambda req: self.update_weights_from_distributed(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n",
    ),
    (
        "                    lambda req: self.update_weights_from_tensor(req),\n",
        "                    lambda req: self.update_weights_from_tensor(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n",
    ),
    (
        "                    lambda req: self.update_weights_from_ipc(req),\n",
        "                    lambda req: self.update_weights_from_ipc(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n",
    ),
    (
        "                    lambda req: self.get_weights_by_name(req),\n",
        "                    lambda req: self.get_weights_by_name(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n",
    ),
    (
        "                    lambda req: self.release_memory_occupation(req),\n",
        "                    lambda req: self.release_memory_occupation(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n",
    ),
    (
        "                    lambda req: self.resume_memory_occupation(req),\n",
        "                    lambda req: self.resume_memory_occupation(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n",
    ),
    (
        "                    lambda req: self.check_weights(req),\n",
        "                    lambda req: self.check_weights(\n"
        "                        self.weight_updater, req\n"
        "                    ),\n",
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
    mixin.write_text(text)

    # 4. In scheduler.py: add import, instantiate weight_updater, delete the
    #    relocated ``self.offload_tags = set()`` (ownership migrated to
    #    manager), rewire dp_attn_adapter's ``offload_tags`` kwarg.
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

    # Replace pre-prep1's relocated ``self.offload_tags = set()\n\n`` + the
    # following ``# Init request dispatcher\n        self.init_request_dispatcher()\n``
    # with the weight_updater ctor + dispatcher call.
    text = replace_call_site(
        text,
        old="        self.offload_tags = set()\n"
        "\n"
        "        # Init request dispatcher\n"
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

    # 5. 10 pre-prep2 lambdas grow with ``self.weight_updater`` first arg.
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
