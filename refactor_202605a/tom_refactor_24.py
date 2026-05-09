#!/usr/bin/env python3
"""Reproducible transform: extract `init_weights_update_group` and
`destroy_weights_update_group` from `ModelRunner` into free functions in a new
`sglang.srt.model_executor.weight_updater` module. The ModelRunner methods
become 1-line delegates that pass `self._model_update_group` and other small
state explicitly via kwargs.

Run from the repo root:
    python3 /tmp/transform_weight_updater_groups.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/23"
TARGET_COMMIT = "tom_refactor/24"


NEW_FILE_CONTENT = '''from __future__ import annotations

import logging

import torch

from sglang.srt.utils import init_custom_process_group
from sglang.srt.utils.network import NetworkAddress

logger = logging.getLogger(__name__)


def init_weights_update_group(
    *,
    _model_update_group,
    tp_rank,
    master_address,
    master_port,
    rank_offset,
    world_size,
    group_name,
    backend="nccl",
):
    """Initialize the Torch process group for model parameter updates.

    `_model_update_group` is used in the RLHF workflow, where rank
    0 is the actor model in the training engine, and the other ranks are
    the inference engine, which is used for rollout.

    In the RLHF workflow, the training engine updates the model
    weights/parameters online, and broadcasts them to the inference
    engine through the `_model_update_group` process group.
    """
    assert (
        torch.distributed.is_initialized()
    ), "Default torch process group must be initialized"
    assert group_name != "", "Group name cannot be empty"

    rank = rank_offset + tp_rank

    logger.info(
        f"init custom process group: master_address={master_address}, master_port={master_port}, "
        f"rank_offset={rank_offset}, rank={rank}, world_size={world_size}, group_name={group_name}, backend={backend}"
    )

    try:
        na = NetworkAddress(master_address, master_port)
        _model_update_group[group_name] = init_custom_process_group(
            backend=backend,
            init_method=na.to_tcp(),
            world_size=world_size,
            rank=rank,
            group_name=group_name,
        )
        return True, "Succeeded to initialize custom process group."
    except Exception as e:
        message = f"Failed to initialize custom process group: {e}."
        logger.error(message)
        return False, message


def destroy_weights_update_group(*, _model_update_group, group_name):
    try:
        if group_name in _model_update_group:
            pg = _model_update_group.pop(group_name)
            torch.distributed.destroy_process_group(pg)
            return True, "Succeeded to destroy custom process group."
        else:
            return False, "The group to be destroyed does not exist."
    except Exception as e:
        message = f"Failed to destroy custom process group: {e}."
        logger.error(message)
        return False, message
'''


def transform(dir_root: Path) -> None:
    # --- Step 1: create new weight_updater.py ---
    new_file = dir_root / "python/sglang/srt/model_executor/weight_updater.py"
    new_file.write_text(NEW_FILE_CONTENT)

    # --- Step 2: update model_runner.py ---
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Add import for the two free functions.
    old_import_anchor = (
        "from sglang.srt.model_executor.cpu_graph_runner import CPUGraphRunner\n"
    )
    assert old_import_anchor in text, "CPUGraphRunner import anchor not found"
    text = text.replace(
        old_import_anchor,
        old_import_anchor
        + "from sglang.srt.model_executor.weight_updater import (\n"
        "    destroy_weights_update_group as _free_destroy_weights_update_group,\n"
        "    init_weights_update_group as _free_init_weights_update_group,\n"
        ")\n",
    )

    # Replace init_weights_update_group body with a 1-line delegate (after the docstring).
    old_init_method = (
        '    def init_weights_update_group(\n'
        '        self,\n'
        '        master_address,\n'
        '        master_port,\n'
        '        rank_offset,\n'
        '        world_size,\n'
        '        group_name,\n'
        '        backend="nccl",\n'
        '    ):\n'
        '        """Initialize the Torch process group for model parameter updates.\n'
        '\n'
        '        `_model_update_group` is used in the RLHF workflow, where rank\n'
        '        0 is the actor model in the training engine, and the other ranks are\n'
        '        the inference engine, which is used for rollout.\n'
        '\n'
        '        In the RLHF workflow, the training engine updates the model\n'
        '        weights/parameters online, and broadcasts them to the inference\n'
        '        engine through the `_model_update_group` process group.\n'
        '        """\n'
        '        assert (\n'
        '            torch.distributed.is_initialized()\n'
        '        ), "Default torch process group must be initialized"\n'
        '        assert group_name != "", "Group name cannot be empty"\n'
        '\n'
        '        rank = rank_offset + self.tp_rank\n'
        '\n'
        '        logger.info(\n'
        '            f"init custom process group: master_address={master_address}, master_port={master_port}, "\n'
        '            f"rank_offset={rank_offset}, rank={rank}, world_size={world_size}, group_name={group_name}, backend={backend}"\n'
        '        )\n'
        '\n'
        '        try:\n'
        '            na = NetworkAddress(master_address, master_port)\n'
        '            self._model_update_group[group_name] = init_custom_process_group(\n'
        '                backend=backend,\n'
        '                init_method=na.to_tcp(),\n'
        '                world_size=world_size,\n'
        '                rank=rank,\n'
        '                group_name=group_name,\n'
        '            )\n'
        '            return True, "Succeeded to initialize custom process group."\n'
        '        except Exception as e:\n'
        '            message = f"Failed to initialize custom process group: {e}."\n'
        '            logger.error(message)\n'
        '            return False, message\n'
    )
    new_init_method = (
        '    def init_weights_update_group(\n'
        '        self,\n'
        '        master_address,\n'
        '        master_port,\n'
        '        rank_offset,\n'
        '        world_size,\n'
        '        group_name,\n'
        '        backend="nccl",\n'
        '    ):\n'
        '        return _free_init_weights_update_group(\n'
        '            _model_update_group=self._model_update_group,\n'
        '            tp_rank=self.tp_rank,\n'
        '            master_address=master_address,\n'
        '            master_port=master_port,\n'
        '            rank_offset=rank_offset,\n'
        '            world_size=world_size,\n'
        '            group_name=group_name,\n'
        '            backend=backend,\n'
        '        )\n'
    )
    assert old_init_method in text, "init_weights_update_group body not found"
    text = text.replace(old_init_method, new_init_method)

    # Replace destroy_weights_update_group body with delegate.
    old_destroy_method = (
        '    def destroy_weights_update_group(self, group_name):\n'
        '        try:\n'
        '            if group_name in self._model_update_group:\n'
        '                pg = self._model_update_group.pop(group_name)\n'
        '                torch.distributed.destroy_process_group(pg)\n'
        '                return True, "Succeeded to destroy custom process group."\n'
        '            else:\n'
        '                return False, "The group to be destroyed does not exist."\n'
        '        except Exception as e:\n'
        '            message = f"Failed to destroy custom process group: {e}."\n'
        '            logger.error(message)\n'
        '            return False, message\n'
    )
    new_destroy_method = (
        '    def destroy_weights_update_group(self, group_name):\n'
        '        return _free_destroy_weights_update_group(\n'
        '            _model_update_group=self._model_update_group,\n'
        '            group_name=group_name,\n'
        '        )\n'
    )
    assert old_destroy_method in text, "destroy_weights_update_group body not found"
    text = text.replace(old_destroy_method, new_destroy_method)

    mr.write_text(text)

    git_add_and_commit(
        "Extract weights update group lifecycle to free functions in weight_updater",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
