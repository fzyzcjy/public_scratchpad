#!/usr/bin/env python3
"""Cut `update_weights_from_ipc` from ModelRunner; paste as a free function in
`weight_updater.py`. Update tp_worker.py call site.

The free function takes the awkwardly-named kwarg
`model_runner_for_checkpoint_engine` to flag the R4 violation: the worker
extension constructor still takes a full `ModelRunner` reference. That R4
hand-off lives at the call site instead of being hidden behind `self`.
"""

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.append(str(HERE))
sys.path.append(".claude/skills/mechanical-refactor-verify")
from _helpers import (
    append_to_file,
    cut_lines,
    dedent_method_to_function,
    find_method_lines,
)
from mechanical_refactor_verify_utils import (
    git_add_and_commit,
    verify_mechanical_refactor,
)

BASE_COMMIT = "tom_refactor/27"
TARGET_COMMIT = "tom_refactor/28"


def transform(dir_root: Path) -> None:
    mr = dir_root / "python/sglang/srt/model_executor/model_runner.py"
    wu = dir_root / "python/sglang/srt/model_executor/weight_updater.py"
    tw = dir_root / "python/sglang/srt/managers/tp_worker.py"

    s, e = find_method_lines(mr.read_text(), class_name="ModelRunner", method_name="update_weights_from_ipc")
    func_text = dedent_method_to_function(cut_lines(mr, s, e)).replace(
        "def update_weights_from_ipc(self, recv_req):",
        "def update_weights_from_ipc(*, model_runner_for_checkpoint_engine, recv_req):",
    ).replace(
        "SGLangCheckpointEngineWorkerExtensionImpl(self)",
        "SGLangCheckpointEngineWorkerExtensionImpl(model_runner_for_checkpoint_engine)",
    )
    append_to_file(wu, func_text)

    text = tw.read_text()
    text = text.replace(
        "    update_weights_from_tensor as _free_update_weights_from_tensor,\n)\n",
        "    update_weights_from_tensor as _free_update_weights_from_tensor,\n)\n"
        "from sglang.srt.model_executor.weight_updater import (\n"
        "    update_weights_from_ipc as _free_update_weights_from_ipc,\n"
        ")\n",
    )
    text = text.replace(
        "        success, message = self.model_runner.update_weights_from_ipc(recv_req)\n",
        "        success, message = _free_update_weights_from_ipc(\n"
        "            model_runner_for_checkpoint_engine=self.model_runner,\n"
        "            recv_req=recv_req,\n"
        "        )\n",
    )
    tw.write_text(text)

    git_add_and_commit(
        "Extract update_weights_from_ipc to free function in weight_updater",
        cwd=str(dir_root),
    )


if __name__ == "__main__":
    verify_mechanical_refactor(
        base_commit=BASE_COMMIT,
        target_commit=TARGET_COMMIT,
        transform=transform,
    )
