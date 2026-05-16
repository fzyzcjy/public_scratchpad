#!/usr/bin/env python3
"""Migrate ``SchedulerUpdateWeightsMixin`` to ``SchedulerWeightUpdaterManager``
at ``scheduler_components/weight_updater.py`` (composition).

- Ctor takes 4 narrow协作者 kwargs + 2 Callable kwargs (``flush_cache`` /
  ``is_fully_idle``, both god-class methods on Scheduler — per CLAUDE.md ch4
  injected as Callable rather than via ``_sched`` back-ref).
- Ownership migration: ``self.offload_tags = set()`` moves from
  Scheduler.``init_watch_dog_memory_saver_input_blocker`` to the new class's
  ``__init__`` body. ``SchedulerDPAttnAdapter`` (introduced in
  ``migrate-dp-attn-mixin``) is updated to take ``offload_tags`` from
  ``self.weight_updater.offload_tags``; ``self.weight_updater`` is constructed
  before ``self.dp_attn_adapter``.
- ``stashed_model_static_state`` is migrated as-is (still uses ``setattr`` /
  ``del`` semantics — bug fix to introduce a ``None`` placeholder is deferred
  to Ch2).
- Module-level helpers ``_export_static_state`` / ``_import_static_state`` are
  preserved verbatim.
- 12 RPC dispatch callsites in ``init_request_dispatcher`` updated to
  ``self.weight_updater.<method>`` form. ``save_remote_model`` /
  ``save_sharded_model`` have no Scheduler-level callers — left as
  ``self.weight_updater.X`` accessible methods only.
- No method renames; no privacy flips.
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

ID = "migrate-update-weights-mixin"
SUBJECT = "Migrate SchedulerUpdateWeightsMixin to SchedulerWeightUpdaterManager (composition)"
BODY = """\
Move ``SchedulerUpdateWeightsMixin`` (12 methods + 2 module-level helpers) to
``SchedulerWeightUpdaterManager`` at
``scheduler_components/weight_updater.py``. Scheduler holds it as
``self.weight_updater``.

Ctor takes narrow typed kwargs per CLAUDE.md ch4: 4 collaborators
(``tp_worker``, ``draft_worker``, ``tp_cpu_group``, ``memory_saver_adapter``)
+ 2 ``Callable`` kwargs (``flush_cache``, ``is_fully_idle`` — Scheduler
methods injected per CLAUDE.md ch4).

Ownership migration:
- ``offload_tags`` (was ``self.offload_tags = set()`` on Scheduler) moves to
  the new class's ``__init__``. ``SchedulerDPAttnAdapter`` is rewired to take
  it from ``self.weight_updater.offload_tags``; the weight updater is
  constructed before the dp_attn_adapter so the reference resolves.

12 RPC dispatch callsites updated to ``self.weight_updater.<method>``. No
method renames or privacy flips.

No behavior change.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


