#!/usr/bin/env python3
"""Cut `update_expert_location` from ModelRunner; paste as a free function in
`eplb/expert_location_updater.py`. The body has 6 self.X reads + 1 call to
`weight_updater.update_weights_from_disk(model_runner_ref=self, ...)`.

The 6 self.X reads become explicit kwargs (R1). The `weight_updater` call,
which originally bound `self` as `model_runner_ref`, is parameterised as a
`update_weights_from_disk_callable` kwarg; the eplb_manager caller bakes
`model_runner_ref=self._model_runner` via ``functools.partial``.

Usage:
    uv run --python 3.12 extract-update-expert-location.py run
    uv run --python 3.12 extract-update-expert-location.py verify
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
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-update-expert-location"
SUBJECT = "Extract ModelRunner.update_expert_location to free function in expert_location_updater"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/we-move-save-get"
AREA_BRANCH = f"tom_refactor_202605a/raw/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    elu = wt / "python/sglang/srt/eplb/expert_location_updater.py"
    eplb = wt / "python/sglang/srt/eplb/eplb_manager.py"

    # Add `from torch import nn` to expert_location_updater.py for the new
    # `model: nn.Module` annotation on the extracted free function.
    elu_text = elu.read_text()
    if "from torch import nn\n" not in elu_text:
        elu_text = insert_after(
            elu_text,
            anchor="import torch\n",
            addition="from torch import nn\n",
        )
        elu.write_text(elu_text)

    # ---- Cut method body from ModelRunner. ----
    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="update_expert_location"
    )
    method_text = cut_lines(mr, s, e)

    # ---- Convert to free function (signature swap + self.X -> kwargs). ----
    # Original signature:
    #     def update_expert_location(
    #         self,
    #         new_expert_location_metadata: ExpertLocationMetadata,
    #         update_layer_ids: List[int],
    #     ):
    func_text = (
        dedent_method_to_function(method_text)
        .replace(
            "def update_expert_location(\n"
            "    self,\n"
            "    new_expert_location_metadata: ExpertLocationMetadata,\n"
            "    update_layer_ids: List[int],\n"
            "):\n",
            # Preserve original typed params `new_expert_location_metadata` /
            # `update_layer_ids` exactly as on the source method; new kwargs
            # get fresh annotations.
            "def update_expert_location(\n"
            "    *,\n"
            "    expert_location_updater: ExpertLocationUpdater,\n"
            "    model: nn.Module,\n"
            "    new_expert_location_metadata: ExpertLocationMetadata,\n"
            "    update_layer_ids: List[int],\n"
            "    nnodes: int,\n"
            "    tp_rank: int,\n"
            "    expert_backup_client,\n"
            "    update_weights_from_disk_callable,\n"
            "):\n",
        )
        .replace("self.expert_location_updater", "expert_location_updater")
        .replace("self.server_args.nnodes", "nnodes")
        .replace("self.tp_rank", "tp_rank")
        .replace("self.expert_backup_client", "expert_backup_client")
        .replace("self.model", "model")
        # After /24-/30 reshuffle, the body calls
        # `self.weight_updater.update_weights_from_disk(...)` (instance method
        # on WeightUpdater, positional args). Free-function form takes a
        # `update_weights_from_disk_callable` kwarg; caller (eplb_manager)
        # passes the bound method directly.
        # NOTE: indentation is 12 spaces (one `dedent_method_to_function` level
        # already stripped from the original 16-space deeply-nested block).
        .replace(
            "            self.weight_updater.update_weights_from_disk(\n"
            "                get_global_server_args().model_path,\n"
            "                get_global_server_args().load_format,\n"
            "                weight_name_filter=weight_name_filter,\n"
            "            )",
            "            update_weights_from_disk_callable(\n"
            "                get_global_server_args().model_path,\n"
            "                get_global_server_args().load_format,\n"
            "                weight_name_filter=weight_name_filter,\n"
            "            )",
        )
    )

    append_to_file(elu, func_text)

    # ---- eplb_manager.py: import + rewrite the sole caller. ----
    text = eplb.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.eplb.expert_location import ExpertLocationMetadata\n",
        addition=(
            "from sglang.srt.eplb.expert_location_updater import update_expert_location\n"
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
            "                update_weights_from_disk_callable=self._model_runner.weight_updater.update_weights_from_disk,\n"
            "            )\n"
        ),
    )
    eplb.write_text(text)

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
