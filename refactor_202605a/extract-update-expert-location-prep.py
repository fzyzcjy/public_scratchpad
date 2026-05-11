#!/usr/bin/env python3
"""Prep stage for extract-update-expert-location (MECH_COMMIT_SPLIT §"二段式"):

In-place reshape of ``ModelRunner.update_expert_location``:
- Rename to ``update_expert_location_with_recovery`` (per
  EXECUTION_GUIDE rename exception — disambiguates from the existing
  ``ExpertLocationUpdater.update`` method).
- @staticmethod + kwarg-only signature.
- Replace 6 ``self.X`` reads with kwargs.
- Replace the inner ``self.weight_updater.update_weights_from_disk(...)`` call
  with an ``update_weights_from_disk_callable(...)`` callback kwarg.

Call site in ``eplb_manager.py`` rewritten to
``ModelRunner.update_expert_location_with_recovery(...)``.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, replace_call_site
from _runner import run_pr

ID = "extract-update-expert-location-prep"
SUBJECT = "Prep update_expert_location for extraction: rename + @staticmethod + kwargs + callback"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/we-move-save-get"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    eplb = wt / "python/sglang/srt/eplb/eplb_manager.py"

    text = mr.read_text()
    start, end = find_method_lines(
        text, class_name="ModelRunner", method_name="update_expert_location"
    )
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    new_method = (
        method
        .replace(
            "    def update_expert_location(\n"
            "        self,\n"
            "        new_expert_location_metadata: ExpertLocationMetadata,\n"
            "        update_layer_ids: List[int],\n"
            "    ):\n",
            "    @staticmethod\n"
            "    def update_expert_location_with_recovery(\n"
            "        *,\n"
            "        expert_location_updater: ExpertLocationUpdater,\n"
            "        model: nn.Module,\n"
            "        new_expert_location_metadata: ExpertLocationMetadata,\n"
            "        update_layer_ids: List[int],\n"
            "        nnodes: int,\n"
            "        tp_rank: int,\n"
            "        expert_backup_client,\n"
            "        update_weights_from_disk_callable,\n"
            "    ):\n",
        )
        .replace("self.expert_location_updater", "expert_location_updater")
        .replace("self.server_args.nnodes", "nnodes")
        .replace("self.tp_rank", "tp_rank")
        .replace("self.expert_backup_client", "expert_backup_client")
        .replace("self.model", "model")
        .replace(
            "                self.weight_updater.update_weights_from_disk(\n"
            "                    get_global_server_args().model_path,\n"
            "                    get_global_server_args().load_format,\n"
            "                    weight_name_filter=weight_name_filter,\n"
            "                )",
            "                update_weights_from_disk_callable(\n"
            "                    get_global_server_args().model_path,\n"
            "                    get_global_server_args().load_format,\n"
            "                    weight_name_filter=weight_name_filter,\n"
            "                )",
        )
    )
    text = "".join(lines[:start]) + new_method + "".join(lines[end:])
    mr.write_text(text)

    text = eplb.read_text()
    text = replace_call_site(
        text,
        old=(
            "            self._model_runner.update_expert_location(\n"
            "                expert_location_metadata,\n"
            "                update_layer_ids=update_layer_ids,\n"
            "            )\n"
        ),
        new=(
            "            ModelRunner.update_expert_location_with_recovery(\n"
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
    # ``ModelRunner`` is in this module only under TYPE_CHECKING (to break a
    # cycle). Rather than promote it to top-level (which would cause the
    # cycle), use a function-local import on the line above the qualified
    # call. The ``-move`` commit drops both.
    text = text.replace(
        "            ModelRunner.update_expert_location_with_recovery(\n",
        "            from sglang.srt.model_executor.model_runner import ModelRunner\n"
        "\n"
        "            ModelRunner.update_expert_location_with_recovery(\n",
        1,
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
