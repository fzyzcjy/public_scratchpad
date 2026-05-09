#!/usr/bin/env python3
"""Cut `_init_lora_cuda_graph_moe_buffers` from ModelRunner; absorb its body
into `LoRAManager.__init__` (gated on a new `cuda_graph_max_bs` kwarg). Update
caller (`init_lora_manager`) to pass the kwarg, and drop the Phase 1 if-block
in `initialize()`.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import (
    cut_lines,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/37"
TARGET_COMMIT = "tom_refactor/38"


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    lm = dir_root / "python/sglang/srt/lora/lora_manager.py"

    # ---- Cut _init_lora_cuda_graph_moe_buffers from ModelRunner ----
    start, end = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="_init_lora_cuda_graph_moe_buffers",
    )
    cut_lines(mr, start, end)

    # ---- Update LoRAManager: add kwarg + Phase 1 init block ----
    text = lm.read_text()

    # Add `cuda_graph_max_bs` kwarg (after `lora_paths`, before close paren).
    text = replace_call_site(
        text,
        old="        lora_paths: Optional[List[LoRARef]] = None,\n    ):\n        self.base_model: torch.nn.Module = base_model\n",
        new="        lora_paths: Optional[List[LoRARef]] = None,\n        cuda_graph_max_bs: Optional[int] = None,\n    ):\n        self.base_model: torch.nn.Module = base_model\n",
    )

    # Mirror the kwarg on `init_state` (carried for symmetry).
    text = replace_call_site(
        text,
        old=(
            "    def init_state(\n"
            "        self,\n"
            "        max_lora_rank: Optional[int] = None,\n"
            "        target_modules: Optional[Iterable[str]] = None,\n"
            "        lora_paths: Optional[List[LoRARef]] = None,\n"
            "    ):\n"
        ),
        new=(
            "    def init_state(\n"
            "        self,\n"
            "        max_lora_rank: Optional[int] = None,\n"
            "        target_modules: Optional[Iterable[str]] = None,\n"
            "        lora_paths: Optional[List[LoRARef]] = None,\n"
            "        cuda_graph_max_bs: Optional[int] = None,\n"
            "    ):\n"
        ),
    )

    # Add `get_available_gpu_memory` to grouped import (alphabetical).
    text = replace_call_site(
        text,
        old="from sglang.srt.utils import replace_submodule\n",
        new="from sglang.srt.utils import get_available_gpu_memory, replace_submodule\n",
    )

    # Append the Phase 1 init block after the `self.init_state(...)` call at
    # the end of `__init__`.
    init_state_block = (
        "        # Initialize mutable internal state of the LoRAManager.\n"
        "        self.init_state(\n"
        "            max_lora_rank=max_lora_rank,\n"
        "            target_modules=target_modules,\n"
        "            lora_paths=lora_paths,\n"
        "        )\n"
    )
    phase1_block = (
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
        '                        f"Pre-allocated shared MoE LoRA CUDA graph buffers "\n'
        '                        f"(max_bs={cuda_graph_max_bs}, max_loras={max_loras_per_batch})"\n'
        "                    )\n"
        "                    break\n"
    )
    text = insert_after(text, anchor=init_state_block, addition=phase1_block)
    lm.write_text(text)

    # ---- Update ModelRunner: caller + drop Phase 1 if-block ----
    text = mr.read_text()

    # Drop the Phase 1 if-block in `initialize()`.
    text = replace_call_site(
        text,
        old=(
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
        ),
        new=(
            "        # Init lora\n"
            "        if server_args.enable_lora:\n"
            "            self.init_lora_manager()\n"
        ),
    )

    # Pass `cuda_graph_max_bs` from `init_lora_manager`.
    text = replace_call_site(
        text,
        old=(
            "            target_modules=self.server_args.lora_target_modules,\n"
            "            lora_paths=self.server_args.lora_paths,\n"
            "        )\n"
        ),
        new=(
            "            target_modules=self.server_args.lora_target_modules,\n"
            "            lora_paths=self.server_args.lora_paths,\n"
            "            cuda_graph_max_bs=(\n"
            "                self.server_args.cuda_graph_max_bs\n"
            "                if not self.server_args.disable_cuda_graph\n"
            "                else None\n"
            "            ),\n"
            "        )\n"
        ),
    )

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
