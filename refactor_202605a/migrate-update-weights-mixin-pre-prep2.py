#!/usr/bin/env python3
"""Pure dispatch-tuple reshape pre-prep2 for
``migrate-update-weights-mixin``: rewrap the 13 RPC dispatch tuples in
``Scheduler.init_request_dispatcher`` that currently use direct bound
method refs (e.g. ``(UpdateWeightFromDiskReqInput,
self.update_weights_from_disk)``) into lambda form
(``(UpdateWeightFromDiskReqInput, lambda req:
self.update_weights_from_disk(req))``). This is a no-op-equivalent
reshape that isolates the dispatch tuple shape from the upcoming
``@staticmethod`` typeflip in ``-prep``.

In ``-prep``, each lambda body grows the ``self.weight_updater`` first
arg so it dispatches to the post-typeflip staticmethod form
(``lambda req: self.update_weights_from_disk(self.weight_updater,
req)``). In ``-move``, the lambdas collapse to direct refs
(``self.weight_updater.update_weights_from_disk``).
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

ID = "migrate-update-weights-mixin-pre-prep2"
SUBJECT = "Wrap weight-update RPC dispatch tuples in lambdas (dispatch tuple reshape)"
BODY = """\
Pure dispatch-tuple reshape pre-prep2 for ``migrate-update-weights-mixin``.

Rewrap the weight-update RPC dispatch tuples in
``Scheduler.init_request_dispatcher`` that currently use direct bound
method refs (e.g. ``(UpdateWeightFromDiskReqInput,
self.update_weights_from_disk)``) into lambda form (``(MessageClass,
lambda req: self.method_name(req))``). Semantically identical at this
commit: the lambda still resolves to the mixin method on Scheduler.

Isolating the dispatch tuple shape from the upcoming ``@staticmethod``
typeflip lets the ``-prep`` commit grow the lambda body with the
``self.weight_updater`` first arg without also having to reshape the
tuple form. The ``-move`` commit then collapses each lambda to a direct
``self.weight_updater.<method>`` reference (pure prefix transformation).

Sites covered: ``flush_cache_after_weight_update`` is not in the
dispatcher (called from within the mixin); the RPC sites here are
``update_weights_from_disk``, ``init_weights_update_group``,
``destroy_weights_update_group``, ``update_weights_from_distributed``,
``update_weights_from_tensor``, ``update_weights_from_ipc``,
``get_weights_by_name``, ``release_memory_occupation``,
``resume_memory_occupation``, ``check_weights``, plus the remaining
entries registered via the dispatcher tuple — see
``init_request_dispatcher`` source.
"""
AREA = "mech_scheduler"
BASE = "tom_refactor_202605a/primary/mech_preflight"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


# 10 RPC dispatch sites. We rewrap each direct method ref into a lambda.
# (Sites already in lambda form, or methods not in the dispatcher tuple, are
# left alone.) The first ``UpdateWeightsFromDistributedReqInput`` site is in
# multi-line form because the message-class name is long; black breaks it.
RPC_LAMBDA_WRAPS = [
    (
        "                (UpdateWeightFromDiskReqInput, self.update_weights_from_disk),\n",
        "                (\n"
        "                    UpdateWeightFromDiskReqInput,\n"
        "                    lambda req: self.update_weights_from_disk(req),\n"
        "                ),\n",
    ),
    (
        "                (InitWeightsUpdateGroupReqInput, self.init_weights_update_group),\n",
        "                (\n"
        "                    InitWeightsUpdateGroupReqInput,\n"
        "                    lambda req: self.init_weights_update_group(req),\n"
        "                ),\n",
    ),
    (
        "                (DestroyWeightsUpdateGroupReqInput, self.destroy_weights_update_group),\n",
        "                (\n"
        "                    DestroyWeightsUpdateGroupReqInput,\n"
        "                    lambda req: self.destroy_weights_update_group(req),\n"
        "                ),\n",
    ),
    (
        "                (\n"
        "                    UpdateWeightsFromDistributedReqInput,\n"
        "                    self.update_weights_from_distributed,\n"
        "                ),\n",
        "                (\n"
        "                    UpdateWeightsFromDistributedReqInput,\n"
        "                    lambda req: self.update_weights_from_distributed(req),\n"
        "                ),\n",
    ),
    (
        "                (UpdateWeightsFromTensorReqInput, self.update_weights_from_tensor),\n",
        "                (\n"
        "                    UpdateWeightsFromTensorReqInput,\n"
        "                    lambda req: self.update_weights_from_tensor(req),\n"
        "                ),\n",
    ),
    (
        "                (UpdateWeightsFromIPCReqInput, self.update_weights_from_ipc),\n",
        "                (\n"
        "                    UpdateWeightsFromIPCReqInput,\n"
        "                    lambda req: self.update_weights_from_ipc(req),\n"
        "                ),\n",
    ),
    (
        "                (GetWeightsByNameReqInput, self.get_weights_by_name),\n",
        "                (\n"
        "                    GetWeightsByNameReqInput,\n"
        "                    lambda req: self.get_weights_by_name(req),\n"
        "                ),\n",
    ),
    (
        "                (ReleaseMemoryOccupationReqInput, self.release_memory_occupation),\n",
        "                (\n"
        "                    ReleaseMemoryOccupationReqInput,\n"
        "                    lambda req: self.release_memory_occupation(req),\n"
        "                ),\n",
    ),
    (
        "                (ResumeMemoryOccupationReqInput, self.resume_memory_occupation),\n",
        "                (\n"
        "                    ResumeMemoryOccupationReqInput,\n"
        "                    lambda req: self.resume_memory_occupation(req),\n"
        "                ),\n",
    ),
    (
        "                (CheckWeightsReqInput, self.check_weights),\n",
        "                (\n"
        "                    CheckWeightsReqInput,\n"
        "                    lambda req: self.check_weights(req),\n"
        "                ),\n",
    ),
]


def transform(wt: Path) -> None:
    sched = wt / "python/sglang/srt/managers/scheduler.py"
    text = sched.read_text()
    for old, new in RPC_LAMBDA_WRAPS:
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
