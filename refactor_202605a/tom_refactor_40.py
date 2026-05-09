#!/usr/bin/env python3
"""Cut `ModelRunner.init_torch_distributed` (139-line method); paste as a free
function `init_torch_distributed` in `sglang.srt.distributed.bootstrap`.

The body is byte-identical after dedent + `self.X` -> kwarg substitution. The
three group writebacks (`tp_group`, `pp_group`, `attention_tp_group`) and the
returned `pre_model_load_memory` are wrapped in a `TorchDistributedResult`
dataclass so the caller can copy them onto `self`.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import (
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/39"
TARGET_COMMIT = "tom_refactor/40"

BOOTSTRAP_HEADER = '''from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import List, Optional, Union

import torch
import torch.distributed as dist

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.distributed import (
    get_attention_tp_group,
    get_default_distributed_backend,
    get_pp_group,
    get_tp_group,
    get_world_group,
    init_distributed_environment,
    initialize_model_parallel,
    set_custom_all_reduce,
    set_mscclpp_all_reduce,
    set_torch_symm_mem_all_reduce,
)
from sglang.srt.environ import envs
from sglang.srt.layers.dp_attention import initialize_dp_attention
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils import (
    cpu_has_amx_support,
    get_available_gpu_memory,
    is_host_cpu_arm64,
    is_npu,
    monkey_patch_p2p_access_check,
    register_sgl_tp_rank,
)
from sglang.srt.utils.network import NetworkAddress

logger = logging.getLogger(__name__)


@dataclass
class TorchDistributedResult:
    tp_group: object
    pp_group: object
    attention_tp_group: object
    pre_model_load_memory: float


def init_torch_distributed(
    *,
    server_args: ServerArgs,
    model_config: ModelConfig,
    device: str,
    gpu_id: int,
    tp_rank: int,
    tp_size: int,
    pp_rank: int,
    pp_size: int,
    dp_size: int,
    attn_cp_size: int,
    moe_ep_size: int,
    moe_dp_size: int,
    dist_port: int,
    is_draft_worker: bool,
    local_omp_cpuid: Optional[Union[List[int], str]],
) -> TorchDistributedResult:
'''

DELEGATE = '''    def init_torch_distributed(self):
        result = _init_torch_distributed(
            server_args=self.server_args,
            model_config=self.model_config,
            device=self.device,
            gpu_id=self.gpu_id,
            tp_rank=self.tp_rank,
            tp_size=self.tp_size,
            pp_rank=self.pp_rank,
            pp_size=self.pp_size,
            dp_size=self.dp_size,
            attn_cp_size=self.attn_cp_size,
            moe_ep_size=self.moe_ep_size,
            moe_dp_size=self.moe_dp_size,
            dist_port=self.dist_port,
            is_draft_worker=self.is_draft_worker,
            local_omp_cpuid=self.local_omp_cpuid if self.device == "cpu" else None,
        )
        self.tp_group = result.tp_group
        self.pp_group = result.pp_group
        self.attention_tp_group = result.attention_tp_group
        return result.pre_model_load_memory

'''


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    bootstrap = dir_root / "python/sglang/srt/distributed/bootstrap.py"

    # ---- Cut the method body from ModelRunner ----
    start, end = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="init_torch_distributed",
    )
    method_text = cut_lines(mr, start, end)

    # ---- Build the function body: dedent + self.X -> kwarg sub ----
    body = dedent_method_to_function(method_text)
    # Drop the original signature line; we'll prepend a new one in the header.
    body = body.replace("def init_torch_distributed(self):\n", "")

    # `self.X` -> `X` for every kwarg.
    self_to_kwarg = [
        "device",
        "gpu_id",
        "tp_rank",
        "tp_size",
        "pp_rank",
        "pp_size",
        "dp_size",
        "attn_cp_size",
        "moe_ep_size",
        "moe_dp_size",
        "dist_port",
        "is_draft_worker",
        "local_omp_cpuid",
        "server_args",
        "model_config",
    ]
    for name in self_to_kwarg:
        body = body.replace(f"self.{name}", name)

    # The 3 group writebacks become local var assignments.
    body = body.replace(
        "        self.tp_group = get_tp_group()\n"
        "        self.pp_group = get_pp_group()\n"
        "        self.attention_tp_group = get_attention_tp_group()\n",
        "        tp_group = get_tp_group()\n"
        "        pp_group = get_pp_group()\n"
        "        attention_tp_group = get_attention_tp_group()\n",
    )

    # Final return wraps in TorchDistributedResult.
    body = body.replace(
        "        return pre_model_load_memory\n",
        "        return TorchDistributedResult(\n"
        "            tp_group=tp_group,\n"
        "            pp_group=pp_group,\n"
        "            attention_tp_group=attention_tp_group,\n"
        "            pre_model_load_memory=pre_model_load_memory,\n"
        "        )\n",
    )

    bootstrap.parent.mkdir(parents=True, exist_ok=True)
    bootstrap.write_text(BOOTSTRAP_HEADER + body)

    # ---- Update ModelRunner: add import + thin delegate ----
    text = mr.read_text()

    # Add the bootstrap import after the parallel_state monkey-patch import.
    text = insert_after(
        text,
        anchor="from sglang.srt.distributed.parallel_state import monkey_patch_vllm_parallel_state\n",
        addition="from sglang.srt.distributed.bootstrap import init_torch_distributed as _init_torch_distributed\n",
    )

    # Splice the delegate where the cut method used to live. The cut left a
    # gap exactly between the previous method's blank-line tail and the next
    # method header. We anchor on the unique line that was after the cut.
    src_lines = mr.read_text().splitlines(keepends=True)
    # Reinsert delegate at the original `start` line.
    new_text = "".join(src_lines[:start]) + DELEGATE + "".join(src_lines[start:])
    mr.write_text(new_text)

    # Sanity check: caller invocation site is unchanged (still
    # `pre_model_load_memory = self.init_torch_distributed()`).
    assert "pre_model_load_memory = self.init_torch_distributed()" in mr.read_text()

    git_add_and_commit(
        "Extract init_torch_distributed to distributed/bootstrap.py",
        cwd=str(dir_root),
    )


# Helper to silence unused-import warnings if ruff strips them.
_ = replace_call_site


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
