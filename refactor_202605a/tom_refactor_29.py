#!/usr/bin/env python3
"""Reproducible transform: extract `init_weights_send_group_for_remote_instance`
and `send_weights_to_remote_instance` from `ModelRunner` into free functions in
a new `sglang.srt.model_executor.weight_exporter` module. The ModelRunner
methods become 1-line delegates that pass the minimal state explicitly via
kwargs (`model`, `_weights_send_group`, `tp_rank`, `tp_size`, `gpu_id`).

Run from the repo root:
    python3 /tmp/transform_weight_exporter_send_group.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/28"
TARGET_COMMIT = "tom_refactor/29"


NEW_FILE_CONTENT = '''from __future__ import annotations

import logging

import torch
import torch.distributed as dist

from sglang.srt.utils import init_custom_process_group
from sglang.srt.utils.network import NetworkAddress

logger = logging.getLogger(__name__)


def init_weights_send_group_for_remote_instance(
    *,
    _weights_send_group,
    tp_rank,
    tp_size,
    gpu_id,
    master_address,
    ports,
    group_rank,
    world_size,
    group_name,
    backend="nccl",
):
    assert (
        torch.distributed.is_initialized()
    ), "Default torch process group must be initialized"
    assert group_name != "", "Group name cannot be empty"

    ports_list = ports.split(",")
    assert (
        len(ports_list) == tp_size
    ), f"Expected {tp_size} ports, but got {len(ports_list)} ports."
    group_port = ports_list[tp_rank]
    group_name = f"{group_name}_{group_port}_{tp_rank}"

    logger.info(
        f"init custom process group: tp_rank={tp_rank}, gpu_id={gpu_id}, master_address={master_address}, master_port={group_port}, "
        f"group_rank={group_rank}, world_size={world_size}, group_name={group_name}, backend={backend}"
    )

    torch.cuda.empty_cache()
    success = False
    message = ""
    try:
        na = NetworkAddress(master_address, group_port)
        _weights_send_group[group_name] = init_custom_process_group(
            backend=backend,
            init_method=na.to_tcp(),
            world_size=world_size,
            rank=group_rank,
            group_name=group_name,
            device_id=torch.device("cuda", gpu_id),
        )
        dist.barrier(group=_weights_send_group[group_name])
        success = True
        message = f"Succeeded to init group through {na.to_host_port_str()} group."
    except Exception as e:
        message = f"Failed to init group: {e}."
        logger.error(message)

    torch.cuda.empty_cache()
    return success, message


def send_weights_to_remote_instance(
    *,
    model,
    _weights_send_group,
    tp_rank,
    tp_size,
    master_address,
    ports,
    group_name,
):
    assert (
        torch.distributed.is_initialized()
    ), "Default torch process group must be initialized"
    assert group_name != "", "Group name cannot be empty"

    ports_list = ports.split(",")
    assert (
        len(ports_list) == tp_size
    ), f"Expected {tp_size} ports, but got {len(ports_list)} ports."
    group_port = ports_list[tp_rank]
    group_name = f"{group_name}_{group_port}_{tp_rank}"

    if _weights_send_group[group_name] is not None:
        send_group = _weights_send_group[group_name]
    else:
        message = f"Group {group_name} not in _weights_send_group list. Please call `init_weights_send_group_for_remote_instance` first."
        logger.error(message)
        return False, message

    torch.cuda.empty_cache()
    success = False
    na = NetworkAddress(master_address, group_port)
    message = ""
    try:
        for _, weights in model.named_parameters():
            torch.distributed.broadcast(
                weights,
                src=0,
                group=send_group,
            )
        success = True
        message = f"Succeeded to send weights through {na.to_host_port_str()} {group_name}."
    except Exception as e:
        message = f"Failed to send weights: {e}."
        logger.error(message)

    # destroy the process group after sending weights
    del _weights_send_group[group_name]
    torch.distributed.distributed_c10d.destroy_process_group(send_group)
    torch.cuda.empty_cache()
    return success, message
'''


def transform(dir_root: Path) -> None:
    # --- Step 1: create the new weight_exporter.py file ---
    new_file = dir_root / "python/sglang/srt/model_executor/weight_exporter.py"
    new_file.write_text(NEW_FILE_CONTENT)

    # --- Step 2: update model_runner.py ---
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Add weight_exporter import next to weight_updater import.
    old_imp_anchor = (
        "from sglang.srt.model_executor.weight_updater import (\n"
    )
    assert old_imp_anchor in text, "weight_updater import anchor not found"
    text = text.replace(
        old_imp_anchor,
        "from sglang.srt.model_executor.weight_exporter import (\n"
        "    init_weights_send_group_for_remote_instance as _free_init_weights_send_group_for_remote_instance,\n"
        "    send_weights_to_remote_instance as _free_send_weights_to_remote_instance,\n"
        ")\n"
        + old_imp_anchor,
    )

    # Replace init_weights_send_group_for_remote_instance body with delegate.
    old_init_send = (
        "    def init_weights_send_group_for_remote_instance(\n"
        "        self,\n"
        "        master_address,\n"
        "        ports,\n"
        "        group_rank,\n"
        "        world_size,\n"
        "        group_name,\n"
        '        backend="nccl",\n'
        "    ):\n"
        "        assert (\n"
        "            torch.distributed.is_initialized()\n"
        '        ), "Default torch process group must be initialized"\n'
        '        assert group_name != "", "Group name cannot be empty"\n'
        "\n"
        '        ports_list = ports.split(",")\n'
        "        assert (\n"
        "            len(ports_list) == self.tp_size\n"
        '        ), f"Expected {self.tp_size} ports, but got {len(ports_list)} ports."\n'
        "        group_port = ports_list[self.tp_rank]\n"
        '        group_name = f"{group_name}_{group_port}_{self.tp_rank}"\n'
        "\n"
        "        logger.info(\n"
        '            f"init custom process group: tp_rank={self.tp_rank}, gpu_id={self.gpu_id}, master_address={master_address}, master_port={group_port}, "\n'
        '            f"group_rank={group_rank}, world_size={world_size}, group_name={group_name}, backend={backend}"\n'
        "        )\n"
        "\n"
        "        torch.cuda.empty_cache()\n"
        "        success = False\n"
        '        message = ""\n'
        "        try:\n"
        "            na = NetworkAddress(master_address, group_port)\n"
        "            self._weights_send_group[group_name] = init_custom_process_group(\n"
        "                backend=backend,\n"
        "                init_method=na.to_tcp(),\n"
        "                world_size=world_size,\n"
        "                rank=group_rank,\n"
        "                group_name=group_name,\n"
        '                device_id=torch.device("cuda", self.gpu_id),\n'
        "            )\n"
        "            dist.barrier(group=self._weights_send_group[group_name])\n"
        "            success = True\n"
        '            message = f"Succeeded to init group through {na.to_host_port_str()} group."\n'
        "        except Exception as e:\n"
        '            message = f"Failed to init group: {e}."\n'
        "            logger.error(message)\n"
        "\n"
        "        torch.cuda.empty_cache()\n"
        "        return success, message\n"
    )
    new_init_send = (
        "    def init_weights_send_group_for_remote_instance(\n"
        "        self,\n"
        "        master_address,\n"
        "        ports,\n"
        "        group_rank,\n"
        "        world_size,\n"
        "        group_name,\n"
        '        backend="nccl",\n'
        "    ):\n"
        "        return _free_init_weights_send_group_for_remote_instance(\n"
        "            _weights_send_group=self._weights_send_group,\n"
        "            tp_rank=self.tp_rank,\n"
        "            tp_size=self.tp_size,\n"
        "            gpu_id=self.gpu_id,\n"
        "            master_address=master_address,\n"
        "            ports=ports,\n"
        "            group_rank=group_rank,\n"
        "            world_size=world_size,\n"
        "            group_name=group_name,\n"
        "            backend=backend,\n"
        "        )\n"
    )
    assert old_init_send in text, "init_weights_send_group_for_remote_instance body not found"
    text = text.replace(old_init_send, new_init_send)

    # Replace send_weights_to_remote_instance body with delegate.
    old_send = (
        "    def send_weights_to_remote_instance(\n"
        "        self,\n"
        "        master_address,\n"
        "        ports,\n"
        "        group_name,\n"
        "    ):\n"
        "        assert (\n"
        "            torch.distributed.is_initialized()\n"
        '        ), "Default torch process group must be initialized"\n'
        '        assert group_name != "", "Group name cannot be empty"\n'
        "\n"
        '        ports_list = ports.split(",")\n'
        "        assert (\n"
        "            len(ports_list) == self.tp_size\n"
        '        ), f"Expected {self.tp_size} ports, but got {len(ports_list)} ports."\n'
        "        group_port = ports_list[self.tp_rank]\n"
        '        group_name = f"{group_name}_{group_port}_{self.tp_rank}"\n'
        "\n"
        "        if self._weights_send_group[group_name] is not None:\n"
        "            send_group = self._weights_send_group[group_name]\n"
        "        else:\n"
        '            message = f"Group {group_name} not in _weights_send_group list. Please call `init_weights_send_group_for_remote_instance` first."\n'
        "            logger.error(message)\n"
        "            return False, message\n"
        "\n"
        "        torch.cuda.empty_cache()\n"
        "        success = False\n"
        "        na = NetworkAddress(master_address, group_port)\n"
        '        message = ""\n'
        "        try:\n"
        "            for _, weights in self.model.named_parameters():\n"
        "                torch.distributed.broadcast(\n"
        "                    weights,\n"
        "                    src=0,\n"
        "                    group=send_group,\n"
        "                )\n"
        "            success = True\n"
        '            message = f"Succeeded to send weights through {na.to_host_port_str()} {group_name}."\n'
        "        except Exception as e:\n"
        '            message = f"Failed to send weights: {e}."\n'
        "            logger.error(message)\n"
        "\n"
        "        # destroy the process group after sending weights\n"
        "        del self._weights_send_group[group_name]\n"
        "        torch.distributed.distributed_c10d.destroy_process_group(send_group)\n"
        "        torch.cuda.empty_cache()\n"
        "        return success, message\n"
    )
    new_send = (
        "    def send_weights_to_remote_instance(\n"
        "        self,\n"
        "        master_address,\n"
        "        ports,\n"
        "        group_name,\n"
        "    ):\n"
        "        return _free_send_weights_to_remote_instance(\n"
        "            model=self.model,\n"
        "            _weights_send_group=self._weights_send_group,\n"
        "            tp_rank=self.tp_rank,\n"
        "            tp_size=self.tp_size,\n"
        "            master_address=master_address,\n"
        "            ports=ports,\n"
        "            group_name=group_name,\n"
        "        )\n"
    )
    assert old_send in text, "send_weights_to_remote_instance body not found"
    text = text.replace(old_send, new_send)

    mr.write_text(text)

    git_add_and_commit(
        "Extract weights send group methods to free functions in weight_exporter",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
