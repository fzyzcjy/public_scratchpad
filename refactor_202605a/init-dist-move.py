#!/usr/bin/env python3
"""Move stage for init-dist (MECH_COMMIT_SPLIT §"二段式"):

Cut the prep'd staticmethod to ``distributed/bootstrap.py``. Body byte-equivalent.
Adds the body's import requirements to bootstrap.py. Caller prefix-strip:
``ModelRunner.init_torch_distributed(`` → ``init_torch_distributed(``.
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

ID = "init-dist-move"
SUBJECT = "Move init_torch_distributed to distributed.bootstrap (cut+paste)"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/init-dist-prep"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


_BODY_IMPORTS = '''import logging
import os
import time
from typing import List, Optional

import torch
import torch.distributed as dist

from sglang.srt.configs.model_config import ModelConfig
from sglang.srt.distributed import (
    get_default_distributed_backend,
    get_pp_group,
    get_tp_group,
    get_world_group,
    init_distributed_environment,
    initialize_model_parallel,
    set_custom_all_reduce,
    set_mscclpp_all_reduce,
    set_torch_symm_mem_all_reduce,
)
from sglang.srt.environ import envs
from sglang.srt.layers.dp_attention import (
    get_attention_tp_group,
    initialize_dp_attention,
)
from sglang.srt.server_args import ServerArgs
from sglang.srt.utils import (
    cpu_has_amx_support,
    get_available_gpu_memory,
    is_host_cpu_arm64,
    is_npu,
    monkey_patch_p2p_access_check,
)
from sglang.srt.utils.network import NetworkAddress
from sglang.srt.utils.patch_torch import register_sgl_tp_rank


logger = logging.getLogger(__name__)

_is_cpu_amx_available = cpu_has_amx_support()
_is_cpu_arm64 = is_host_cpu_arm64()


'''


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    bootstrap = wt / "python/sglang/srt/distributed/bootstrap.py"

    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="init_torch_distributed")
    method_text = cut_lines(mr, s, e)
    lines = method_text.splitlines(keepends=True)
    assert lines[0].strip() == "@staticmethod"
    function_text = dedent_method_to_function("".join(lines[1:]))

    # bootstrap.py: prepend body-imports BEFORE the dataclass definition.
    bootstrap_text = bootstrap.read_text()
    bootstrap_text = _BODY_IMPORTS + bootstrap_text.replace("from __future__ import annotations\n\n", "", 1)
    bootstrap.write_text(bootstrap_text)
    append_to_file(bootstrap, function_text)

    # ModelRunner: prefix-strip caller + swap import from dataclass to function.
    text = mr.read_text()
    text = replace_call_site(text, old="ModelRunner.init_torch_distributed(", new="init_torch_distributed(")
    text = replace_call_site(
        text,
        old="from sglang.srt.distributed.bootstrap import TorchDistributedResult\n",
        new="from sglang.srt.distributed.bootstrap import init_torch_distributed\n",
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
