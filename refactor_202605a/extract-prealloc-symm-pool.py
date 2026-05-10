#!/usr/bin/env python3
"""Cut `prealloc_symmetric_memory_pool` from ModelRunner; paste as a free
function in `pynccl_allocator.py`. Update sole caller.

Usage:
    uv run --python 3.12 extract-prealloc-symm-pool.py run
    uv run --python 3.12 extract-prealloc-symm-pool.py verify
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
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
    insert_after,
    replace_call_site,
)
from _runner import run_pr

ID = "extract-prealloc-symm-pool"
SUBJECT = "Extract prealloc_symmetric_memory_pool to free function"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/inline-max-pool-size"
AREA_BRANCH = f"tom_refactor_202605a/raw/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    allocator = wt / "python/sglang/srt/distributed/device_communicators/pynccl_allocator.py"

    start, end = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="prealloc_symmetric_memory_pool",
    )
    method_text = cut_lines(mr, start, end)
    fn = (
        dedent_method_to_function(method_text)
        .replace(
            "def prealloc_symmetric_memory_pool(self):\n",
            "def prealloc_symmetric_memory_pool(\n"
            "    *,\n"
            "    is_draft_worker: bool,\n"
            "    enable_symm_mem: bool,\n"
            "    device: str,\n"
            "    forward_stream: torch.cuda.Stream,\n"
            "):\n",
        )
        .replace("self.is_draft_worker", "is_draft_worker")
        .replace("self.server_args.enable_symm_mem", "enable_symm_mem")
        .replace("self.forward_stream", "forward_stream")
        .replace("self.device", "device")
        # Local `from sglang.srt.distributed import get_tp_group` import is
        # kept inside the function body — `sglang.srt.distributed` indirectly
        # imports this module via parallel_state, so a top-level import would
        # introduce a cycle (matches the original method's pattern).
        .replace(
            "        return\n\n    # Memory allocation",
            "        return\n\n    from sglang.srt.distributed import get_tp_group\n\n    # Memory allocation",
        )
    )

    a_text = allocator.read_text()
    if "\nlogger = logging.getLogger(__name__)\n" not in a_text:
        a_text = insert_after(
            a_text,
            anchor="_symm_mem_logger = logging.getLogger(__name__)\n",
            addition="logger = logging.getLogger(__name__)\n",
        )
        allocator.write_text(a_text)
    append_to_file(allocator, fn)

    text = mr.read_text()
    text = replace_call_site(
        text,
        old="        self.prealloc_symmetric_memory_pool()\n",
        new=(
            "        prealloc_symmetric_memory_pool(\n"
            "            is_draft_worker=self.is_draft_worker,\n"
            "            enable_symm_mem=self.server_args.enable_symm_mem,\n"
            "            device=self.device,\n"
            "            forward_stream=self.forward_stream,\n"
            "        )\n"
        ),
    )
    text = replace_call_site(
        text,
        old="    use_symmetric_memory,\n)\n",
        new="    prealloc_symmetric_memory_pool,\n    use_symmetric_memory,\n)\n",
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
