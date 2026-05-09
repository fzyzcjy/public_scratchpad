#!/usr/bin/env python3
"""Reproducible transform: extract `ModelRunner.configure_kv_cache_dtype` to a
free function in a new module `sglang.srt.mem_cache.kv_cache_dtype`.
Strict-minimal mechanical move:
- KEEP function name as `configure_kv_cache_dtype` (NOT renamed).
- NO docstring added (original had none).
- NO type annotations on parameters.
- Body byte-identical with `self.X` -> kwarg substitutions, KEEP the entire
  if-elif-else chain unchanged including all branches and warning ordering.
- Return `(server_args.kv_cache_dtype, kv_cache_dtype)` at the end.
- Move `TORCH_DTYPE_TO_KV_CACHE_STR` from model_runner.py to the new file.
- ModelRunner: delete method, update sole caller.

Run from the repo root:
    python3 /tmp/transform_configure_kv_cache_dtype.py
"""

import sys
from pathlib import Path

sys.path.append(".claude/skills/mechanical-refactor-verify")
from mechanical_refactor_verify_utils import (
    verify_mechanical_refactor,
    git_add_and_commit,
)

BASE_COMMIT = "tom_refactor/22"
TARGET_COMMIT = "tom_refactor/23"


NEW_FILE_CONTENT = (
    "import logging\n"
    "\n"
    "import torch\n"
    "\n"
    "from sglang.srt.layers.quantization.fp8_kernel import fp8_dtype\n"
    "from sglang.srt.utils import is_hip, log_info_on_rank0\n"
    "\n"
    "logger = logging.getLogger(__name__)\n"
    "\n"
    "_is_hip = is_hip()\n"
    "\n"
    "TORCH_DTYPE_TO_KV_CACHE_STR = {\n"
    '    torch.float8_e4m3fn: "fp8_e4m3",\n'
    '    torch.float8_e4m3fnuz: "fp8_e4m3",\n'
    '    torch.float8_e5m2: "fp8_e5m2",\n'
    '    torch.bfloat16: "bf16",\n'
    "}\n"
    "\n"
    "\n"
    "def configure_kv_cache_dtype(server_args, *, quant_config, model_dtype):\n"
    '    if server_args.kv_cache_dtype == "auto":\n'
    '        kv_cache_quant_algo = getattr(quant_config, "kv_cache_quant_algo", None)\n'
    "        if (\n"
    "            isinstance(kv_cache_quant_algo, str)\n"
    '            and kv_cache_quant_algo.upper() == "FP8"\n'
    "        ):\n"
    "            if _is_hip:\n"
    "                kv_cache_dtype = fp8_dtype\n"
    "                server_args.kv_cache_dtype = TORCH_DTYPE_TO_KV_CACHE_STR[\n"
    "                    kv_cache_dtype\n"
    "                ]\n"
    "            else:\n"
    "                kv_cache_dtype = torch.float8_e4m3fn\n"
    "                server_args.kv_cache_dtype = TORCH_DTYPE_TO_KV_CACHE_STR[\n"
    "                    kv_cache_dtype\n"
    "                ]\n"
    "        else:\n"
    "            kv_cache_dtype = model_dtype\n"
    '    elif server_args.kv_cache_dtype == "fp8_e5m2":\n'
    "        if _is_hip:  # Using natively supported format\n"
    "            kv_cache_dtype = fp8_dtype\n"
    "        else:\n"
    "            kv_cache_dtype = torch.float8_e5m2\n"
    '    elif server_args.kv_cache_dtype == "fp8_e4m3":\n'
    "        if _is_hip:  # Using natively supported format\n"
    "            kv_cache_dtype = fp8_dtype\n"
    "        else:\n"
    "            kv_cache_dtype = torch.float8_e4m3fn\n"
    '    elif server_args.kv_cache_dtype in ("bf16", "bfloat16"):\n'
    "        kv_cache_dtype = torch.bfloat16\n"
    '    elif server_args.kv_cache_dtype == "fp4_e2m1":\n'
    '        if hasattr(torch, "float4_e2m1fn_x2"):\n'
    "            kv_cache_dtype = torch.float4_e2m1fn_x2\n"
    '            logger.warning(f"FP4 (E2M1) KV Cache might lead to a accuracy drop!")\n'
    "        else:\n"
    "            logger.warning(\n"
    "                f\"--kv-cache-dtype falls back to 'auto' because this torch version does not support torch.float4_e2m1fn_x2\"\n"
    "            )\n"
    "            kv_cache_dtype = model_dtype\n"
    "    else:\n"
    "        raise ValueError(\n"
    '            f"Unsupported kv_cache_dtype: {server_args.kv_cache_dtype}."\n'
    "        )\n"
    "\n"
    '    log_info_on_rank0(logger, f"Using KV cache dtype: {kv_cache_dtype}")\n'
    "    return server_args.kv_cache_dtype, kv_cache_dtype\n"
)


