#!/usr/bin/env python3
"""Cut `configure_kv_cache_dtype` and `TORCH_DTYPE_TO_KV_CACHE_STR` to new file mem_cache/kv_cache_dtype.py."""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import append_to_file, cut_lines, dedent_method_to_function, find_method_lines
from mechanical_refactor_verify_utils import git_add_and_commit, verify_mechanical_refactor

BASE_COMMIT = "tom_refactor/22"
TARGET_COMMIT = "tom_refactor/23"

NEW_HEADER = (
    "import logging\n\nimport torch\n\n"
    "from sglang.srt.layers.quantization.fp8_kernel import fp8_dtype\n"
    "from sglang.srt.utils import is_hip, log_info_on_rank0\n\n"
    "logger = logging.getLogger(__name__)\n\n_is_hip = is_hip()\n"
)


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    new_file = dir_root / "python/sglang/srt/mem_cache/kv_cache_dtype.py"

    start, end = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="configure_kv_cache_dtype"
    )
    method_text = cut_lines(mr, start, end)
    fn = dedent_method_to_function(method_text)
    fn = fn.replace(
        "def configure_kv_cache_dtype(self):\n",
        "def configure_kv_cache_dtype(server_args, *, quant_config, model_dtype):\n",
    )
    fn = fn.replace(
        '    if server_args.kv_cache_dtype == "auto":\n        quant_config = getattr(self.model, "quant_config", None)\n        kv_cache_quant_algo',
        '    if server_args.kv_cache_dtype == "auto":\n        kv_cache_quant_algo',
    )
    fn = fn.replace("self.server_args", "server_args")
    fn = fn.replace("self.kv_cache_dtype = ", "kv_cache_dtype = ")
    fn = fn.replace("self.kv_cache_dtype", "kv_cache_dtype")
    fn = fn.replace("self.dtype", "model_dtype")
    fn = fn.rstrip() + "\n    return server_args.kv_cache_dtype, kv_cache_dtype\n"

    text = mr.read_text()
    old_const = (
        "TORCH_DTYPE_TO_KV_CACHE_STR = {\n"
        '    torch.float8_e4m3fn: "fp8_e4m3",\n'
        '    torch.float8_e4m3fnuz: "fp8_e4m3",\n'
        '    torch.float8_e5m2: "fp8_e5m2",\n'
        '    torch.bfloat16: "bf16",\n'
        "}\n\n\n"
    )
    assert old_const in text, "TORCH_DTYPE_TO_KV_CACHE_STR not found"
    text = text.replace(old_const, "")
    text = text.replace(
        "        self.configure_kv_cache_dtype()\n",
        "        self.server_args.kv_cache_dtype, self.kv_cache_dtype = (\n"
        "            configure_kv_cache_dtype(\n                self.server_args,\n"
        '                quant_config=getattr(self.model, "quant_config", None),\n'
        "                model_dtype=self.dtype,\n            )\n        )\n")
    text = text.replace(
        "from sglang.srt.mem_cache.memory_pool import ReqToTokenPool\n",
        "from sglang.srt.mem_cache.kv_cache_dtype import configure_kv_cache_dtype\n"
        "from sglang.srt.mem_cache.memory_pool import ReqToTokenPool\n",
    )
    mr.write_text(text)

    new_file.write_text(NEW_HEADER + "\n" + old_const.rstrip() + "\n")
    append_to_file(new_file, fn)

    git_add_and_commit(
        "Extract configure_kv_cache_dtype to mem_cache.kv_cache_dtype",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT, target_commit=TARGET_COMMIT, transform=transform
    )
