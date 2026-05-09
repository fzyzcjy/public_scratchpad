#!/usr/bin/env python3
"""Reproducible transform: extract `ModelRunner.prealloc_symmetric_memory_pool`
to a free function in
`sglang.srt.distributed.device_communicators.pynccl_allocator`.

Strict-minimal mechanical move:
- KEEP the function name and parameter names (no rename).
- NO docstring added.
- NO type annotations added beyond what existed (kwargs annotated with their
  types because the call site needs explicit kwargs and the module already
  imports `torch`; this matches the existing free-function style in this file).
- Body byte-identical with `self.X` -> kwarg substitution.
- KEEP the `# PyTorch mempools never de-fragment...` comment (original had it).
- Local import `from sglang.srt.distributed import get_tp_group` is added inside
  the function (necessary because `get_tp_group` was implicitly available via
  ModelRunner's imports before; importing at module level here would create an
  import-time cycle with `sglang.srt.distributed`).
- ModelRunner method is deleted; sole caller updated to invoke the free func.

Run from the repo root:
    python3 /tmp/transform_prealloc_symmetric_memory_pool.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/21"
TARGET_COMMIT = "tom_refactor/22"


def transform(dir_root: Path) -> None:
    # --- Step 1: Append free function to pynccl_allocator.py ---
    allocator = (
        dir_root
        / "python/sglang/srt/distributed/device_communicators/pynccl_allocator.py"
    )
    text = allocator.read_text()
    text = text.rstrip() + (
        "\n\n\ndef prealloc_symmetric_memory_pool(\n"
        "    *,\n"
        "    is_draft_worker: bool,\n"
        "    enable_symm_mem: bool,\n"
        "    device: str,\n"
        "    forward_stream: torch.cuda.Stream,\n"
        "):\n"
        "    # PyTorch mempools never de-fragment memory in OOM scenarios, so we need to pre-allocate a large chunk of memory to limit fragmentation.\n"
        "    if (\n"
        "        is_draft_worker\n"
        "        or not enable_symm_mem\n"
        "        or envs.SGLANG_SYMM_MEM_PREALLOC_GB_SIZE.get() <= 0\n"
        "    ):\n"
        "        return\n\n"
        "    # Local import to avoid an import-time cycle with get_tp_group.\n"
        "    from sglang.srt.distributed import get_tp_group\n\n"
        "    # Memory allocation is tied to a cuda stream, use the forward stream\n"
        "    with torch.get_device_module(device).stream(forward_stream):\n"
        "        logger.info(\n"
        '            f"Pre-allocating symmetric memory pool with {envs.SGLANG_SYMM_MEM_PREALLOC_GB_SIZE.get()} GiB"\n'
        "        )\n"
        "        with use_symmetric_memory(get_tp_group()):\n"
        "            torch.empty(\n"
        "                (envs.SGLANG_SYMM_MEM_PREALLOC_GB_SIZE.get() * 1024 * 1024 * 1024,),\n"
        "                dtype=torch.uint8,\n"
        "                device=device,\n"
        "            )\n"
    )
    # NOTE: pynccl_allocator.py uses `_symm_mem_logger` (module-level
    # `logging.getLogger(__name__)` aliased) for symm-mem debug warnings, but
    # the original ModelRunner method used the model_runner module's `logger`.
    # The byte-identical rule says we must use `logger.info(...)` here. The
    # file does not have a top-level `logger = ...`, only `_symm_mem_logger`.
    # If `logger` is not defined in pynccl_allocator.py at base, the function
    # will NameError. Resolve by also adding a `logger = logging.getLogger(__name__)`
    # at module level (next to `_symm_mem_logger`). This is necessary
    # infrastructure (matches the apply_torch_tp pattern in /19).
    if "\nlogger = logging.getLogger(__name__)\n" not in text:
        text = text.replace(
            "_symm_mem_logger = logging.getLogger(__name__)\n",
            "_symm_mem_logger = logging.getLogger(__name__)\n"
            "logger = logging.getLogger(__name__)\n",
        )
    allocator.write_text(text)

    # --- Step 2: Update model_runner.py ---
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    old_method = (
        "    def prealloc_symmetric_memory_pool(self):\n"
        "        # PyTorch mempools never de-fragment memory in OOM scenarios, so we need to pre-allocate a large chunk of memory to limit fragmentation.\n"
        "        if (\n"
        "            self.is_draft_worker\n"
        "            or not self.server_args.enable_symm_mem\n"
        "            or envs.SGLANG_SYMM_MEM_PREALLOC_GB_SIZE.get() <= 0\n"
        "        ):\n"
        "            return\n\n"
        "        # Memory allocation is tied to a cuda stream, use the forward stream\n"
        "        with torch.get_device_module(self.device).stream(self.forward_stream):\n"
        "            logger.info(\n"
        '                f"Pre-allocating symmetric memory pool with {envs.SGLANG_SYMM_MEM_PREALLOC_GB_SIZE.get()} GiB"\n'
        "            )\n"
        "            with use_symmetric_memory(get_tp_group()):\n"
        "                torch.empty(\n"
        "                    (envs.SGLANG_SYMM_MEM_PREALLOC_GB_SIZE.get() * 1024 * 1024 * 1024,),\n"
        "                    dtype=torch.uint8,\n"
        "                    device=self.device,\n"
        "                )\n\n"
    )
    assert old_method in text, "prealloc_symmetric_memory_pool method not found"
    text = text.replace(old_method, "")

    # Update sole caller.
    text = text.replace(
        "        self.prealloc_symmetric_memory_pool()\n",
        "        prealloc_symmetric_memory_pool(\n"
        "            is_draft_worker=self.is_draft_worker,\n"
        "            enable_symm_mem=self.server_args.enable_symm_mem,\n"
        "            device=self.device,\n"
        "            forward_stream=self.forward_stream,\n"
        "        )\n",
    )

    # Add the import. The pynccl_allocator import already exists (used for
    # `use_symmetric_memory`); extend it with `prealloc_symmetric_memory_pool`.
    text = text.replace(
        "from sglang.srt.distributed.device_communicators.pynccl_allocator import (\n"
        "    use_symmetric_memory,\n"
        ")\n",
        "from sglang.srt.distributed.device_communicators.pynccl_allocator import (\n"
        "    prealloc_symmetric_memory_pool,\n"
        "    use_symmetric_memory,\n"
        ")\n",
    )

    mr.write_text(text)

    git_add_and_commit(
        "Extract prealloc_symmetric_memory_pool to free function",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