def transform(dir_root: Path) -> None:
    # --- Step 1: Create new module mem_cache/kv_cache_dtype.py ---
    new_file = dir_root / "python/sglang/srt/mem_cache/kv_cache_dtype.py"
    new_file.write_text(NEW_FILE_CONTENT)

    # --- Step 2: Update model_runner.py ---
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    text = mr.read_text()

    # Remove TORCH_DTYPE_TO_KV_CACHE_STR (moved to new file).
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

    # Delete the method.
    old_method = (
        "    def configure_kv_cache_dtype(self):\n"
        '        if self.server_args.kv_cache_dtype == "auto":\n'
        '            quant_config = getattr(self.model, "quant_config", None)\n'
        '            kv_cache_quant_algo = getattr(quant_config, "kv_cache_quant_algo", None)\n'
        "            if (\n"
        "                isinstance(kv_cache_quant_algo, str)\n"
        '                and kv_cache_quant_algo.upper() == "FP8"\n'
        "            ):\n"
        "                if _is_hip:\n"
        "                    self.kv_cache_dtype = fp8_dtype\n"
        "                    self.server_args.kv_cache_dtype = TORCH_DTYPE_TO_KV_CACHE_STR[\n"
        "                        self.kv_cache_dtype\n"
        "                    ]\n"
        "                else:\n"
        "                    self.kv_cache_dtype = torch.float8_e4m3fn\n"
        "                    self.server_args.kv_cache_dtype = TORCH_DTYPE_TO_KV_CACHE_STR[\n"
        "                        self.kv_cache_dtype\n"
        "                    ]\n"
        "            else:\n"
        "                self.kv_cache_dtype = self.dtype\n"
        '        elif self.server_args.kv_cache_dtype == "fp8_e5m2":\n'
        "            if _is_hip:  # Using natively supported format\n"
        "                self.kv_cache_dtype = fp8_dtype\n"
        "            else:\n"
        "                self.kv_cache_dtype = torch.float8_e5m2\n"
        '        elif self.server_args.kv_cache_dtype == "fp8_e4m3":\n'
        "            if _is_hip:  # Using natively supported format\n"
        "                self.kv_cache_dtype = fp8_dtype\n"
        "            else:\n"
        "                self.kv_cache_dtype = torch.float8_e4m3fn\n"
        '        elif self.server_args.kv_cache_dtype in ("bf16", "bfloat16"):\n'
        "            self.kv_cache_dtype = torch.bfloat16\n"
        '        elif self.server_args.kv_cache_dtype == "fp4_e2m1":\n'
        '            if hasattr(torch, "float4_e2m1fn_x2"):\n'
        "                self.kv_cache_dtype = torch.float4_e2m1fn_x2\n"
        '                logger.warning(f"FP4 (E2M1) KV Cache might lead to a accuracy drop!")\n'
        "            else:\n"
        "                logger.warning(\n"
        "                    f\"--kv-cache-dtype falls back to 'auto' because this torch version does not support torch.float4_e2m1fn_x2\"\n"
        "                )\n"
        "                self.kv_cache_dtype = self.dtype\n"
        "        else:\n"
        "            raise ValueError(\n"
        '                f"Unsupported kv_cache_dtype: {self.server_args.kv_cache_dtype}."\n'
        "            )\n"
        "\n"
        '        log_info_on_rank0(logger, f"Using KV cache dtype: {self.kv_cache_dtype}")\n\n'
    )
    assert old_method in text, "configure_kv_cache_dtype method not found"
    text = text.replace(old_method, "")

    # Replace the sole caller.
    text = text.replace(
        "        # Deduce KV cache dtype\n"
        "        self.configure_kv_cache_dtype()\n",
        "        # Deduce KV cache dtype\n"
        "        self.server_args.kv_cache_dtype, self.kv_cache_dtype = (\n"
        "            configure_kv_cache_dtype(\n"
        "                self.server_args,\n"
        '                quant_config=getattr(self.model, "quant_config", None),\n'
        "                model_dtype=self.dtype,\n"
        "            )\n"
        "        )\n",
    )

    # Add the import for the new free function (alphabetical position right
    # after `from sglang.srt.mem_cache.memory_pool import ReqToTokenPool`).
    text = text.replace(
        "from sglang.srt.mem_cache.memory_pool import ReqToTokenPool\n",
        "from sglang.srt.mem_cache.kv_cache_dtype import configure_kv_cache_dtype\n"
        "from sglang.srt.mem_cache.memory_pool import ReqToTokenPool\n",
    )

    mr.write_text(text)

    git_add_and_commit(
        "Extract configure_kv_cache_dtype to mem_cache.kv_cache_dtype",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
