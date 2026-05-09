#!/usr/bin/env python3
"""Delete `update_expert_location` from ModelRunner; the body was already a
1-call delegate to the imported `update_expert_location` in
`expert_location_updater.py`. Update the sole external caller (eplb_manager.py)
to call the imported free function directly with explicit kwargs (assembled
from `self._model_runner.X`).

The `update_weights_from_disk_callable` kwarg is rebuilt at the caller site
using `functools.partial(_free_update_weights_from_disk, model_runner_ref=...)`.

Usage:
    uv run --python 3.12 tom_refactor_31.py run
    uv run --python 3.12 tom_refactor_31.py verify
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import (
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

BASE = "tom_refactor/30"
TARGET = "tom_refactor/31"


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    eplb = wt / "python/sglang/srt/eplb/eplb_manager.py"

    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="update_expert_location"
    )
    cut_lines(mr, s, e)

    # eplb_manager.py: import update_expert_location + functools + free
    # update_weights_from_disk; rewrite the caller.
    text = eplb.read_text()
    text = insert_after(
        text,
        anchor="import time\n",
        addition="import functools\n",
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.eplb.expert_location import ExpertLocationMetadata\n",
        addition=(
            "from sglang.srt.eplb.expert_location_updater import update_expert_location\n"
            "from sglang.srt.model_executor.weight_updater import (\n"
            "    update_weights_from_disk as _free_update_weights_from_disk,\n"
            ")\n"
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "            self._model_runner.update_expert_location(\n"
            "                expert_location_metadata,\n"
            "                update_layer_ids=update_layer_ids,\n"
            "            )\n"
        ),
        new=(
            "            update_expert_location(\n"
            "                expert_location_updater=self._model_runner.expert_location_updater,\n"
            "                model=self._model_runner.model,\n"
            "                new_expert_location_metadata=expert_location_metadata,\n"
            "                update_layer_ids=update_layer_ids,\n"
            "                nnodes=self._model_runner.server_args.nnodes,\n"
            "                tp_rank=self._model_runner.tp_rank,\n"
            "                expert_backup_client=self._model_runner.expert_backup_client,\n"
            "                update_weights_from_disk_callable=functools.partial(\n"
            "                    _free_update_weights_from_disk,\n"
            "                    model_runner_ref=self._model_runner,\n"
            "                ),\n"
            "            )\n"
        ),
    )
    eplb.write_text(text)

    git_add_and_commit(
        "Inline ModelRunner.update_expert_location into the eplb_manager caller",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
