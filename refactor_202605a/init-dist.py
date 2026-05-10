#!/usr/bin/env python3
"""Cut `ModelRunner.init_torch_distributed` (139-line method); paste as a free
function `init_torch_distributed` in `sglang.srt.distributed.bootstrap`. Three
group writebacks (`tp_group`, `pp_group`, `attention_tp_group`) plus the
returned `pre_model_load_memory` are wrapped in a `TorchDistributedResult`
dataclass so the caller can copy them onto `self`.

Body is byte-identical after dedent + ``self.X`` -> ``X`` substitution. The
delegate method is NOT kept on ModelRunner -- the sole caller (in
``ModelRunner.initialize``) is updated directly to call the free function and
write back the 3 group fields.

Usage:
    uv run --python 3.12 init-dist.py run
    uv run --python 3.12 init-dist.py verify
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

ID = "init-dist"
SUBJECT = "Extract init_torch_distributed to distributed/bootstrap.py"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-lora-moe-buffers"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"

# Header for the new bootstrap.py file: imports + module-level constants
# (the original ones live on model_runner.py and are referenced inside the
# init_torch_distributed body), the result dataclass, and the function
# signature line. Body is appended after the signature.
BOOTSTRAP_HEADER = '''from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import List, Optional

import torch
import torch.distributed as dist

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.distributed import (
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
from sglang.srt.layers.dp_attention import (
    get_attention_tp_group,
    initialize_dp_attention,
)
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils import (
    cpu_has_amx_support,
    get_available_gpu_memory,
    is_host_cpu_arm64,
    is_npu,
    monkey_patch_p2p_access_check,
)
from sglang.srt.utils.network import NetworkAddress
from sglang.srt.utils.patch_torch import register_sgl_tp_rank

logger = logging.getLogger(__name__)

_is_cpu_amx_available = cpu_has_amx_support()
_is_cpu_arm64 = is_host_cpu_arm64()


@dataclass(frozen=True, slots=True, kw_only=True)
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
    local_omp_cpuid: Optional[List[int]],
):
'''

# Replacement for the call site `pre_model_load_memory = self.init_torch_distributed()`
# in `ModelRunner.initialize`. Calls the free function with 15 kwargs and
# writes the 3 group results back onto `self`.
INLINE_CALL = '''        result = init_torch_distributed(
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
        pre_model_load_memory = result.pre_model_load_memory'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    bootstrap = wt / "python/sglang/srt/distributed/bootstrap.py"

    # ---- Cut the method body from ModelRunner ----
    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="init_torch_distributed"
    )
    method_text = cut_lines(mr, start, end)

    # ---- Build the function body: dedent, drop signature, s/self.X/X/, ----
    # ---- replace the 3 group writebacks with local var assigns + return  ----
    body = dedent_method_to_function(method_text)
    body = body.replace("def init_torch_distributed(self):\n", "")

    for name in (
        "device", "gpu_id", "tp_rank", "tp_size", "pp_rank", "pp_size",
        "dp_size", "attn_cp_size", "moe_ep_size", "moe_dp_size",
        "dist_port", "is_draft_worker", "local_omp_cpuid",
        "server_args", "model_config",
    ):
        body = body.replace(f"self.{name}", name)

    # After dedent, original 8-space indent is now 4 spaces (function body).
    body = body.replace(
        "    self.tp_group = get_tp_group()\n"
        "    self.pp_group = get_pp_group()\n"
        "    self.attention_tp_group = get_attention_tp_group()\n",
        "    tp_group = get_tp_group()\n"
        "    pp_group = get_pp_group()\n"
        "    attention_tp_group = get_attention_tp_group()\n",
    )

    body = body.replace(
        "    return pre_model_load_memory\n",
        "    return TorchDistributedResult(\n"
        "        tp_group=tp_group,\n"
        "        pp_group=pp_group,\n"
        "        attention_tp_group=attention_tp_group,\n"
        "        pre_model_load_memory=pre_model_load_memory,\n"
        "    )\n",
    )

    bootstrap.parent.mkdir(parents=True, exist_ok=True)
    bootstrap.write_text(BOOTSTRAP_HEADER + body)

    # ---- Update ModelRunner: add free-function import; rewrite caller ----
    text = mr.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.distributed.parallel_state import monkey_patch_vllm_parallel_state\n",
        addition="from sglang.srt.distributed.bootstrap import init_torch_distributed\n",
    )
    text = replace_call_site(
        text,
        old="        pre_model_load_memory = self.init_torch_distributed()\n",
        new=INLINE_CALL + "\n",
    )
    mr.write_text(text)

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
