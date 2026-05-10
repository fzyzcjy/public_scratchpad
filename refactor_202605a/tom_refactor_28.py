#!/usr/bin/env python3
"""Cut `update_weights_from_ipc` from ModelRunner; paste as a free function in
`weight_updater.py`. Update tp_worker.py call site.

The free function takes the awkwardly-named kwarg
`model_runner_for_checkpoint_engine` to flag the R4 violation: the worker
extension constructor still takes a full `ModelRunner` reference. That R4
hand-off lives at the call site instead of being hidden behind `self`.

Usage:
    uv run --python 3.12 tom_refactor_28.py run
    uv run --python 3.12 tom_refactor_28.py verify
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

BASE = "tom_refactor/27"
TARGET = "tom_refactor/28"


def transform(wt: Path) -> None:
    sys.path.insert(0, str(wt / ".claude/skills/mechanical-refactor-verify"))
    from mechanical_refactor_verify_utils import git_add_and_commit

    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    wu = wt / "python/sglang/srt/model_executor/weight_updater.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"

    s, e = find_method_lines(
        mr.read_text(),
        class_name="ModelRunner",
        method_name="update_weights_from_ipc",
    )
    func_text = (
        dedent_method_to_function(cut_lines(mr, s, e))
        .replace(
            "def update_weights_from_ipc(self, recv_req):",
            "def update_weights_from_ipc(*, model_runner_for_checkpoint_engine, recv_req):",
        )
        .replace(
            "SGLangCheckpointEngineWorkerExtensionImpl(self)",
            "SGLangCheckpointEngineWorkerExtensionImpl(model_runner_for_checkpoint_engine)",
        )
    )
    append_to_file(wu, func_text)

    # tp_worker.py already imports `weight_updater` (added in /25); just rewrite
    # the call site.
    text = tw.read_text()
    if "from sglang.srt.model_executor import weight_updater\n" not in text:
        text = insert_after(
            text,
            anchor="from sglang.srt.model_executor.forward_batch_info import ForwardBatch, PPProxyTensors\n",
            addition="from sglang.srt.model_executor import weight_updater\n",
        )
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.update_weights_from_ipc(recv_req)\n",
        new=(
            "        success, message = weight_updater.update_weights_from_ipc(\n"
            "            model_runner_for_checkpoint_engine=self.model_runner,\n"
            "            recv_req=recv_req,\n"
            "        )\n"
        ),
    )
    tw.write_text(text)

    git_add_and_commit(
        "Extract update_weights_from_ipc to free function in weight_updater",
        cwd=str(wt),
    )


if __name__ == "__main__":
    run_pr(transform=transform, base=BASE, target=TARGET)
