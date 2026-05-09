#!/usr/bin/env python3
"""Reproducible transform: extract `ModelRunner.update_expert_location` to a free
function `update_expert_location` in `sglang.srt.eplb.expert_location_updater`.

Strict-minimal mechanical extraction:
  - Free function body is byte-identical to the original method body, with
    `self.X` reads replaced by explicit kwargs and the only side-effecting
    write `self.update_weights_from_disk(...)` replaced by an injected
    `update_weights_from_disk_callable(...)` Callable kwarg (R4 compliance).
  - The original method on `ModelRunner` becomes a 1-line delegate so callers
    are unaffected.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/30"
TARGET_COMMIT = "tom_refactor/31"


def transform(dir_root: Path) -> None:
    elu = dir_root / "python/sglang/srt/eplb/expert_location_updater.py"
    text = elu.read_text()

    free_func = (
        "\n\n"
        "def update_expert_location(\n"
        "    *,\n"
        "    expert_location_updater,\n"
        "    model,\n"
        "    new_expert_location_metadata: ExpertLocationMetadata,\n"
        "    update_layer_ids: List[int],\n"
        "    nnodes: int,\n"
        "    tp_rank: int,\n"
        "    expert_backup_client,\n"
        "    update_weights_from_disk_callable,\n"
        "):\n"
        "    p2p_missing_logical_experts = expert_location_updater.update(\n"
        "        model.routed_experts_weights_of_layer,\n"
        "        new_expert_location_metadata,\n"
        "        update_layer_ids=update_layer_ids,\n"
        "        nnodes=nnodes,\n"
        "        rank=tp_rank,\n"
        "    )\n"
        "\n"
        "    if len(p2p_missing_logical_experts) > 0:\n"
        "        # Load the missing expert weights from disk\n"
        '        if callable(getattr(model, "generate_weight_name_filter", None)):\n'
        "            # Filter and load only missing expert weights\n"
        "            weight_name_filter = model.generate_weight_name_filter(\n"
        "                p2p_missing_logical_experts\n"
        "            )\n"
        "        else:\n"
        "            # Do a full reload from disk/DRAM\n"
        "            logger.info(\n"
        '                "[Elastic EP] Model does not implement generate_weight_name_filter. "\n'
        '                "Performing full weight reload."\n'
        "            )\n"
        "            weight_name_filter = None\n"
        "\n"
        "        if (\n"
        "            expert_backup_client is not None\n"
        "            and expert_backup_client.use_backup\n"
        "        ):\n"
        "            # Load the missing weights from the DRAM backup\n"
        "            expert_backup_client.update_weights(weight_name_filter)\n"
        "        else:\n"
        "            # Load the missing weights from disk\n"
        "            update_weights_from_disk_callable(\n"
        "                get_global_server_args().model_path,\n"
        "                get_global_server_args().load_format,\n"
        "                weight_name_filter=weight_name_filter,\n"
        "            )\n"
    )
    text = text.rstrip() + free_func
    elu.write_text(text)

    # ---- Update model_runner.py ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    old_method = (
        "    def update_expert_location(\n"
        "        self,\n"
        "        new_expert_location_metadata: ExpertLocationMetadata,\n"
        "        update_layer_ids: List[int],\n"
        "    ):\n"
        "        p2p_missing_logical_experts = self.expert_location_updater.update(\n"
        "            self.model.routed_experts_weights_of_layer,\n"
        "            new_expert_location_metadata,\n"
        "            update_layer_ids=update_layer_ids,\n"
        "            nnodes=self.server_args.nnodes,\n"
        "            rank=self.tp_rank,\n"
        "        )\n"
        "\n"
        "        if len(p2p_missing_logical_experts) > 0:\n"
        "            # Load the missing expert weights from disk\n"
        '            if callable(getattr(self.model, "generate_weight_name_filter", None)):\n'
        "                # Filter and load only missing expert weights\n"
        "                weight_name_filter = self.model.generate_weight_name_filter(\n"
        "                    p2p_missing_logical_experts\n"
        "                )\n"
        "            else:\n"
        "                # Do a full reload from disk/DRAM\n"
        "                logger.info(\n"
        '                    "[Elastic EP] Model does not implement generate_weight_name_filter. "\n'
        '                    "Performing full weight reload."\n'
        "                )\n"
        "                weight_name_filter = None\n"
        "\n"
        "            if (\n"
        "                self.expert_backup_client is not None\n"
        "                and self.expert_backup_client.use_backup\n"
        "            ):\n"
        "                # Load the missing weights from the DRAM backup\n"
        "                self.expert_backup_client.update_weights(weight_name_filter)\n"
        "            else:\n"
        "                # Load the missing weights from disk\n"
        "                self.update_weights_from_disk(\n"
        "                    get_global_server_args().model_path,\n"
        "                    get_global_server_args().load_format,\n"
        "                    weight_name_filter=weight_name_filter,\n"
        "                )\n"
    )
    assert old_method in text, "update_expert_location method not found"

    new_delegate = (
        "    def update_expert_location(\n"
        "        self,\n"
        "        new_expert_location_metadata: ExpertLocationMetadata,\n"
        "        update_layer_ids: List[int],\n"
        "    ):\n"
        "        update_expert_location(\n"
        "            expert_location_updater=self.expert_location_updater,\n"
        "            model=self.model,\n"
        "            new_expert_location_metadata=new_expert_location_metadata,\n"
        "            update_layer_ids=update_layer_ids,\n"
        "            nnodes=self.server_args.nnodes,\n"
        "            tp_rank=self.tp_rank,\n"
        "            expert_backup_client=self.expert_backup_client,\n"
        "            update_weights_from_disk_callable=self.update_weights_from_disk,\n"
        "        )\n"
    )
    text = text.replace(old_method, new_delegate)

    # Add import for the free function (alongside the existing
    # ExpertLocationUpdater import).
    old_import = (
        "from sglang.srt.eplb.expert_location_updater import ExpertLocationUpdater\n"
    )
    new_import = (
        "from sglang.srt.eplb.expert_location_updater import (\n"
        "    ExpertLocationUpdater,\n"
        "    update_expert_location,\n"
        ")\n"
    )
    assert old_import in text, "ExpertLocationUpdater import not found"
    text = text.replace(old_import, new_import)

    mr.write_text(text)

    git_add_and_commit(
        "Extract update_expert_location to free function in eplb.expert_location_updater",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
