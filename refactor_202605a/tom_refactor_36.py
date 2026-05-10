#!/usr/bin/env python3
"""Cut leaf helpers `_should_run_flashinfer_autotune` and
`_flashinfer_autotune_cache_path` from ModelRunner; paste as free functions
in new file `model_executor/kernel_warmup.py`. Update the in-class callers
(inside `kernel_warmup` / `_flashinfer_autotune`, still on ModelRunner) and
add an aliased import.
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

BASE = "tom_refactor/35"
TARGET = "tom_refactor/36"


_HEADER = (
    "from __future__ import annotations\n"
    "\n"
    "import hashlib\n"
    "from pathlib import Path\n"
    "\n"
    "import torch\n"
    "\n"
    "from sglang.srt.configs.model_config import ModelConfig\n"
    "from sglang.srt.environ import envs\n"
    "from sglang.srt.server_args import ServerArgs\n"
    "from sglang.srt.speculative.spec_info import SpeculativeAlgorithm\n"
)


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    kw = wt / "python/sglang/srt/model_executor/kernel_warmup.py"

    kw.write_text(_HEADER)

    # ---- Cut _should_run_flashinfer_autotune. ----
    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="_should_run_flashinfer_autotune",
    )
    fn = dedent_method_to_function(cut_lines(mr, s, e))
    fn = fn.replace(
        "def _should_run_flashinfer_autotune(self) -> bool:\n",
        "def _should_run_flashinfer_autotune(\n"
        "    *,\n"
        "    server_args: ServerArgs,\n"
        "    spec_algorithm: SpeculativeAlgorithm,\n"
        "    is_draft_worker: bool,\n"
        ") -> bool:\n",
    )
    fn = fn.replace("self.server_args", "server_args")
    fn = fn.replace("self.spec_algorithm", "spec_algorithm")
    fn = fn.replace("self.is_draft_worker", "is_draft_worker")
    append_to_file(kw, fn)

    # ---- Cut _flashinfer_autotune_cache_path. ----
    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="_flashinfer_autotune_cache_path",
    )
    fn = dedent_method_to_function(cut_lines(mr, s, e))
    fn = fn.replace(
        "def _flashinfer_autotune_cache_path(self) -> Path:\n",
        "def _flashinfer_autotune_cache_path(\n"
        "    *,\n"
        "    server_args: ServerArgs,\n"
        "    model_config: ModelConfig,\n"
        "    dtype: torch.dtype,\n"
        "    device: str,\n"
        "    tp_rank: int,\n"
        "    tp_size: int,\n"
        "    pp_rank: int,\n"
        "    pp_size: int,\n"
        "    dp_rank: int,\n"
        "    dp_size: int,\n"
        "    moe_ep_size: int,\n"
        ") -> Path:\n",
    )
    fn = fn.replace("torch.cuda.get_device_capability(self.device)",
                    "torch.cuda.get_device_capability(device)")
    fn = fn.replace("self.server_args", "server_args")
    fn = fn.replace("self.dtype", "dtype")
    fn = fn.replace("self.tp_size", "tp_size")
    fn = fn.replace("self.pp_size", "pp_size")
    fn = fn.replace("self.dp_size", "dp_size")
    fn = fn.replace("self.moe_ep_size", "moe_ep_size")
    fn = fn.replace("self.model_config", "model_config")
    fn = fn.replace("self.tp_rank", "tp_rank")
    fn = fn.replace("self.pp_rank", "pp_rank")
    fn = fn.replace("self.dp_rank", "dp_rank")
    append_to_file(kw, fn)

    # ---- Update model_runner.py: in-class callers + import. ----
    text = mr.read_text()

    text = replace_call_site(
        text,
        old="if self._should_run_flashinfer_autotune():",
        new=(
            "if _should_run_flashinfer_autotune(\n"
            "            server_args=self.server_args,\n"
            "            spec_algorithm=self.spec_algorithm,\n"
            "            is_draft_worker=self.is_draft_worker,\n"
            "        ):"
        ),
    )

    text = replace_call_site(
        text,
        old="cache_path = self._flashinfer_autotune_cache_path()",
        new=(
            "cache_path = _flashinfer_autotune_cache_path(\n"
            "            server_args=self.server_args,\n"
            "            model_config=self.model_config,\n"
            "            dtype=self.dtype,\n"
            "            device=self.device,\n"
            "            tp_rank=self.tp_rank,\n"
            "            tp_size=self.tp_size,\n"
            "            pp_rank=self.pp_rank,\n"
            "            pp_size=self.pp_size,\n"
            "            dp_rank=self.dp_rank,\n"
            "            dp_size=self.dp_size,\n"
            "            moe_ep_size=self.moe_ep_size,\n"
            "        )"
        ),
    )

    text = insert_after(
        text,
        anchor=(
            "from sglang.srt.model_executor.cuda_graph_runner import (\n"
            "    DecodeInputBuffers,\n"
            "    set_torch_compile_config,\n"
            ")\n"
        ),
        addition=(
            "from sglang.srt.model_executor.kernel_warmup import (\n"
            "    _flashinfer_autotune_cache_path,\n"
            "    _should_run_flashinfer_autotune,\n"
            ")\n"
        ),
    )

    mr.write_text(text)

    git_add_and_commit(
        "Extract _should_run_flashinfer_autotune and _flashinfer_autotune_cache_path to free functions",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
