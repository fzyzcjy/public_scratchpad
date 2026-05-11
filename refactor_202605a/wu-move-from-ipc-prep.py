#!/usr/bin/env python3
"""Prep stage for wu-move-from-ipc (MECH_COMMIT_SPLIT §"拆 class 场景"):

Reshape ``update_weights_from_ipc`` toward becoming a ``WeightUpdater``
method. ``@staticmethod`` + ``self: WeightUpdater``; body's
``SGLangCheckpointEngineWorkerExtensionImpl(self)`` → ``...(self._mr)``.
External callers in tp_worker.py and eagle_worker_v2.py use local
import + class-qualified call.
"""

# /// script
# requires-python = ">=3.10"
# dependencies = ["typer"]
# ///

import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _helpers import find_method_lines, replace_call_site
from _runner import run_pr

ID = "wu-move-from-ipc-prep"
SUBJECT = "Prep update_weights_from_ipc for move onto WeightUpdater"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/wu-move-from-tensor"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"
    ew = wt / "python/sglang/srt/speculative/eagle_worker_v2.py"

    text = mr.read_text()
    start, end = find_method_lines(text, class_name="ModelRunner", method_name="update_weights_from_ipc")
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    # Try multi-line signature first, fall back to single-line.
    if "    def update_weights_from_ipc(\n        self,\n" in method:
        method = method.replace(
            "    def update_weights_from_ipc(\n        self,\n",
            "    @staticmethod\n    def update_weights_from_ipc(\n        self: \"WeightUpdater\",\n",
            1,
        )
    else:
        method = method.replace(
            "    def update_weights_from_ipc(self, ",
            "    @staticmethod\n    def update_weights_from_ipc(self: \"WeightUpdater\", ",
            1,
        )
    method = method.replace(
        "SGLangCheckpointEngineWorkerExtensionImpl(self)",
        "SGLangCheckpointEngineWorkerExtensionImpl(self._mr)",
    )
    text = "".join(lines[:start]) + method + "".join(lines[end:])
    mr.write_text(text)

    # tp_worker.py: local import + qualified.
    text = tw.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.update_weights_from_ipc(recv_req)\n",
        new=(
            "        from sglang.srt.model_executor.model_runner import ModelRunner\n"
            "\n"
            "        success, message = ModelRunner.update_weights_from_ipc(\n"
            "            self.model_runner.weight_updater, recv_req\n"
            "        )\n"
        ),
    )
    tw.write_text(text)

    # eagle_worker_v2.py.
    text = ew.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self._draft_worker.draft_runner.update_weights_from_ipc(\n",
        new=(
            "        from sglang.srt.model_executor.model_runner import ModelRunner\n"
            "\n"
            "        success, message = ModelRunner.update_weights_from_ipc(\n"
            "            self._draft_worker.draft_runner.weight_updater,\n"
        ),
    )
    ew.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
