#!/usr/bin/env python3
"""Cut `prealloc_symmetric_memory_pool` from ModelRunner; paste in pynccl_allocator."""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import (
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/21"
TARGET_COMMIT = "tom_refactor/22"


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    allocator = dir_root / "python/sglang/srt/distributed/device_communicators/pynccl_allocator.py"

    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="prealloc_symmetric_memory_pool"
    )
    method_text = cut_lines(mr, start, end)
    fn = dedent_method_to_function(method_text)
    fn = fn.replace(
        "def prealloc_symmetric_memory_pool(self):\n",
        "def prealloc_symmetric_memory_pool(\n    *,\n    is_draft_worker: bool,\n"
        "    enable_symm_mem: bool,\n    device: str,\n    forward_stream: torch.cuda.Stream,\n):\n",
    )
    fn = fn.replace("self.is_draft_worker", "is_draft_worker")
    fn = fn.replace("self.server_args.enable_symm_mem", "enable_symm_mem")
    fn = fn.replace("self.forward_stream", "forward_stream")
    fn = fn.replace("self.device", "device")
    fn = fn.replace(
        "        return\n\n    # Memory allocation",
        "        return\n\n    # Local import to avoid an import-time cycle with get_tp_group.\n"
        "    from sglang.srt.distributed import get_tp_group\n\n    # Memory allocation",
    )

    a_text = allocator.read_text()
    if "\nlogger = logging.getLogger(__name__)\n" not in a_text:
        a_text = a_text.replace(
            "_symm_mem_logger = logging.getLogger(__name__)\n",
            "_symm_mem_logger = logging.getLogger(__name__)\nlogger = logging.getLogger(__name__)\n",
        )
        allocator.write_text(a_text)
    append_to_file(allocator, fn)

    text = mr.read_text()
    text = text.replace(
        "        self.prealloc_symmetric_memory_pool()\n",
        "        prealloc_symmetric_memory_pool(\n"
        "            is_draft_worker=self.is_draft_worker,\n"
        "            enable_symm_mem=self.server_args.enable_symm_mem,\n"
        "            device=self.device,\n"
        "            forward_stream=self.forward_stream,\n        )\n",
    )
    text = text.replace(
        "    use_symmetric_memory,\n)\n",
        "    prealloc_symmetric_memory_pool,\n    use_symmetric_memory,\n)\n",
    )
    mr.write_text(text)

    git_add_and_commit(
        "Extract prealloc_symmetric_memory_pool to free function", cwd=str(dir_root)
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT, target_commit=TARGET_COMMIT, transform=transform
    )
