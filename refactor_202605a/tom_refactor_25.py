#!/usr/bin/env python3
"""Cut `update_weights_from_disk` from ModelRunner; paste as a free function in
`weight_updater.py`. R4 concession: takes `model_runner_ref` kwarg because the
body has 10+ `self.X` reads, 4 self-write writebacks, and a call to
`self.init_device_graphs()`. Body is byte-identical except for s/self/model_runner_ref/
plus the signature changes (`self,` -> `*,\n    model_runner_ref,`).

Caller sites updated:
- model_runner.py: line 1492 captured-method ref -> functools.partial
- tp_worker.py: positional kwargs -> explicit kwargs
- eagle_worker_v2.py: positional kwargs -> explicit kwargs
- expert_location_updater.py: positional call -> kwarg call (so partial works)

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
    add_to_grouped_import,
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
    elu = wt / "python/sglang/srt/eplb/expert_location_updater.py"

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

    # model_runner.py: add free-function import; rewire line 1492 via functools.partial.
    text = mr.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.model_executor.pool_configurator import MemoryPoolConfig\n",
        addition=(
            "from sglang.srt.model_executor.weight_updater import (\n"
            "    update_weights_from_disk as _free_update_weights_from_disk,\n"
            ")\n"
        ),
    )
    if "import functools\n" not in text:
        text = insert_after(text, anchor="import gc\n", addition="import functools\n")
    text = replace_call_site(
        text,
        old="            update_weights_from_disk_callable=self.update_weights_from_disk,\n",
        new=(
            "            update_weights_from_disk_callable=functools.partial(\n"
            "                _free_update_weights_from_disk, model_runner_ref=self\n"
            "            ),\n"
        ),
    )
    mr.write_text(text)

    # tp_worker.py: add to existing grouped import; rewrite caller.
    text = tw.read_text()
    text = add_to_grouped_import(
        text,
        anchor_name="init_weights_update_group",
        new_line="    update_weights_from_disk as _free_update_weights_from_disk,",
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
            "        success, message = _free_update_weights_from_disk(\n"
            "            model_runner_ref=self.model_runner,\n"
            "            model_path=recv_req.model_path,\n"
            "            load_format=recv_req.load_format,\n"
            "            recapture_cuda_graph=recv_req.recapture_cuda_graph,\n"
            "        )\n"
        ),
    )
    tw.write_text(text)

    # eagle_worker_v2.py: add new import block; rewrite caller.
    text = ew.read_text()
    text = insert_after(
        text,
        anchor="from sglang.srt.model_executor.forward_batch_info import CaptureHiddenMode, ForwardBatch\n",
        addition=(
            "from sglang.srt.model_executor.weight_updater import (\n"
            "    update_weights_from_disk as _free_update_weights_from_disk,\n"
            ")\n"
        ),
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
            "        success, message = _free_update_weights_from_disk(\n"
            "            model_runner_ref=self._draft_worker.draft_runner,\n"
            "            model_path=recv_req.model_path,\n"
            "            load_format=recv_req.load_format,\n"
            "            recapture_cuda_graph=recv_req.recapture_cuda_graph,\n"
            "        )\n"
        ),
    )
    ew.write_text(text)

    # expert_location_updater.py: change positional call to kwarg form.
    text = elu.read_text()
    text = replace_call_site(
        text,
        old=(
            "            update_weights_from_disk_callable(\n"
            "                get_global_server_args().model_path,\n"
            "                get_global_server_args().load_format,\n"
            "                weight_name_filter=weight_name_filter,\n"
            "            )\n"
        ),
        new=(
            "            update_weights_from_disk_callable(\n"
            "                model_path=get_global_server_args().model_path,\n"
            "                load_format=get_global_server_args().load_format,\n"
            "                weight_name_filter=weight_name_filter,\n"
            "            )\n"
        ),
    )
    elu.write_text(text)

    git_add_and_commit(
        "Extract update_weights_from_disk to free function in weight_updater",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