NEW_CLASS_HEADER = '''\
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
        flush_cache: "Callable[..., bool]",
        is_fully_idle: "Callable[..., bool]",
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


# RPC dispatch callsites — 12 lines in init_request_dispatcher.
RPC_DISPATCH_REPLACEMENTS = [
    (
        "                (UpdateWeightFromDiskReqInput, self.update_weights_from_disk),\n",
        "                (UpdateWeightFromDiskReqInput, self.weight_updater.update_weights_from_disk),\n",
    ),
    (
        "                (InitWeightsUpdateGroupReqInput, self.init_weights_update_group),\n",
        "                (InitWeightsUpdateGroupReqInput, self.weight_updater.init_weights_update_group),\n",
    ),
    (
        "                (DestroyWeightsUpdateGroupReqInput, self.destroy_weights_update_group),\n",
        "                (DestroyWeightsUpdateGroupReqInput, self.weight_updater.destroy_weights_update_group),\n",
    ),
    (
        "                    self.update_weights_from_distributed,\n",
        "                    self.weight_updater.update_weights_from_distributed,\n",
    ),
    (
        "                (UpdateWeightsFromTensorReqInput, self.update_weights_from_tensor),\n",
        "                (UpdateWeightsFromTensorReqInput, self.weight_updater.update_weights_from_tensor),\n",
    ),
    (
        "                (UpdateWeightsFromIPCReqInput, self.update_weights_from_ipc),\n",
        "                (UpdateWeightsFromIPCReqInput, self.weight_updater.update_weights_from_ipc),\n",
    ),
    (
        "                (GetWeightsByNameReqInput, self.get_weights_by_name),\n",
        "                (GetWeightsByNameReqInput, self.weight_updater.get_weights_by_name),\n",
    ),
    (
        "                (ReleaseMemoryOccupationReqInput, self.release_memory_occupation),\n",
        "                (ReleaseMemoryOccupationReqInput, self.weight_updater.release_memory_occupation),\n",
    ),
    (
        "                (ResumeMemoryOccupationReqInput, self.resume_memory_occupation),\n",
        "                (ResumeMemoryOccupationReqInput, self.weight_updater.resume_memory_occupation),\n",
    ),
    (
        "                (CheckWeightsReqInput, self.check_weights),\n",
        "                (CheckWeightsReqInput, self.weight_updater.check_weights),\n",
    ),
]


def transform(wt: Path) -> None:
    src = wt / "python/sglang/srt/managers/scheduler_update_weights_mixin.py"
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    pkg_init = wt / "python/sglang/srt/managers/scheduler_components/__init__.py"
    target = wt / "python/sglang/srt/managers/scheduler_components/weight_updater.py"

    pkg_init.parent.mkdir(parents=True, exist_ok=True)
    pkg_init.write_text("")

    text = src.read_text()
    if "class SchedulerUpdateWeightsMixin:\n" not in text:
        raise RuntimeError("UpdateWeights class header anchor mismatch")
    text = text.replace("class SchedulerUpdateWeightsMixin:\n", NEW_CLASS_HEADER)
    # Need ``Callable`` import on the new file.
    text = text.replace(
        "from typing import TYPE_CHECKING, Tuple\n",
        "from typing import TYPE_CHECKING, Callable, Tuple\n",
    )

    # Drop ``: Scheduler`` annotations.
    text = text.replace("self: Scheduler", "self")

    # Drop TYPE_CHECKING Scheduler import + the now-empty ``if TYPE_CHECKING:``
    # block (would be a syntax error otherwise).
    text = text.replace(
        "if TYPE_CHECKING:\n    from sglang.srt.managers.scheduler import Scheduler\n\n",
        "",
    )
    # Also drop the now-unused TYPE_CHECKING import.
    text = text.replace(
        "from typing import TYPE_CHECKING, Callable, Tuple\n",
        "from typing import Callable, Tuple\n",
    )

    target.write_text(text)
    src.unlink()

    # Update Scheduler.
    text = sched.read_text()
    text = text.replace(
        "from sglang.srt.managers.scheduler_update_weights_mixin import (\n"
        "    SchedulerUpdateWeightsMixin,\n"
        ")\n",
        "",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.managers.scheduler_components.dp_attn import (\n    SchedulerDPAttnAdapter,\n)\n",
        addition=(
            "from sglang.srt.managers.scheduler_components.weight_updater import (\n"
            "    SchedulerWeightUpdaterManager,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old="    SchedulerUpdateWeightsMixin,\n",
        new="",
    )
    # Remove ``self.offload_tags = set()`` from init_watch_dog_memory_saver_input_blocker.
    text = replace_call_site(
        text,
        old="        self.offload_tags = set()\n",
        new="",
    )
    # Insert weight_updater ctor BEFORE ``self.init_request_dispatcher()``,
    # which reads ``self.weight_updater.<rpc>`` for the dispatch table. (The
    # dp_attn_adapter ctor is later in __init__ and reads ``offload_tags`` from
    # the weight_updater, which still resolves because we construct earlier.)
    text = replace_call_site(
        text,
        old="        # Init request dispatcher\n        self.init_request_dispatcher()\n",
        new=SCHEDULER_INIT_INSERT_WEIGHT_UPDATER
        + "        # Init request dispatcher\n        self.init_request_dispatcher()\n",
    )
    # Rewire dp_attn_adapter's offload_tags arg from self.offload_tags to
    # self.weight_updater.offload_tags.
    text = replace_call_site(
        text,
        old="            offload_tags=self.offload_tags,\n",
        new="            offload_tags=self.weight_updater.offload_tags,\n",
    )
    # 10 RPC dispatch callsite rewrites.
    for old, new in RPC_DISPATCH_REPLACEMENTS:
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
