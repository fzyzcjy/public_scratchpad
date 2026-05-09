#!/usr/bin/env python3
"""Reproducible transform: add `cuda_graph_max_bs` kwarg to LoRAManager and
absorb `ModelRunner._init_lora_cuda_graph_moe_buffers` body into
`LoRAManager.__init__`.

Per `lora_manager.md` ch1:
- Add `cuda_graph_max_bs: Optional[int] = None` kwarg to `LoRAManager.__init__`
  and to `LoRAManager.init_state` (kwarg is forwarded but currently unused
  inside `init_state`; carried for symmetry).
- Append the MoE-buffer prealloc block to the end of `__init__`, gated by
  `cuda_graph_max_bs is not None`.
- Add `get_available_gpu_memory` to `sglang.srt.utils` import line (not used
  here but follows the upstream change set).
- ModelRunner: drop `_init_lora_cuda_graph_moe_buffers`; pass
  `cuda_graph_max_bs=...` from `init_lora_manager`; remove the Phase 1
  if-block in `initialize()`.

Run from the repo root:
    python3 /tmp/transform_lora_cuda_graph_max_bs.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/37"
TARGET_COMMIT = "tom_refactor/38"


def transform(dir_root: Path) -> None:
    # ---- Update lora_manager.py ----
    lm = dir_root / "python/sglang/srt/lora/lora_manager.py"
    text = lm.read_text()

    old_import = "from sglang.srt.utils import replace_submodule\n"
    new_import = "from sglang.srt.utils import get_available_gpu_memory, replace_submodule\n"
    assert old_import in text
    text = text.replace(old_import, new_import)

    old_init_sig_tail = (
        "        max_lora_rank: Optional[int] = None,\n"
        "        target_modules: Optional[Iterable[str]] = None,\n"
        "        lora_paths: Optional[List[LoRARef]] = None,\n"
        "    ):\n"
        "        self.base_model: torch.nn.Module = base_model\n"
    )
    new_init_sig_tail = (
        "        max_lora_rank: Optional[int] = None,\n"
        "        target_modules: Optional[Iterable[str]] = None,\n"
        "        lora_paths: Optional[List[LoRARef]] = None,\n"
        "        cuda_graph_max_bs: Optional[int] = None,\n"
        "    ):\n"
        "        self.base_model: torch.nn.Module = base_model\n"
    )
    assert old_init_sig_tail in text
    text = text.replace(old_init_sig_tail, new_init_sig_tail)

    old_init_state_call = (
        "        # Initialize mutable internal state of the LoRAManager.\n"
        "        self.init_state(\n"
        "            max_lora_rank=max_lora_rank,\n"
        "            target_modules=target_modules,\n"
        "            lora_paths=lora_paths,\n"
        "        )\n"
    )
    new_init_state_with_phase1 = (
        "        # Initialize mutable internal state of the LoRAManager.\n"
        "        self.init_state(\n"
        "            max_lora_rank=max_lora_rank,\n"
        "            target_modules=target_modules,\n"
        "            lora_paths=lora_paths,\n"
        "        )\n"
        "\n"
        "        # Phase 1 of LoRA CUDA graph init: pre-allocate MoE intermediate buffers\n"
        "        # if requested. Phase 2 (dense LoRA batch metadata) happens later in\n"
        "        # CudaGraphRunner.__init__() via init_cuda_graph_batch_info().\n"
        "        if cuda_graph_max_bs is not None:\n"
        "            from sglang.srt.lora.layers import FusedMoEWithLoRA\n"
        "\n"
        "            for module in base_model.modules():\n"
        "                if isinstance(module, FusedMoEWithLoRA):\n"
        "                    self.init_cuda_graph_moe_buffers(\n"
        "                        cuda_graph_max_bs, max_loras_per_batch, dtype, module\n"
        "                    )\n"
        "                    logger.info(\n"
        "                        f\"Pre-allocated shared MoE LoRA CUDA graph buffers \"\n"
        "                        f\"(max_bs={cuda_graph_max_bs}, max_loras={max_loras_per_batch})\"\n"
        "                    )\n"
        "                    break\n"
    )
    assert old_init_state_call in text
    text = text.replace(old_init_state_call, new_init_state_with_phase1)

    # init_state signature: also add the kwarg (carried for symmetry).
    old_init_state_sig = (
        "    def init_state(\n"
        "        self,\n"
        "        max_lora_rank: Optional[int] = None,\n"
        "        target_modules: Optional[Iterable[str]] = None,\n"
        "        lora_paths: Optional[List[LoRARef]] = None,\n"
        "    ):\n"
    )
    new_init_state_sig = (
        "    def init_state(\n"
        "        self,\n"
        "        max_lora_rank: Optional[int] = None,\n"
        "        target_modules: Optional[Iterable[str]] = None,\n"
        "        lora_paths: Optional[List[LoRARef]] = None,\n"
        "        cuda_graph_max_bs: Optional[int] = None,\n"
        "    ):\n"
    )
    assert old_init_state_sig in text
    text = text.replace(old_init_state_sig, new_init_state_sig)

    lm.write_text(text)

    # ---- Update model_runner.py ----
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Remove the Phase 1 if-block in `initialize()`.
    old_phase1 = (
        "        # Init lora\n"
        "        if server_args.enable_lora:\n"
        "            self.init_lora_manager()\n"
        "            if not server_args.disable_cuda_graph:\n"
        "                # Phase 1 of LoRA CUDA graph init: pre-allocate large MoE\n"
        "                # intermediate buffers before init_memory_pool() so memory\n"
        "                # profiling accounts for them.  Phase 2 (dense LoRA batch\n"
        "                # metadata) is handled in CudaGraphRunner.__init__() via\n"
        "                # lora_manager.init_cuda_graph_batch_info().\n"
        "                self._init_lora_cuda_graph_moe_buffers()\n"
    )
    new_phase1 = (
        "        # Init lora\n"
        "        if server_args.enable_lora:\n"
        "            self.init_lora_manager()\n"
    )
    assert old_phase1 in text
    text = text.replace(old_phase1, new_phase1)

    # Pass cuda_graph_max_bs from init_lora_manager.
    old_init_lora_call = (
        "    def init_lora_manager(self):\n"
        "        self.lora_manager = LoRAManager(\n"
        "            base_model=self.model,\n"
        "            base_hf_config=self.model_config.hf_config,\n"
        "            max_loras_per_batch=self.server_args.max_loras_per_batch,\n"
        "            load_config=self.load_config,\n"
        "            dtype=self.dtype,\n"
        "            server_args=self.server_args,\n"
        "            lora_backend=self.server_args.lora_backend,\n"
        "            tp_size=self.tp_size,\n"
        "            tp_rank=self.tp_rank,\n"
        "            max_lora_rank=self.server_args.max_lora_rank,\n"
        "            target_modules=self.server_args.lora_target_modules,\n"
        "            lora_paths=self.server_args.lora_paths,\n"
        "        )\n"
    )
    new_init_lora_call = (
        "    def init_lora_manager(self):\n"
        "        self.lora_manager = LoRAManager(\n"
        "            base_model=self.model,\n"
        "            base_hf_config=self.model_config.hf_config,\n"
        "            max_loras_per_batch=self.server_args.max_loras_per_batch,\n"
        "            load_config=self.load_config,\n"
        "            dtype=self.dtype,\n"
        "            server_args=self.server_args,\n"
        "            lora_backend=self.server_args.lora_backend,\n"
        "            tp_size=self.tp_size,\n"
        "            tp_rank=self.tp_rank,\n"
        "            max_lora_rank=self.server_args.max_lora_rank,\n"
        "            target_modules=self.server_args.lora_target_modules,\n"
        "            lora_paths=self.server_args.lora_paths,\n"
        "            cuda_graph_max_bs=(\n"
        "                self.server_args.cuda_graph_max_bs\n"
        "                if not self.server_args.disable_cuda_graph\n"
        "                else None\n"
        "            ),\n"
        "        )\n"
    )
    assert old_init_lora_call in text
    text = text.replace(old_init_lora_call, new_init_lora_call)

    # Delete _init_lora_cuda_graph_moe_buffers method.
    old_moe_method = (
        "    def _init_lora_cuda_graph_moe_buffers(self):\n"
        '        """Phase 1 of LoRA CUDA graph init: pre-allocate MoE intermediate buffers.\n'
        "\n"
        "        Must be called before init_memory_pool() so that memory profiling\n"
        "        sees the reduced available memory and sizes KV cache correctly.\n"
        "        All MoE LoRA layers share one set of buffers (managed by the\n"
        "        lora_backend) since they execute sequentially during forward.\n"
        "\n"
        "        Phase 2 (dense LoRA batch metadata) is handled later in\n"
        "        CudaGraphRunner.__init__() via lora_manager.init_cuda_graph_batch_info(),\n"
        "        because it needs capture-time parameters (max_bs, num_tokens_per_bs)\n"
        "        that are only available at that stage.\n"
        '        """\n'
        "        from sglang.srt.lora.layers import FusedMoEWithLoRA\n"
        "\n"
        "        max_bs = self.server_args.cuda_graph_max_bs\n"
        "        max_loras = self.server_args.max_loras_per_batch\n"
        "        for module in self.model.modules():\n"
        "            if isinstance(module, FusedMoEWithLoRA):\n"
        "                self.lora_manager.init_cuda_graph_moe_buffers(\n"
        "                    max_bs, max_loras, self.dtype, module\n"
        "                )\n"
        "                logger.info(\n"
        '                    f"Pre-allocated shared MoE LoRA CUDA graph buffers "\n'
        '                    f"(max_bs={max_bs}, max_loras={max_loras})"\n'
        "                )\n"
        "                break\n"
        "\n"
    )
    assert old_moe_method in text
    text = text.replace(old_moe_method, "")

    mr.write_text(text)

    git_add_and_commit(
        "Refactor LoRAManager interface and inline MoE buffer prealloc",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
