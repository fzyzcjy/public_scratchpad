#!/usr/bin/env python3
"""Move stage for extract-kv-cache-dtype (MECH_COMMIT_SPLIT §"二段式"):

Cut+paste the staticmethod + ``TORCH_DTYPE_TO_KV_CACHE_STR`` constant into
the new file ``mem_cache/kv_cache_dtype.py``. Body byte-equivalent.
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
    replace_call_site,
)
from _runner import run_pr

ID = "extract-kv-cache-dtype-move"
SUBJECT = "Move configure_kv_cache_dtype + TORCH_DTYPE_TO_KV_CACHE_STR to mem_cache.kv_cache_dtype (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-kv-cache-dtype-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


NEW_HEADER = (
    "import logging\n\n"
    "import torch\n"
    "from torch import nn\n\n"
    "from sglang.srt.layers.quantization.fp8_kernel import fp8_dtype\n"
    "from sglang.srt.server_args import ServerArgs\n"
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
        mr.read_text(), class_name="ModelRunner", method_name="configure_kv_cache_dtype"
    )
    method_text = cut_lines(mr, start, end)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    function_text = dedent_method_to_function("".join(lines[1:]))

    text = mr.read_text()
    assert OLD_CONST in text, "TORCH_DTYPE_TO_KV_CACHE_STR not found"
    text = text.replace(OLD_CONST, "")
    text = replace_call_site(
        text,
        old="ModelRunner.configure_kv_cache_dtype(",
        new="configure_kv_cache_dtype(",
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

    new_file.write_text(NEW_HEADER + "\n\n" + OLD_CONST.rstrip() + "\n")
    append_to_file(new_file, function_text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
