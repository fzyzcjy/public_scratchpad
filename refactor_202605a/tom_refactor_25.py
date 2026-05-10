#!/usr/bin/env python3
"""Cut `update_weights_from_disk` from ModelRunner; paste as a free function in
`weight_updater.py`. R4 concession: takes `model_runner_ref` kwarg because the
body has 10+ `self.X` reads + 4 self-write writebacks + a call to
`self.init_device_graphs()`. Body is byte-identical except for s/self/model_runner_ref/
plus the signature change (`self,` -> `*,\n    model_runner_ref,`).

Caller sites updated:
- model_runner.py: inline callsite inside `update_expert_location` body
- tp_worker.py: positional args -> explicit kwargs
- eagle_worker_v2.py: positional args -> explicit kwargs

Usage:
    uv run --python 3.12 tom_refactor_25.py run
    uv run --python 3.12 tom_refactor_25.py verify
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

BASE = "tom_refactor/24"
TARGET = "tom_refactor/25"


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"
    ew = wt / "python/sglang/srt/speculative/eagle_worker_v2.py"

    s, e = find_method_lines(
        mr.read_text(), class_name="ModelRunner", method_name="update_weights_from_disk"
    )
    func_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def update_weights_from_disk(\n"
            "    self,\n"
            "    model_path: str,\n"
            "    load_format: str,\n"
            "    weight_name_filter: Optional[Callable[[str], bool]] = None,\n"
            "    recapture_cuda_graph: bool = False,\n"
            ") -> tuple[bool, str]:\n",
            "def update_weights_from_disk(\n"
            "    *,\n"
            "    model_runner_ref,\n"
            "    model_path: str,\n"
            "    load_format: str,\n"
            "    weight_name_filter: Optional[Callable[[str], bool]] = None,\n"
            "    recapture_cuda_graph: bool = False,\n"
            ") -> tuple[bool, str]:\n",
        )
        .replace("self.", "model_runner_ref.")
    )

    # Add imports needed by the new free function to weight_updater.py.
    text = wu.read_text()
    text = insert_after(
        text,
        anchor="import logging\n",
        addition=(
            "import gc\n"
            "from typing import Callable, Optional\n"
        ),
    )
    text = insert_after(
        text,
        anchor="from sglang.srt.utils import init_custom_process_group\n",
        addition=(
            "from sglang.srt.configs.load_config import LoadConfig\n"
            "from sglang.srt.model_loader.loader import DefaultModelLoader, get_model_loader\n"
            "from sglang.srt.model_loader.utils import set_default_torch_dtype\n"
            "from sglang.srt.platforms import current_platform\n"
            "from sglang.srt.utils import get_available_gpu_memory\n"
        ),
    )
    wu.write_text(text)
    append_to_file(wu, func_text)

    # model_runner.py: add module import; replace the inline call inside
    # `update_expert_location` body with a module-qualified call.
    text = mr.read_text()
    if "from sglang.srt.model_executor import weight_updater\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.model_executor.pool_configurator import MemoryPoolConfig\n",
            addition="from sglang.srt.model_executor import weight_updater\n",
        )
    text = replace_call_site(
        text,
        old=(
            "                self.update_weights_from_disk(\n"
            "                    get_global_server_args().model_path,\n"
            "                    get_global_server_args().load_format,\n"
            "                    weight_name_filter=weight_name_filter,\n"
            "                )\n"
        ),
        new=(
            "                weight_updater.update_weights_from_disk(\n"
            "                    model_runner_ref=self,\n"
            "                    model_path=get_global_server_args().model_path,\n"
            "                    load_format=get_global_server_args().load_format,\n"
            "                    weight_name_filter=weight_name_filter,\n"
            "                )\n"
        ),
    )
    mr.write_text(text)

    # tp_worker.py: add module import; rewrite caller.
    text = tw.read_text()
    if "from sglang.srt.model_executor import weight_updater\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.model_executor.forward_batch_info import ForwardBatch, PPProxyTensors\n",
            addition="from sglang.srt.model_executor import weight_updater\n",
        )
    text = replace_call_site(
        text,
        old=(
            "        success, message = self.model_runner.update_weights_from_disk(\n"
            "            recv_req.model_path,\n"
            "            recv_req.load_format,\n"
            "            recapture_cuda_graph=recv_req.recapture_cuda_graph,\n"
            "        )\n"
        ),
        new=(
            "        success, message = weight_updater.update_weights_from_disk(\n"
            "            model_runner_ref=self.model_runner,\n"
            "            model_path=recv_req.model_path,\n"
            "            load_format=recv_req.load_format,\n"
            "            recapture_cuda_graph=recv_req.recapture_cuda_graph,\n"
            "        )\n"
        ),
    )
    tw.write_text(text)

    # eagle_worker_v2.py: add module import; rewrite caller.
    text = ew.read_text()
    if "from sglang.srt.model_executor import weight_updater\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.model_executor.forward_batch_info import CaptureHiddenMode, ForwardBatch\n",
            addition="from sglang.srt.model_executor import weight_updater\n",
        )
    text = replace_call_site(
        text,
        old=(
            "        success, message = self._draft_worker.draft_runner.update_weights_from_disk(\n"
            "            recv_req.model_path,\n"
            "            recv_req.load_format,\n"
            "            recapture_cuda_graph=recv_req.recapture_cuda_graph,\n"
            "        )\n"
        ),
        new=(
            "        success, message = weight_updater.update_weights_from_disk(\n"
            "            model_runner_ref=self._draft_worker.draft_runner,\n"
            "            model_path=recv_req.model_path,\n"
            "            load_format=recv_req.load_format,\n"
            "            recapture_cuda_graph=recv_req.recapture_cuda_graph,\n"
            "        )\n"
        ),
    )
    ew.write_text(text)

    git_add_and_commit(
        "Extract update_weights_from_disk to free function in weight_updater",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
