#!/usr/bin/env python3
"""Cut `configure_kv_cache_dtype` and `TORCH_DTYPE_TO_KV_CACHE_STR` from
ModelRunner to a new file `mem_cache/kv_cache_dtype.py`. The free function
returns a 2-tuple; caller unpacks directly.

Usage:
    uv run --python 3.12 extract-kv-cache-dtype.py run
    uv run --python 3.12 extract-kv-cache-dtype.py verify
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

ID = "extract-kv-cache-dtype"
SUBJECT = "Extract configure_kv_cache_dtype to mem_cache.kv_cache_dtype"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/raw/mech_model_runner/extract-prealloc-symm-pool"
AREA_BRANCH = f"tom_refactor_202605a/raw/{AREA}"


NEW_HEADER = (
    "import logging\n\n"
    "import torch\n\n"
    "from sglang.srt.layers.quantization.fp8_kernel import fp8_dtype\n"
    "from sglang.srt.utils import is_hip, log_info_on_rank0\n\n"
    "logger = logging.getLogger(__name__)\n\n"
    "_is_hip = is_hip()\n"
)

OLD_CONST = (
    "TORCH_DTYPE_TO_KV_CACHE_STR = {\n"
    '    torch.float8_e4m3fn: "fp8_e4m3",\n'
    '    torch.float8_e4m3fnuz: "fp8_e4m3",\n'
    '    torch.float8_e5m2: "fp8_e5m2",\n'
    '    torch.bfloat16: "bf16",\n'
    "}\n\n\n"
)


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    new_file = wt / "python/sglang/srt/mem_cache/kv_cache_dtype.py"

    start, end = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="configure_kv_cache_dtype",
    )
    method_text = cut_lines(mr, start, end)
    fn = (
        dedent_method_to_function(method_text)
        .replace(
            "def configure_kv_cache_dtype(self):\n",
            "def configure_kv_cache_dtype(\n"
            "    *,\n"
            "    server_args: ServerArgs,\n"
            "    model: nn.Module,\n"
            "    model_dtype: torch.dtype,\n"
            ") -> tuple[str, torch.dtype]:\n",
        )
        .replace("self.server_args", "server_args")
        .replace("self.model", "model")
        .replace("self.kv_cache_dtype = ", "kv_cache_dtype = ")
        .replace("self.kv_cache_dtype", "kv_cache_dtype")
        .replace("self.dtype", "model_dtype")
    )
    fn = fn.rstrip() + "\n    return server_args.kv_cache_dtype, kv_cache_dtype\n"

    # Add the typing-related global imports the new signature needs.
    header_with_imports = NEW_HEADER.replace(
        "import torch\n",
        "import torch\nfrom torch import nn\n\n"
        "from sglang.srt.server_args import ServerArgs\n",
    )

    text = mr.read_text()
    assert OLD_CONST in text, "TORCH_DTYPE_TO_KV_CACHE_STR not found"
    text = text.replace(OLD_CONST, "")
    text = replace_call_site(
        text,
        old="        self.configure_kv_cache_dtype()\n",
        new=(
            "        self.server_args.kv_cache_dtype, self.kv_cache_dtype = (\n"
            "            configure_kv_cache_dtype(\n"
            "                server_args=self.server_args,\n"
            "                model=self.model,\n"
            "                model_dtype=self.dtype,\n"
            "            )\n"
            "        )\n"
        ),
    )
    text = replace_call_site(
        text,
        old="from sglang.srt.mem_cache.memory_pool import ReqToTokenPool\n",
        new=(
            "from sglang.srt.mem_cache.kv_cache_dtype import configure_kv_cache_dtype\n"
            "from sglang.srt.mem_cache.memory_pool import ReqToTokenPool\n"
        ),
    )
    mr.write_text(text)

    new_file.write_text(header_with_imports + "\n\n" + OLD_CONST.rstrip() + "\n")
    append_to_file(new_file, fn)

if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
