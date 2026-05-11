#!/usr/bin/env python3
"""Prep stage for wu-move-from-tensor (MECH_COMMIT_SPLIT §"拆 class 场景"):

Reshape ``update_weights_from_tensor`` + helper
``_update_weights_from_flattened_bucket`` toward becoming ``WeightUpdater``
methods. Module-level helpers (``_unwrap_tensor`` / ``_model_load_weights_direct``)
and the ``LocalSerializedTensor`` dataclass stay in ModelRunner.py at this
stage; ``-move`` cuts them all together.

Body subs (per the original mech script's ``_rewrite_self`` ordering — longest
prefix first so ``self._mr.X`` isn't double-rewritten):
- ``self.model.load_weights`` → ``self._mr.model.load_weights``
- ``self.model,`` → ``self._mr.model,``
- ``self.device`` → ``self._mr.device``
- ``self.server_args.custom_weight_loader`` → ``self._mr.server_args.custom_weight_loader``

External caller in tp_worker.py uses local-import + class-qualified form.
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

ID = "wu-move-from-tensor-prep"
SUBJECT = "Prep update_weights_from_tensor for move onto WeightUpdater"
BODY = ""
AREA = "mech_model_runner"
BASE = "tom_refactor_202605a/primary/mech_model_runner/wu-move-from-distributed-move"
AREA_BRANCH = f"tom_refactor_202605a/primary/{AREA}"


def _reshape(text: str, *, method_name: str) -> str:
    start, end = find_method_lines(text, class_name="ModelRunner", method_name=method_name)
    lines = text.splitlines(keepends=True)
    method = "".join(lines[start:end])
    method = method.replace(
        f"    def {method_name}(\n        self,\n",
        f"    @staticmethod\n    def {method_name}(\n        self: \"WeightUpdater\",\n",
        1,
    )
    # Body subs — longest-prefix-first.
    method = method.replace("self.model.load_weights", "self._mr.model.load_weights")
    method = method.replace("self.model,", "self._mr.model,")
    method = method.replace("self.device", "self._mr.device")
    method = method.replace(
        "self.server_args.custom_weight_loader",
        "self._mr.server_args.custom_weight_loader",
    )
    return "".join(lines[:start]) + method + "".join(lines[end:])


def transform(wt: Path) -> None:
    mr = wt / "python/sglang/srt/model_executor/model_runner.py"
    tw = wt / "python/sglang/srt/managers/tp_worker.py"

    text = mr.read_text()
    text = _reshape(text, method_name="_update_weights_from_flattened_bucket")
    text = _reshape(text, method_name="update_weights_from_tensor")
    # The public method calls the private helper inside its body — class-qualify.
    text = replace_call_site(
        text,
        old="self._update_weights_from_flattened_bucket(",
        new="ModelRunner._update_weights_from_flattened_bucket(self, ",
    )
    mr.write_text(text)

    # External caller: local import + class-qualified.
    text = tw.read_text()
    text = replace_call_site(
        text,
        old="        success, message = self.model_runner.update_weights_from_tensor(\n",
        new=(
            "        from sglang.srt.model_executor.model_runner import ModelRunner\n"
            "\n"
            "        success, message = ModelRunner.update_weights_from_tensor(\n"
            "            self.model_runner.weight_updater,\n"
        ),
    )
    tw.write_text(text)


if __name__ == "__main__":
    run_pr(
        transform=transform,
        base=BASE,
        area_branch=AREA_BRANCH,
        id=ID,
        subject=SUBJECT,
        body=BODY,
    )
