#!/usr/bin/env python3
"""Prep stage for init-dist (MECH_COMMIT_SPLIT §"二段式"):

Reshape ``ModelRunner.init_torch_distributed`` (139-line method) toward
free-function form. Add ``@staticmethod`` + 15 kwargs; rewrite 15 ``self.X``
reads to bare kwarg names. The 3 group writebacks (``self.tp_group = ...``)
become locals + return a new ``TorchDistributedResult`` dataclass.

The dataclass needs to exist somewhere at prep time so the method body can
return it. Create the new module ``distributed/bootstrap.py`` with just the
dataclass; ``-move`` appends the function body to it. ModelRunner imports
the dataclass for the return; the caller unpacks attribute reads onto
``self.X``.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, insert_after, replace_call_site
from _runner import run_pr

ID = "init-dist-prep"
SUBJECT = "Prep init_torch_distributed for extraction: @staticmethod + 15 kwargs + TorchDistributedResult"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/extract-lora-moe-buffers-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_BOOTSTRAP_SKELETON = '''from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True, kw_only=True)
class TorchDistributedResult:
    tp_group: object
    pp_group: object
    attention_tp_group: object
    pre_model_load_memory: float
'''


_KWARGS = (
    "        *,\n"
    "        server_args: ServerArgs,\n"
    "        model_config: ModelConfig,\n"
    "        device: str,\n"
    "        gpu_id: int,\n"
    "        tp_rank: int,\n"
    "        tp_size: int,\n"
    "        pp_rank: int,\n"
    "        pp_size: int,\n"
    "        dp_size: int,\n"
    "        attn_cp_size: int,\n"
    "        moe_ep_size: int,\n"
    "        moe_dp_size: int,\n"
    "        dist_port: int,\n"
    "        is_draft_worker: bool,\n"
    "        local_omp_cpuid: Optional[List[int]],\n"
)


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    bootstrap = wt / "python/sglang/srt/distributed/bootstrap.py"

    # Create bootstrap.py with just the dataclass.
    bootstrap.parent.mkdir(parents=True, exist_ok=True)
    bootstrap.write_text(_BOOTSTRAP_SKELETON)

    # Reshape the method in place.
    text = mr.read_text()
    start, end = find_method_lines(text, class_name="ModelRunner", method_name="init_torch_distributed")
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    method = method.replace(
        "    def init_torch_distributed(self):\n",
        f"    @staticmethod\n    def init_torch_distributed(\n{_KWARGS}    ):\n",
        1,
    )
    # Body: replace 15 self.X reads.
    for name in (
        "device", "gpu_id", "tp_rank", "tp_size", "pp_rank", "pp_size",
        "dp_size", "attn_cp_size", "moe_ep_size", "moe_dp_size",
        "dist_port", "is_draft_worker", "local_omp_cpuid",
        "server_args", "model_config",
    ):
        method = method.replace(f"self.{name}", name)
    # 3 group writebacks → locals (body is at 8-space indent inside class).
    method = method.replace(
        "        self.tp_group = get_tp_group()\n"
        "        self.pp_group = get_pp_group()\n"
        "        self.attention_tp_group = get_attention_tp_group()\n",
        "        tp_group = get_tp_group()\n"
        "        pp_group = get_pp_group()\n"
        "        attention_tp_group = get_attention_tp_group()\n",
    )
    # Return wraps the 4 values in TorchDistributedResult.
    method = method.replace(
        "        return pre_model_load_memory\n",
        "        return TorchDistributedResult(\n"
        "            tp_group=tp_group,\n"
        "            pp_group=pp_group,\n"
        "            attention_tp_group=attention_tp_group,\n"
        "            pre_model_load_memory=pre_model_load_memory,\n"
        "        )\n",
    )
    text = "".join(lines[:start]) + method + "".join(lines[end:])

    # ModelRunner needs TorchDistributedResult in scope for the return.
    text = insert_after(
        text,
        anchor="from sglang.srt.distributed.parallel_state import monkey_patch_vllm_parallel_state\n",
        addition="from sglang.srt.distributed.bootstrap import TorchDistributedResult\n",
    )

    # Caller in initialize() — class-qualified + unpack onto self.
    text = replace_call_site(
        text,
        old="        pre_model_load_memory = self.init_torch_distributed()\n",
        new=(
            "        result = ModelRunner.init_torch_distributed(\n"
            "            server_args=self.server_args,\n"
            "            model_config=self.model_config,\n"
            "            device=self.device,\n"
            "            gpu_id=self.gpu_id,\n"
            "            tp_rank=self.tp_rank,\n"
            "            tp_size=self.tp_size,\n"
            "            pp_rank=self.pp_rank,\n"
            "            pp_size=self.pp_size,\n"
            "            dp_size=self.dp_size,\n"
            "            attn_cp_size=self.attn_cp_size,\n"
            "            moe_ep_size=self.moe_ep_size,\n"
            "            moe_dp_size=self.moe_dp_size,\n"
            "            dist_port=self.dist_port,\n"
            "            is_draft_worker=self.is_draft_worker,\n"
            "            local_omp_cpuid=self.local_omp_cpuid if self.device == \"cpu\" else None,\n"
            "        )\n"
            "        self.tp_group = result.tp_group\n"
            "        self.pp_group = result.pp_group\n"
            "        self.attention_tp_group = result.attention_tp_group\n"
            "        pre_model_load_memory = result.pre_model_load_memory\n"
        ),
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
