#!/usr/bin/env python3
"""Cut `init_weights_send_group_for_remote_instance` and
`send_weights_to_remote_instance` from ModelRunner; paste as free functions in
new `weight_exporter.py`. Update tp_worker.py call sites.

`self._weights_send_group` (a dict) stays on ModelRunner; the free functions
take it as a kwarg.

Usage:
    uv run --python 3.12 tom_refactor_29.py run
    uv run --python 3.12 tom_refactor_29.py verify
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
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

BASE = "tom_refactor/28"
TARGET = "tom_refactor/29"


HEADER = '''from __future__ import annotations

import logging

import torch
import torch.distributed as dist

from sglang.srt.utils import init_custom_process_group
from sglang.srt.utils.network import NetworkAddress

logger = logging.getLogger(__name__)


'''


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    we = wt / "python/sglang/srt/model_executor/weight_exporter.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="send_weights_to_remote_instance",
    )
    send_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def send_weights_to_remote_instance(\n"
            "    self,\n"
            "    master_address,\n"
            "    ports,\n"
            "    group_name,\n"
            "):",
            "def send_weights_to_remote_instance(\n"
            "    *,\n"
            "    model,\n"
            "    _weights_send_group,\n"
            "    tp_rank,\n"
            "    tp_size,\n"
            "    master_address,\n"
            "    ports,\n"
            "    group_name,\n"
            "):",
        )
        .replace("self.tp_size", "tp_size")
        .replace("self.tp_rank", "tp_rank")
        .replace("self._weights_send_group", "_weights_send_group")
        .replace("self.model.named_parameters", "model.named_parameters")
    )

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_weights_send_group_for_remote_instance",
    )
    init_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def init_weights_send_group_for_remote_instance(\n"
            "    self,\n"
            "    master_address,\n"
            "    ports,\n"
            "    group_rank,\n"
            "    world_size,\n"
            "    group_name,\n"
            '    backend="nccl",\n'
            "):",
            "def init_weights_send_group_for_remote_instance(\n"
            "    *,\n"
            "    _weights_send_group,\n"
            "    tp_rank,\n"
            "    tp_size,\n"
            "    gpu_id,\n"
            "    master_address,\n"
            "    ports,\n"
            "    group_rank,\n"
            "    world_size,\n"
            "    group_name,\n"
            '    backend="nccl",\n'
            "):",
        )
        .replace("self.tp_size", "tp_size")
        .replace("self.tp_rank", "tp_rank")
        .replace("self.gpu_id", "gpu_id")
        .replace("self._weights_send_group", "_weights_send_group")
    )

    we.write_text(HEADER + init_text + "\n" + send_text)

    # tp_worker.py: add module import for weight_exporter; rewrite call sites.
    text = tw.read_text()
    if "from sglang.srt.model_executor import weight_exporter\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.model_executor.forward_batch_info import ForwardBatch, PPProxyTensors\n",
            addition="from sglang.srt.model_executor import weight_exporter\n",
        )
    text = replace_call_site(
        text,
        old=(
            "        success, message = (\n"
            "            self.model_runner.init_weights_send_group_for_remote_instance(\n"
            "                recv_req.master_address,\n"
            "                recv_req.ports,\n"
            "                recv_req.group_rank,\n"
            "                recv_req.world_size,\n"
            "                recv_req.group_name,\n"
            "                recv_req.backend,\n"
            "            )\n"
            "        )\n"
        ),
        new=(
            "        success, message = weight_exporter.init_weights_send_group_for_remote_instance(\n"
            "            _weights_send_group=self.model_runner._weights_send_group,\n"
            "            tp_rank=self.model_runner.tp_rank,\n"
            "            tp_size=self.model_runner.tp_size,\n"
            "            gpu_id=self.model_runner.gpu_id,\n"
            "            master_address=recv_req.master_address,\n"
            "            ports=recv_req.ports,\n"
            "            group_rank=recv_req.group_rank,\n"
            "            world_size=recv_req.world_size,\n"
            "            group_name=recv_req.group_name,\n"
            "            backend=recv_req.backend,\n"
            "        )\n"
        ),
    )
    text = replace_call_site(
        text,
        old=(
            "        success, message = self.model_runner.send_weights_to_remote_instance(\n"
            "            recv_req.master_address,\n"
            "            recv_req.ports,\n"
            "            recv_req.group_name,\n"
            "        )\n"
        ),
        new=(
            "        success, message = weight_exporter.send_weights_to_remote_instance(\n"
            "            model=self.model_runner.model,\n"
            "            _weights_send_group=self.model_runner._weights_send_group,\n"
            "            tp_rank=self.model_runner.tp_rank,\n"
            "            tp_size=self.model_runner.tp_size,\n"
            "            master_address=recv_req.master_address,\n"
            "            ports=recv_req.ports,\n"
            "            group_name=recv_req.group_name,\n"
            "        )\n"
        ),
    )
    tw.write_text(text)

    git_add_and_commit(
        "Extract weights send group methods to free functions in weight_exporter",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
