#!/usr/bin/env python3
"""Reproducible transform: extract `ModelRunner.init_torch_distributed` into a
free function `init_torch_distributed` in `sglang.srt.distributed.bootstrap`.

The new file lives at `python/sglang/srt/distributed/bootstrap.py` and exports
a `TorchDistributedResult` dataclass + `init_torch_distributed(...)` function.
The body is byte-equivalent with `self.X` -> kwarg substitution; the three
group writebacks (`tp_group`, `pp_group`, `attention_tp_group`) are returned
via the dataclass so the caller can copy them onto `self`. The caller method
on `ModelRunner` becomes a thin delegate.
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/39"
TARGET_COMMIT = "tom_refactor/40"


BOOTSTRAP_PY = '''
from __future__ import annotations

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
    local_omp_cpuid: Optional[Union[List[int], str]],
) -> TorchDistributedResult:
    tic = time.perf_counter()
    logger.info("Init torch distributed begin.")

    try:
        torch.get_device_module(device).set_device(gpu_id)
    except Exception:
        logger.warning(
            f"Context: {device=} {gpu_id=} {os.environ.get('CUDA_VISIBLE_DEVICES')=} {tp_rank=} {tp_size=}"
        )
        raise

    backend = get_default_distributed_backend(device)
    if device == "cuda" and server_args.elastic_ep_backend == "mooncake":
        backend = "mooncake"
        if server_args.mooncake_ib_device:
            mooncake_ib_device = server_args.mooncake_ib_device.split(",")
            try:
                from mooncake import ep as mooncake_ep

                mooncake_ep.set_device_filter(mooncake_ib_device)
            except Exception:
                pass  # A warning will be raised in `init_distributed_environment`

    before_avail_memory = get_available_gpu_memory(device, gpu_id)
    if not server_args.enable_p2p_check:
        monkey_patch_p2p_access_check()

    # Allow external orchestrators (e.g. trainpi) to override the distributed
    # init method. When set to "env://", torch uses MASTER_ADDR/MASTER_PORT
    # env-vars and an externally-created TCPStore, completely avoiding port
    # conflicts with intra-host collocation.
    dist_init_method_override = envs.SGLANG_DISTRIBUTED_INIT_METHOD_OVERRIDE.get()
    if dist_init_method_override:
        dist_init_method = dist_init_method_override
    elif server_args.dist_init_addr:
        na = NetworkAddress.parse(server_args.dist_init_addr)
        dist_init_method = na.to_tcp()
    else:
        dist_init_method = NetworkAddress(
            server_args.host or "127.0.0.1", dist_port
        ).to_tcp()
    set_custom_all_reduce(not server_args.disable_custom_all_reduce)
    set_mscclpp_all_reduce(server_args.enable_mscclpp)
    set_torch_symm_mem_all_reduce(server_args.enable_torch_symm_mem)

    _is_cpu_amx_available = cpu_has_amx_support()
    _is_cpu_arm64 = is_host_cpu_arm64()
    if not is_draft_worker:
        if device == "cpu":
            if _is_cpu_amx_available or _is_cpu_arm64:
                # Bind OpenMP threads to CPU cores
                torch.ops.sgl_kernel.init_cpu_threads_env(local_omp_cpuid)

                # Set local size to hint SGLang to use shared memory based AllReduce
                os.environ["LOCAL_SIZE"] = str(tp_size)
                torch.ops.sgl_kernel.initialize(tp_size, tp_rank)

                @torch.library.register_fake("sgl_kernel::shm_allgather")
                def _(data, dim):
                    return torch.cat([data] * tp_size, dim=dim)

            else:
                logger.warning(
                    "init_cpu_threads_env and shared memory based AllReduce is disabled, only intel amx backend and arm64 are supported"
                )

        # Only initialize the distributed environment on the target model worker.
        init_distributed_environment(
            backend=backend,
            world_size=tp_size * pp_size,
            rank=tp_size * pp_rank + tp_rank,
            local_rank=gpu_id,
            distributed_init_method=dist_init_method,
            timeout=server_args.dist_timeout,
            moe_a2a_backend=server_args.moe_a2a_backend,
            recovered_rank=server_args.elastic_ep_rejoin,
        )
        initialize_model_parallel(
            tensor_model_parallel_size=tp_size,
            attention_data_parallel_size=dp_size,
            pipeline_model_parallel_size=pp_size,
            expert_model_parallel_size=moe_ep_size,
            attention_context_model_parallel_size=attn_cp_size,
            moe_data_model_parallel_size=moe_dp_size,
            duplicate_tp_group=server_args.enable_pdmux,
            enable_symm_mem=server_args.enable_symm_mem,
            recovered_rank=server_args.elastic_ep_rejoin,
        )
        initialize_dp_attention(
            server_args=server_args,
            model_config=model_config,
        )
        if is_npu():
            register_sgl_tp_rank(gpu_id)

        # Pre-warm NCCL/RCCL to eliminate cold-start latency in first request
        # Controlled by --pre-warm-nccl flag (default: enabled on AMD GPUs)
        if server_args.pre_warm_nccl and (
            tp_size > 1 or pp_size > 1 or moe_ep_size > 1
        ):
            warmup_start = time.perf_counter()
            tp_group_handle = get_tp_group().device_group

            # Single warmup all_reduce to initialize NCCL/RCCL communicator
            warmup_tensor = torch.zeros(1, device=torch.cuda.current_device())
            dist.all_reduce(warmup_tensor, group=tp_group_handle)
            torch.cuda.synchronize()

            warmup_elapsed = time.perf_counter() - warmup_start
            logger.info(
                f"NCCL/RCCL warmup completed in {warmup_elapsed:.3f}s "
                f"(tp_size={tp_size}, pp_size={pp_size}, ep_size={moe_ep_size})"
            )

    pre_model_load_memory = get_available_gpu_memory(
        device,
        gpu_id,
        distributed=get_world_group().world_size > 1,
        cpu_group=get_world_group().cpu_group,
    )
    tp_group = get_tp_group()
    pp_group = get_pp_group()
    attention_tp_group = get_attention_tp_group()

    # Check memory for tensor parallelism
    local_gpu_memory = get_available_gpu_memory(device, gpu_id)
    if tp_size > 1 and not is_draft_worker:
        if pre_model_load_memory < local_gpu_memory * 0.9:
            msg = "The memory capacity is unbalanced. Some GPUs may be occupied by other processes. "
            msg += f"{pre_model_load_memory=}, {local_gpu_memory=}, {local_gpu_memory * 0.9=}"
            if envs.SGLANG_ENABLE_TP_MEMORY_INBALANCE_CHECK.get():
                raise RuntimeError(msg)
            logger.warning(msg)

    logger.info(
        f"Init torch distributed ends. elapsed={time.perf_counter() - tic:.2f} s, "
        f"mem usage={(before_avail_memory - local_gpu_memory):.2f} GB"
    )
    return TorchDistributedResult(
        tp_group=tp_group,
        pp_group=pp_group,
        attention_tp_group=attention_tp_group,
        pre_model_load_memory=pre_model_load_memory,
    )
'''


def transform(dir_root: Path) -> None:
    # ---- Create new bootstrap.py ----
    bootstrap = dir_root / "python/sglang/srt/distributed/bootstrap.py"
    bootstrap.parent.mkdir(parents=True, exist_ok=True)
    bootstrap.write_text(BOOTSTRAP_PY)

    # ---- Update model_runner.py ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Add the import line, just below `monkey_patch_vllm_parallel_state` import.
    old_import_anchor = (
        "from sglang.srt.distributed.parallel_state import monkey_patch_vllm_parallel_state\n"
        "from sglang.srt.elastic_ep.elastic_ep import (\n"
    )
    new_import_anchor = (
        "from sglang.srt.distributed.parallel_state import monkey_patch_vllm_parallel_state\n"
        "from sglang.srt.distributed.bootstrap import init_torch_distributed as _init_torch_distributed\n"
        "from sglang.srt.elastic_ep.elastic_ep import (\n"
    )
    assert old_import_anchor in text
    text = text.replace(old_import_anchor, new_import_anchor)

    # Replace the entire init_torch_distributed method with a delegate.
    old_method = (
        "    def init_torch_distributed(self):\n"
        "        tic = time.perf_counter()\n"
        '        logger.info("Init torch distributed begin.")\n'
        "\n"
        "        try:\n"
        "            torch.get_device_module(self.device).set_device(self.gpu_id)\n"
        "        except Exception:\n"
        "            logger.warning(\n"
        "                f\"Context: {self.device=} {self.gpu_id=} {os.environ.get('CUDA_VISIBLE_DEVICES')=} {self.tp_rank=} {self.tp_size=}\"\n"
        "            )\n"
        "            raise\n"
        "\n"
        "        backend = get_default_distributed_backend(self.device)\n"
        '        if self.device == "cuda" and self.server_args.elastic_ep_backend == "mooncake":\n'
        '            backend = "mooncake"\n'
        "            if self.server_args.mooncake_ib_device:\n"
        '                mooncake_ib_device = self.server_args.mooncake_ib_device.split(",")\n'
        "                try:\n"
        "                    from mooncake import ep as mooncake_ep\n"
        "\n"
        "                    mooncake_ep.set_device_filter(mooncake_ib_device)\n"
        "                except:\n"
        "                    pass  # A warning will be raised in `init_distributed_environment`\n"
        "\n"
        "        before_avail_memory = get_available_gpu_memory(self.device, self.gpu_id)\n"
        "        if not self.server_args.enable_p2p_check:\n"
        "            monkey_patch_p2p_access_check()\n"
        "\n"
        "        # Allow external orchestrators (e.g. trainpi) to override the distributed\n"
        '        # init method.  When set to "env://", torch uses MASTER_ADDR/MASTER_PORT\n'
        "        # env-vars and an externally-created TCPStore, completely avoiding port\n"
        "        # conflicts with intra-host collocation.\n"
        "        dist_init_method_override = envs.SGLANG_DISTRIBUTED_INIT_METHOD_OVERRIDE.get()\n"
        "        if dist_init_method_override:\n"
        "            dist_init_method = dist_init_method_override\n"
        "        elif self.server_args.dist_init_addr:\n"
        "            na = NetworkAddress.parse(self.server_args.dist_init_addr)\n"
        "            dist_init_method = na.to_tcp()\n"
        "        else:\n"
        "            dist_init_method = NetworkAddress(\n"
        '                self.server_args.host or "127.0.0.1", self.dist_port\n'
        "            ).to_tcp()\n"
        "        set_custom_all_reduce(not self.server_args.disable_custom_all_reduce)\n"
        "        set_mscclpp_all_reduce(self.server_args.enable_mscclpp)\n"
        "        set_torch_symm_mem_all_reduce(self.server_args.enable_torch_symm_mem)\n"
        "\n"
        "        if not self.is_draft_worker:\n"
        '            if self.device == "cpu":\n'
        "                if _is_cpu_amx_available or _is_cpu_arm64:\n"
        "                    # Bind OpenMP threads to CPU cores\n"
        "                    torch.ops.sgl_kernel.init_cpu_threads_env(self.local_omp_cpuid)\n"
        "\n"
        "                    # Set local size to hint SGLang to use shared memory based AllReduce\n"
        '                    os.environ["LOCAL_SIZE"] = str(self.tp_size)\n'
        "                    torch.ops.sgl_kernel.initialize(self.tp_size, self.tp_rank)\n"
        "\n"
        '                    @torch.library.register_fake("sgl_kernel::shm_allgather")\n'
        "                    def _(data, dim):\n"
        "                        return torch.cat([data] * self.tp_size, dim=dim)\n"
        "\n"
        "                else:\n"
        "                    logger.warning(\n"
        '                        "init_cpu_threads_env and shared memory based AllReduce is disabled, only intel amx backend and arm64 are supported"\n'
        "                    )\n"
        "\n"
        "            # Only initialize the distributed environment on the target model worker.\n"
        "            init_distributed_environment(\n"
        "                backend=backend,\n"
        "                world_size=self.tp_size * self.pp_size,\n"
        "                rank=self.tp_size * self.pp_rank + self.tp_rank,\n"
        "                local_rank=self.gpu_id,\n"
        "                distributed_init_method=dist_init_method,\n"
        "                timeout=self.server_args.dist_timeout,\n"
        "                moe_a2a_backend=self.server_args.moe_a2a_backend,\n"
        "                recovered_rank=self.server_args.elastic_ep_rejoin,\n"
        "            )\n"
        "            initialize_model_parallel(\n"
        "                tensor_model_parallel_size=self.tp_size,\n"
        "                attention_data_parallel_size=self.dp_size,\n"
        "                pipeline_model_parallel_size=self.pp_size,\n"
        "                expert_model_parallel_size=self.moe_ep_size,\n"
        "                attention_context_model_parallel_size=self.attn_cp_size,\n"
        "                moe_data_model_parallel_size=self.moe_dp_size,\n"
        "                duplicate_tp_group=self.server_args.enable_pdmux,\n"
        "                enable_symm_mem=self.server_args.enable_symm_mem,\n"
        "                recovered_rank=self.server_args.elastic_ep_rejoin,\n"
        "            )\n"
        "            initialize_dp_attention(\n"
        "                server_args=self.server_args,\n"
        "                model_config=self.model_config,\n"
        "            )\n"
        "            if is_npu():\n"
        "                register_sgl_tp_rank(self.gpu_id)\n"
        "\n"
        "            # Pre-warm NCCL/RCCL to eliminate cold-start latency in first request\n"
        "            # Controlled by --pre-warm-nccl flag (default: enabled on AMD GPUs)\n"
        "            if self.server_args.pre_warm_nccl and (\n"
        "                self.tp_size > 1 or self.pp_size > 1 or self.moe_ep_size > 1\n"
        "            ):\n"
        "                warmup_start = time.perf_counter()\n"
        "                tp_group_handle = get_tp_group().device_group\n"
        "\n"
        "                # Single warmup all_reduce to initialize NCCL/RCCL communicator\n"
        "                warmup_tensor = torch.zeros(1, device=torch.cuda.current_device())\n"
        "                dist.all_reduce(warmup_tensor, group=tp_group_handle)\n"
        "                torch.cuda.synchronize()\n"
        "\n"
        "                warmup_elapsed = time.perf_counter() - warmup_start\n"
        "                logger.info(\n"
        '                    f"NCCL/RCCL warmup completed in {warmup_elapsed:.3f}s "\n'
        '                    f"(tp_size={self.tp_size}, pp_size={self.pp_size}, ep_size={self.moe_ep_size})"\n'
        "                )\n"
        "\n"
        "        pre_model_load_memory = get_available_gpu_memory(\n"
        "            self.device,\n"
        "            self.gpu_id,\n"
        "            distributed=get_world_group().world_size > 1,\n"
        "            cpu_group=get_world_group().cpu_group,\n"
        "        )\n"
        "        self.tp_group = get_tp_group()\n"
        "        self.pp_group = get_pp_group()\n"
        "        self.attention_tp_group = get_attention_tp_group()\n"
        "\n"
        "        # Check memory for tensor parallelism\n"
        "        local_gpu_memory = get_available_gpu_memory(self.device, self.gpu_id)\n"
        "        if self.tp_size > 1 and not self.is_draft_worker:\n"
        "            if pre_model_load_memory < local_gpu_memory * 0.9:\n"
        '                msg = "The memory capacity is unbalanced. Some GPUs may be occupied by other processes. "\n'
        '                msg += f"{pre_model_load_memory=}, {local_gpu_memory=}, {local_gpu_memory * 0.9=}"\n'
        "                if envs.SGLANG_ENABLE_TP_MEMORY_INBALANCE_CHECK.get():\n"
        "                    raise RuntimeError(msg)\n"
        "                else:\n"
        "                    logger.warning(msg)\n"
        "\n"
        "        logger.info(\n"
        '            f"Init torch distributed ends. elapsed={time.perf_counter() - tic:.2f} s, "\n'
        '            f"mem usage={(before_avail_memory - local_gpu_memory):.2f} GB"\n'
        "        )\n"
        "        return pre_model_load_memory\n"
    )
    new_method = (
        "    def init_torch_distributed(self):\n"
        "        result = _init_torch_distributed(\n"
        "            server_args=self.server_args,\n"
        "            model_config=self.model_config,\n"
        "            device=self.device,\n"
        "            gpu_id=self.gpu_id,\n"
        "            tp_rank=self.tp_rank,\n"
        "            tp_size=self.tp_size,\n"
        "            pp_rank=self.pp_rank,\n"
        "            pp_size=self.pp_size,\n"
        "            dp_size=self.dp_size,\n"
        "            attn_cp_size=self.attn_cp_size,\n"
        "            moe_ep_size=self.moe_ep_size,\n"
        "            moe_dp_size=self.moe_dp_size,\n"
        "            dist_port=self.dist_port,\n"
        "            is_draft_worker=self.is_draft_worker,\n"
        '            local_omp_cpuid=self.local_omp_cpuid if self.device == "cpu" else None,\n'
        "        )\n"
        "        self.tp_group = result.tp_group\n"
        "        self.pp_group = result.pp_group\n"
        "        self.attention_tp_group = result.attention_tp_group\n"
        "        return result.pre_model_load_memory\n"
        "\n"
    )
    assert old_method in text, "old init_torch_distributed body not found"
    text = text.replace(old_method, new_method)

    mr.write_text(text)

    git_add_and_commit(
        "Extract init_torch_distributed to distributed/bootstrap.py",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
